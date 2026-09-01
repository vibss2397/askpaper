import re
from datetime import datetime
from pathlib import Path

from .. import config
from ..llm import get_client
from ..llm.base import LLMNotConfiguredError
from ..vault import get_vault_path, SPACES_DIR, list_spaces

SLUG_PROMPT = """Generate a very short 2-4 word slug/topic name for a research Q&A session. The slug should summarize the topic being discussed. Return ONLY the slug, lowercase, words separated by hyphens. No quotes, no punctuation, no explanation.

Question: {question}
Context: {context}
Source: {source}

Slug:"""


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-")


def _heuristic_slug(source_title: str, question: str) -> str:
    if source_title:
        words = source_title.lower().split()
        significant = [w for w in words if w.isalpha() and len(w) > 2][:4]
        if significant:
            return "-".join(significant)
        return _slugify(source_title)[:40]
    if question:
        words = question.lower().split()
        significant = [w for w in words if w.isalpha() and len(w) > 2][:4]
        if significant:
            return "-".join(significant)
        return _slugify(question)[:40]
    return "research-session"


async def _generate_slug(
    question: str,
    selected_text: str = "",
    source_title: str = "",
) -> str:
    try:
        client = get_client()
    except LLMNotConfiguredError:
        return _heuristic_slug(source_title, question)

    context = selected_text[:200] if selected_text else "not provided"
    source = source_title if source_title else "not provided"
    prompt = SLUG_PROMPT.format(question=question, context=context, source=source)

    try:
        result = []
        async for token in client.generate(prompt=prompt, system=None):
            result.append(token)
        slug = "".join(result).strip().strip('"').strip("'").lower()
        slug = _slugify(slug)
        if slug and len(slug.split("-")) >= 1:
            return slug[:60]
    except Exception:
        pass

    return _heuristic_slug(source_title, question)


def _build_session_content(
    space: str,
    model: str,
    slug: str,
    question: str,
    answer: str,
    selected_text: str = "",
    source_app: str = "",
    source_title: str = "",
    source_url: str = "",
    paper_id: str = "",
    section: str = "",
    existing_content: str = "",
) -> tuple[str, int]:
    q_number = 1
    if existing_content:
        existing_qs = re.findall(r"^### Q(\d+)$", existing_content, re.MULTILINE)
        if existing_qs:
            q_number = max(int(n) for n in existing_qs) + 1

    source_parts = [p for p in [source_app, source_title, source_url] if p]
    source_line = " — ".join(source_parts) if source_parts else "terminal"

    entry = f"\n### Q{q_number}\n\n"
    entry += f"**Q:** {question}\n\n"

    if paper_id:
        entry += f"**Paper:** {paper_id}\n\n"

    if section:
        entry += f"**Section:** {section}\n\n"

    if selected_text:
        entry += f"**Context:**\n> {selected_text}\n\n"

    entry += f"**Source:** {source_line}\n\n"
    entry += f"**A:** {answer}\n"

    if existing_content:
        content = existing_content + entry
        # Keep frontmatter qa_count current on reading-session files
        content = re.sub(
            r"(?m)^(qa_count:)\s*\d+$", rf"\g<1> {q_number}", content, count=1
        )
        return content, q_number
    else:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        header_lines = [
            "---",
            f"space: {space}",
            f"model: {model}",
            f"date: {today}",
            f"slug: {slug}",
        ]
        if paper_id:
            header_lines.append(f"paper: {paper_id}")
            header_lines.append("reading_session: true")
            header_lines.append(f"started_at: {now.isoformat(timespec='seconds')}")
            header_lines.append(f"qa_count: {q_number}")
            if source_url:
                header_lines.append(f"source_url: {source_url}")
        header_lines.append("---")
        return "\n".join(header_lines) + f"\n\n# Session: {slug}\n" + entry, q_number


def reading_session_path(space: str, paper_id: str) -> Path:
    vault_path = get_vault_path()
    return vault_path / SPACES_DIR / space / "sessions" / f"reading-{paper_id}.md"


async def save_qa(
    space: str,
    question: str,
    answer: str,
    selected_text: str = "",
    source_app: str = "",
    source_title: str = "",
    source_url: str = "",
    paper_id: str = "",
    section: str = "",
    slug: str | None = None,
) -> str:
    if space not in list_spaces():
        from ..agent import PaperAgentError
        raise PaperAgentError(f"Space '{space}' does not exist.")

    if paper_id:
        # Reading session — one file per paper, deterministic name, no LLM slug call
        slug = f"reading-{paper_id}"
        filepath = reading_session_path(space, paper_id)
    else:
        if slug is None:
            slug = await _generate_slug(question, selected_text, source_title)
        today = datetime.now().strftime("%Y%m%d")
        vault_path = get_vault_path()
        filepath = (
            vault_path / SPACES_DIR / space / "sessions" / f"{slug}-{today}.md"
        )

    cfg = config.load_config()
    model = cfg.get("model", config.DEFAULT_MODEL)

    existing_content = ""
    if filepath.exists():
        existing_content = filepath.read_text()

    content, q_number = _build_session_content(
        space=space,
        model=model,
        slug=slug,
        question=question,
        answer=answer,
        selected_text=selected_text,
        source_app=source_app,
        source_title=source_title,
        source_url=source_url,
        paper_id=paper_id,
        section=section,
        existing_content=existing_content,
    )

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)

    from ..vault import regenerate_index
    regenerate_index(space)

    return str(filepath)
