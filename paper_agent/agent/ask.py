import asyncio
import json
from collections.abc import AsyncIterator

from . import PaperAgentError
from .. import context
from ..llm import get_client, prompts
from ..llm.base import LLMNotConfiguredError
from ..vault import get_paper_path, list_spaces
from .sections import deepest, find_section

THREAD_HISTORY_TURNS = 5


def _status(event_type: str, **extra) -> str:
    payload = {"status": event_type}
    payload.update(extra)
    return json.dumps(payload)


def _should_continue(current_section: str, prev_pairs: list[dict], has_selection: bool) -> bool:
    """Follow-up rules:
    - no prior turns → fresh
    - no selected text → continue (asking about what's on screen)
    - selection not found in paper.md → continue (fallback: same paper = same thread)
    - same section/subsection as last turn → continue
    - different section → fresh
    """
    if not prev_pairs:
        return False
    if not has_selection:
        return True
    if not current_section:
        return True
    return prev_pairs[-1].get("section", "") == current_section


async def ask(
    space: str,
    question: str,
    selected_text: str = "",
    source_app: str = "",
    source_title: str = "",
    source_url: str = "",
    paper_id: str | None = None,
    fresh: bool = False,
) -> AsyncIterator[str]:
    if space not in list_spaces():
        raise PaperAgentError(
            f"Space '{space}' does not exist. Create it with:\n"
            f"  paper-agent init --space {space}"
        )

    try:
        client = get_client()
    except LLMNotConfiguredError as e:
        raise PaperAgentError(str(e))

    paper_content = ""
    paper_title = ""
    resolved_paper_id = None

    if paper_id:
        resolved_paper_id = paper_id
    elif source_url:
        from ..ingestion.pipeline import find_paper_anywhere, ingest

        match = find_paper_anywhere(source_url, prefer_space=space)
        if match:
            space, resolved_paper_id = match
        else:
            yield _status("ingesting", message="Downloading and converting paper...")
            try:
                metadata = await ingest(space, source_url)
                resolved_paper_id = metadata["slug"]
                yield _status(
                    "ingested",
                    paper_id=resolved_paper_id,
                    title=metadata.get("title", ""),
                )
            except Exception as e:
                yield _status("ingest_failed", error=str(e))
    elif not selected_text.strip():
        # No selection and no URL: assume continuation of the last thread.
        # The daemon remembers the last active paper from context.
        active = context.get_active_paper_id()
        if active:
            for candidate_space in dict.fromkeys([space, context.get_last_space() or ""]):
                if (get_paper_path(candidate_space, active) / "paper.md").exists():
                    space = candidate_space
                    resolved_paper_id = active
                    break

    if resolved_paper_id:
        paper_dir = get_paper_path(space, resolved_paper_id)
        paper_md_path = paper_dir / "paper.md"
        if paper_md_path.exists():
            paper_content = paper_md_path.read_text()
            meta_path = paper_dir / "metadata.yaml"
            if meta_path.exists():
                import yaml

                with open(meta_path) as f:
                    meta = yaml.safe_load(f) or {}
                paper_title = meta.get("title", "")

        yield _status(
            "resolved",
            space=space,
            paper={"paper_id": resolved_paper_id, "title": paper_title},
        )

    # Thread decision: follow-up vs fresh question
    current_section = find_section(paper_content, selected_text) if paper_content else ""
    conversation_history: list[dict] = []
    effective_section = current_section
    if resolved_paper_id:
        from ..session.reader import get_recent_qa_for_paper

        prev_pairs = get_recent_qa_for_paper(space, resolved_paper_id, n=THREAD_HISTORY_TURNS)
        continued = not fresh and _should_continue(
            current_section, prev_pairs, bool(selected_text.strip())
        )
        # Continuing without a section match (no selection, or match failed):
        # assume the same section as the last question — keeps the thread's
        # section identity so the next real selection in that section still
        # continues instead of breaking the chain.
        if continued and not effective_section and prev_pairs:
            effective_section = prev_pairs[-1].get("section", "")
        yield _status("thread", section=deepest(effective_section), continued=continued)
        if continued:
            conversation_history = [
                {"question": p["question"], "answer": p["answer"]} for p in prev_pairs
            ]

    system_prompt = prompts.build_system_prompt(space)
    user_prompt = prompts.build_user_prompt(
        question=question,
        selected_text=selected_text,
        source_app=source_app,
        source_title=source_title,
        source_url=source_url,
        paper_content=paper_content,
        paper_title=paper_title,
        conversation_history=conversation_history,
    )

    from ..session.writer import save_qa, _generate_slug

    slug_task = (
        None
        if resolved_paper_id
        else asyncio.create_task(_generate_slug(question, selected_text, source_title))
    )

    full_answer: list[str] = []

    try:
        async for token in client.generate(
            prompt=user_prompt,
            system=system_prompt,
        ):
            full_answer.append(token)
            yield token
    finally:
        await client.aclose()

    answer_text = "".join(full_answer)
    slug = await slug_task if slug_task else None

    session_path = await save_qa(
        space=space,
        question=question,
        answer=answer_text,
        selected_text=selected_text,
        source_app=source_app,
        source_title=source_title,
        source_url=source_url,
        paper_id=resolved_paper_id or "",
        section=effective_section,
        slug=slug,
    )
    context.update_context(
        space=space,
        source_url=source_url if source_url else None,
        source_title=source_title if source_title else None,
        source_app=source_app if source_app else None,
        session_file=session_path,
        paper_id=resolved_paper_id,
    )
