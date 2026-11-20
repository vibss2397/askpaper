import json

from . import PaperAgentError
from ..llm import get_structured_client, prompts
from ..llm.base import LLMNotConfiguredError
from ..vault import (
    get_paper_metadata,
    get_paper_summary,
    get_vault_path,
    list_papers,
    list_spaces,
    regenerate_index,
    SPACES_DIR,
)


MIN_PAPERS_FOR_SYNTHESIS = 2
VERDICT_RETRIES = 1


async def synthesize(space: str) -> dict | None:
    if space not in list_spaces():
        raise PaperAgentError(
            f"Space '{space}' does not exist. Create it with:\n"
            f"  paper-agent init --space {space}"
        )

    summaries = _collect_summaries(space)

    if len(summaries) < MIN_PAPERS_FOR_SYNTHESIS:
        raise PaperAgentError(
            f"Only {len(summaries)} paper(s) with summaries found in '{space}'. "
            f"Need at least {MIN_PAPERS_FOR_SYNTHESIS} to synthesize."
        )

    try:
        client = get_structured_client()
    except LLMNotConfiguredError as e:
        raise PaperAgentError(str(e))

    # One-vs-rest: each paper is judged against all papers after it in a
    # single call, so every pair gets exactly one forced verdict (no
    # open-ended "find connections" the model can bail on with an empty
    # array). N papers -> N-1 calls.
    connections = []
    unrelated = []
    for i, focus in enumerate(summaries):
        others = summaries[i + 1:]
        if not others:
            break

        verdicts = await _verdicts_for(client, focus, others)

        by_title = {v.get("other_paper", "").strip(): v for v in verdicts}
        for other in others:
            verdict = by_title.get(other["title"].strip())
            if verdict is None:
                raise PaperAgentError(
                    f"Synthesize verdict missing for '{other['title']}' "
                    f"(focus paper '{focus['title']}')."
                )
            entry = {
                "paper_a": focus["title"],
                "paper_b": other["title"],
                "relationship": verdict.get("relationship", "unrelated"),
                "insight": verdict.get("insight", ""),
            }
            if verdict.get("related"):
                connections.append(entry)
            else:
                unrelated.append(entry)

    if connections:
        overall = await client.generate_structured(
            prompt=prompts.build_overall_synthesis_prompt(summaries, connections),
            system=prompts.SYNTHESIZE_SYSTEM_PROMPT,
            response_schema=prompts.OVERALL_SYNTHESIS_SCHEMA,
        )
        overall_synthesis = overall.get("overall_synthesis", "")
    else:
        # All pairs were explicitly judged unrelated — a verified negative,
        # not a model bail-out.
        overall_synthesis = (
            "No significant cross-paper connections found. "
            f"All {len(unrelated)} paper pair(s) were evaluated and judged unrelated."
        )

    result = {
        "connections": connections,
        "unrelated": unrelated,
        "overall_synthesis": overall_synthesis,
    }

    markdown = _render_synthesis_md(result)
    vault_path = get_vault_path()
    summaries_dir = vault_path / SPACES_DIR / space / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    insights_path = summaries_dir / "cross-paper-insights.md"
    insights_path.write_text(markdown)

    json_path = summaries_dir / "synthesis.json"
    json_path.write_text(json.dumps(result, indent=2))

    regenerate_index(space)

    return result


async def _verdicts_for(client, focus: dict, others: list[dict]) -> list[dict]:
    """One call: focus paper vs all others, forced verdict per other paper.

    Retries once on malformed output (missing/partial verdicts); the
    retry is a JSON-safety net, not an emptiness workaround — with
    forced verdicts the model cannot return zero verdicts.
    """
    prompt = prompts.build_synthesize_pairwise_prompt(focus, others)

    last_error = None
    for attempt in range(VERDICT_RETRIES + 1):
        try:
            result = await client.generate_structured(
                prompt=prompt,
                system=prompts.SYNTHESIZE_SYSTEM_PROMPT,
                response_schema=prompts.SYNTHESIS_VERDICTS_SCHEMA,
            )
            verdicts = result.get("verdicts", [])
            titles = {v.get("other_paper", "").strip() for v in verdicts}
            if all(o["title"].strip() in titles for o in others):
                return verdicts
            last_error = (
                f"got {len(verdicts)} verdict(s) for {len(others)} paper(s)"
            )
        except Exception as e:
            last_error = str(e)

    raise PaperAgentError(
        f"Synthesize verdict call failed for focus paper "
        f"'{focus['title']}' ({last_error})."
    )


def _collect_summaries(space: str) -> list[dict]:
    summaries = []
    for idx, paper_id in enumerate(list_papers(space), 1):
        data = get_paper_summary(space, paper_id)
        if not data:
            continue
        summary = data["summary"]
        summary["index"] = idx
        summary["title"] = get_paper_metadata(space, paper_id).get("title", paper_id)
        summary["paper_id"] = paper_id
        summaries.append(summary)
    return summaries


def _render_synthesis_md(result: dict) -> str:
    parts = ["# Cross-Paper Insights", ""]

    connections = result.get("connections", [])
    if connections:
        for conn in connections:
            parts.append(f"## {conn['paper_a']} ↔ {conn['paper_b']}")
            parts.append(f"**{conn['relationship']}** — {conn['insight']}")
            parts.append("")
    else:
        parts.append("No connections found — every pair was judged on its merits.")
        parts.append("")

    unrelated = result.get("unrelated", [])
    if unrelated:
        parts.append("## Judged Unrelated")
        for pair in unrelated:
            parts.append(f"- **{pair['paper_a']} ↔ {pair['paper_b']}** — {pair['insight']}")
        parts.append("")

    overall = result.get("overall_synthesis", "")
    if overall:
        parts.append("## Overall Synthesis")
        parts.append(overall)
        parts.append("")

    return "\n".join(parts)
