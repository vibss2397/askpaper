import json

from . import PaperAgentError
from ..llm import get_client, prompts
from ..llm.base import LLMNotConfiguredError
from ..vault import get_paper_metadata, get_vault_path, list_papers, list_spaces, SPACES_DIR


MIN_PAPERS_FOR_SYNTHESIS = 2


async def synthesize(space: str) -> dict | None:
    if space not in list_spaces():
        raise PaperAgentError(
            f"Space '{space}' does not exist. Create it with:\n"
            f"  paper-agent init --space {space}"
        )

    summaries = []
    for idx, paper_id in enumerate(list_papers(space), 1):
        meta = get_paper_metadata(space, paper_id)
        summary = meta.get("summary")
        if not summary:
            continue
        summary["index"] = idx
        summary["title"] = meta.get("title", paper_id)
        summary["paper_id"] = paper_id
        summaries.append(summary)

    if len(summaries) < MIN_PAPERS_FOR_SYNTHESIS:
        raise PaperAgentError(
            f"Only {len(summaries)} paper(s) with summaries found in '{space}'. "
            f"Need at least {MIN_PAPERS_FOR_SYNTHESIS} to synthesize."
        )

    try:
        client = get_client()
    except LLMNotConfiguredError as e:
        raise PaperAgentError(str(e))

    user_prompt = prompts.build_synthesize_prompt(summaries)

    result = await client.generate_structured(
        prompt=user_prompt,
        system=prompts.SYNTHESIZE_SYSTEM_PROMPT,
        response_schema=prompts.SYNTHESIS_SCHEMA,
    )

    connections = result.get("connections", [])
    if not connections:
        return None

    markdown = _render_synthesis_md(result, summaries)
    vault_path = get_vault_path()
    summaries_dir = vault_path / SPACES_DIR / space / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    insights_path = summaries_dir / "cross-paper-insights.md"
    insights_path.write_text(markdown)

    json_path = summaries_dir / "synthesis.json"
    json_path.write_text(json.dumps(result, indent=2))

    from ..vault import regenerate_index
    regenerate_index(space)

    return result


def _render_synthesis_md(result: dict, summaries: list[dict]) -> str:
    title_map = {s["title"]: s["title"] for s in summaries}

    parts = ["# Cross-Paper Insights", ""]

    for conn in result.get("connections", []):
        paper_a = conn["paper_a"]
        paper_b = conn["paper_b"]
        rel = conn["relationship"]
        insight = conn["insight"]

        parts.append(f"## {paper_a} ↔ {paper_b}")
        parts.append(f"**{rel}** — {insight}")
        parts.append("")

    overall = result.get("overall_synthesis", "")
    if overall:
        parts.append("## Overall Synthesis")
        parts.append(overall)
        parts.append("")

    return "\n".join(parts)
