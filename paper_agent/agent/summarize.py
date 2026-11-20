import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import PaperAgentError
from ..llm import get_structured_client, prompts
from ..llm.base import LLMNotConfiguredError
from ..session import reader as session_reader
from ..vault import get_paper_metadata, get_paper_path, list_spaces, regenerate_index


MIN_QA_FOR_SUMMARY = 5


async def summarize(space: str, paper_id: str) -> dict | None:
    if space not in list_spaces():
        raise PaperAgentError(
            f"Space '{space}' does not exist. Create it with:\n"
            f"  paper-agent init --space {space}"
        )

    paper_dir = get_paper_path(space, paper_id)
    if not paper_dir.exists():
        raise PaperAgentError(
            f"Paper '{paper_id}' not found in space '{space}'."
        )

    qa_pairs = session_reader.get_qa_by_paper(space, paper_id)

    if len(qa_pairs) < MIN_QA_FOR_SUMMARY:
        raise PaperAgentError(
            f"Only {len(qa_pairs)} Q&A found for '{paper_id}'. "
            f"Need at least {MIN_QA_FOR_SUMMARY} to generate a summary."
        )

    try:
        client = get_structured_client()
    except LLMNotConfiguredError as e:
        raise PaperAgentError(str(e))

    meta = get_paper_metadata(space, paper_id)
    paper_title = meta.get("title", paper_id)

    user_prompt = prompts.build_summarize_prompt(paper_title, qa_pairs)

    result = await client.generate_structured(
        prompt=user_prompt,
        system=prompts.SUMMARIZE_SYSTEM_PROMPT,
        response_schema=prompts.SUMMARY_SCHEMA,
    )

    if not result.get("should_summarize", True):
        return None

    markdown = _render_summary_md(paper_title, result)
    summary_path = paper_dir / "summary.md"
    summary_path.write_text(markdown)

    # Sidecar JSON is the single structured-storage convention (9.5.4):
    # freshness metadata lives with the summary it describes (9.5.3).
    summary_data = {
        "summary": result,
        "summarized_qa_count": len(qa_pairs),
        "summarized_at": datetime.now(timezone.utc).isoformat(),
        "model": client.model,
    }
    (paper_dir / "summary.json").write_text(json.dumps(summary_data, indent=2))

    # metadata.yaml goes back to being purely descriptive — drop the
    # legacy embedded summary if an older summarize wrote it there.
    meta.pop("summary", None)
    meta_path = paper_dir / "metadata.yaml"
    with open(meta_path, "w") as f:
        yaml.dump(meta, f)

    regenerate_index(space)

    return result


def _render_summary_md(paper_title: str, result: dict) -> str:
    parts = [f"# Summary: {paper_title}", ""]

    for theme in result.get("themes", []):
        parts.append(f"## {theme['name']}")
        parts.append(f"- **Explored:** {theme['explored']}")
        parts.append(f"- **Learned:** {theme['learned']}")
        parts.append(f"- **Surprise:** {theme['surprise']}")
        parts.append(f"- **So what:** {theme['so_what']}")
        parts.append("")

    open_threads = result.get("open_threads", [])
    if open_threads:
        parts.append("## Open threads")
        for thread in open_threads:
            parts.append(f"- {thread}")
        parts.append("")

    gaps = result.get("gaps", [])
    if gaps:
        parts.append("## Gaps")
        for gap in gaps:
            parts.append(f"- {gap}")
        parts.append("")

    takeaway = result.get("biggest_takeaway", "")
    if takeaway:
        parts.append("## Biggest takeaway")
        parts.append(takeaway)
        parts.append("")

    return "\n".join(parts)
