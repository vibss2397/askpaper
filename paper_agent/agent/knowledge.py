from ..llm import get_client, prompts
from ..llm.base import LLMNotConfiguredError
from ..vault import get_paper_metadata, get_vault_path, list_papers, list_spaces, SPACES_DIR
from . import PaperAgentError


MIN_PAPERS_FOR_KNOWLEDGE = 1


async def update_knowledge(space: str) -> dict | None:
    if space not in list_spaces():
        raise PaperAgentError(
            f"Space '{space}' does not exist. Create it with:\n"
            f"  paper-agent init --space {space}"
        )

    summaries = _collect_summaries(space)

    if len(summaries) < MIN_PAPERS_FOR_KNOWLEDGE:
        raise PaperAgentError(
            f"No summarized papers found in '{space}'. "
            f"Summarize at least {MIN_PAPERS_FOR_KNOWLEDGE} paper(s) first "
            f"with: paper-agent summarize --space {space} --paper <paper_id>"
        )

    try:
        client = get_client()
    except LLMNotConfiguredError as e:
        raise PaperAgentError(str(e))

    user_prompt = prompts.build_knowledge_prompt(summaries)

    result = await client.generate_structured(
        prompt=user_prompt,
        system=prompts.KNOWLEDGE_SYSTEM_PROMPT,
        response_schema=prompts.KNOWLEDGE_SCHEMA,
    )

    markdown = _render_knowledge_md(result)
    vault_path = get_vault_path()
    space_path = vault_path / SPACES_DIR / space
    space_path.mkdir(parents=True, exist_ok=True)
    knowledge_path = space_path / "knowledge.md"
    knowledge_path.write_text(markdown)

    from ..vault import regenerate_index
    regenerate_index(space)

    return result


def _render_knowledge_md(result: dict) -> str:
    parts = ["# Knowledge", ""]

    for theme in result.get("themes", []):
        confidence = theme.get("confidence", "")
        parts.append(f"## {theme['name']}")
        parts.append(f"*Confidence: {confidence}*")
        parts.append("")
        parts.append(theme.get("understanding", ""))
        papers = theme.get("papers", [])
        if papers:
            parts.append(f"\n*Papers: {', '.join(papers)}*")
        parts.append("")

    key_facts = result.get("key_facts", [])
    if key_facts:
        parts.append("## Key Facts")
        for fact in key_facts:
            parts.append(f"- {fact['fact']} *({fact.get('source', '')})*")
        parts.append("")

    evolving = result.get("evolving_understanding", "")
    if evolving:
        parts.append("## Evolving Understanding")
        parts.append(evolving)
        parts.append("")

    overall = result.get("overall_synthesis", "")
    if overall:
        parts.append("## Overall")
        parts.append(overall)
        parts.append("")

    return "\n".join(parts)


async def update_open_questions(space: str) -> dict | None:
    if space not in list_spaces():
        raise PaperAgentError(
            f"Space '{space}' does not exist. Create it with:\n"
            f"  paper-agent init --space {space}"
        )

    summaries = _collect_summaries(space)

    if len(summaries) < MIN_PAPERS_FOR_KNOWLEDGE:
        raise PaperAgentError(
            f"No summarized papers found in '{space}'. "
            f"Summarize at least {MIN_PAPERS_FOR_KNOWLEDGE} paper(s) first "
            f"with: paper-agent summarize --space {space} --paper <paper_id>"
        )

    try:
        client = get_client()
    except LLMNotConfiguredError as e:
        raise PaperAgentError(str(e))

    user_prompt = prompts.build_open_questions_prompt(summaries)

    result = await client.generate_structured(
        prompt=user_prompt,
        system=prompts.OPEN_QUESTIONS_SYSTEM_PROMPT,
        response_schema=prompts.OPEN_QUESTIONS_SCHEMA,
    )

    questions = result.get("questions", [])
    if not questions:
        return None

    markdown = _render_open_questions_md(result)
    vault_path = get_vault_path()
    space_path = vault_path / SPACES_DIR / space
    space_path.mkdir(parents=True, exist_ok=True)
    questions_path = space_path / "open-questions.md"
    questions_path.write_text(markdown)

    from ..vault import regenerate_index
    regenerate_index(space)

    return result


def _collect_summaries(space: str) -> list[dict]:
    summaries = []
    for paper_id in list_papers(space):
        meta = get_paper_metadata(space, paper_id)
        summary = meta.get("summary")
        if not summary:
            continue
        summary["title"] = meta.get("title", paper_id)
        summary["paper_id"] = paper_id
        summaries.append(summary)
    return summaries


def _render_open_questions_md(result: dict) -> str:
    parts = ["# Open Questions", ""]

    questions = result.get("questions", [])
    priority_order = {"high": 0, "medium": 1, "low": 2}
    questions.sort(key=lambda q: priority_order.get(q.get("priority", "low"), 3))

    high = [q for q in questions if q.get("priority") == "high"]
    medium = [q for q in questions if q.get("priority") == "medium"]
    low = [q for q in questions if q.get("priority") == "low"]

    for label, group in [("High Priority", high), ("Medium Priority", medium), ("Low Priority", low)]:
        if not group:
            continue
        parts.append(f"## {label}")
        for q in group:
            qtype = q.get("type", "")
            papers = q.get("papers", [])
            parts.append(f"### {q['question']}")
            parts.append(f"*Type: {qtype} · Papers: {', '.join(papers)}*")
            parts.append("")
            parts.append(q.get("context", ""))
            parts.append("")

    if not questions:
        parts.append("No open questions or gaps found. All threads resolved.")

    return "\n".join(parts)
