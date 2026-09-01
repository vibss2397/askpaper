SYSTEM_PROMPT = (
    "You are a research assistant helping someone read and understand academic papers. "
    "The user is working in space '{space}'. "
    "When provided with selected text as context, ground your answers in that context. "
    "When provided with the full paper content, use it as your primary source. "
    "When provided with earlier conversation turns, maintain continuity — "
    "references like 'it' or 'that' refer to the prior discussion. "
    "Be concise, accurate, and helpful. "
    "Use markdown formatting when it improves clarity."
)


def build_system_prompt(space: str) -> str:
    return SYSTEM_PROMPT.format(space=space)


def build_user_prompt(
    question: str,
    selected_text: str = "",
    source_app: str = "",
    source_title: str = "",
    source_url: str = "",
    paper_content: str = "",
    paper_title: str = "",
    conversation_history: list[dict] | None = None,
) -> str:
    parts = []

    if paper_content:
        header = f"**Paper:** {paper_title}" if paper_title else "**Paper content:**"
        parts.append(f"{header}\n\n{paper_content}")

    if conversation_history:
        lines = ["**Earlier in this conversation:**"]
        for turn in conversation_history:
            lines.append(f"**User:** {turn['question']}")
            lines.append(f"**Assistant:** {turn['answer']}")
        parts.append("\n\n".join(lines))

    if selected_text:
        parts.append(f"**Selected text:**\n> {selected_text}")

    source_fragments = [s for s in [source_app, source_title, source_url] if s]
    if source_fragments:
        parts.append(f"**Source:** {' — '.join(source_fragments)}")

    parts.append(f"**Question:** {question}")

    return "\n\n".join(parts)


SUMMARIZE_SYSTEM_PROMPT = (
    "You are a research assistant. Your task is to distill insights from a user's "
    "Q&A history about a specific paper they read. You are NOT summarizing the "
    "paper — you are summarizing what the user learned through conversation."
)

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "should_summarize": {
            "type": "boolean",
            "description": (
                "False if the Q&A was superficial — quick clarifications, "
                "terminology lookups, no real exploration. Don't inflate "
                "shallow engagement."
            ),
        },
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "explored": {
                        "type": "string",
                        "description": "What was asked about",
                    },
                    "learned": {
                        "type": "string",
                        "description": "The factual takeaway",
                    },
                    "surprise": {
                        "type": "string",
                        "description": (
                            "What was non-obvious, counterintuitive, or "
                            "challenged an assumption. What would the user "
                            "NOT have known before asking? If nothing was "
                            "surprising, say so."
                        ),
                    },
                    "so_what": {
                        "type": "string",
                        "description": (
                            "How does this change how the user should think "
                            "about the topic? What assumption did this "
                            "challenge or confirm?"
                        ),
                    },
                },
                "required": ["name", "explored", "learned", "surprise", "so_what"],
            },
        },
        "open_threads": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Things the answers touched on but the user didn't follow "
                "up on. Specific, grounded in the Q&A — not generic "
                "'explore more'. Empty array if none."
            ),
        },
        "gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "What the user didn't ask about but should have, based on "
                "their exploration trajectory. Point to the specific gap — "
                "e.g. 'you asked about X but not about Y which the paper "
                "addresses directly in section Z'. Not generic coverage "
                "suggestions. Empty array if none."
            ),
        },
        "biggest_takeaway": {
            "type": "string",
            "description": "1-2 sentences. The single most important insight from the Q&A.",
        },
    },
    "required": ["should_summarize", "themes", "biggest_takeaway", "open_threads", "gaps"],
}


def build_summarize_prompt(paper_title: str, qa_pairs: list[dict]) -> str:
    sections = [f"## Paper: {paper_title}", "The user read this paper and asked the following questions.", "## Q&A History"]

    for qa in qa_pairs:
        sections.append(f"### {qa['id']}")
        sections.append(f"**Question:** {qa['question']}")
        if qa.get("context"):
            sections.append(f"**Context:**\n> {qa['context']}")
        sections.append(f"**Answer:** {qa['answer']}")

    sections.append("## Your task")
    sections.append(
        "Analyze these Q&A exchanges and distill the insights that emerged.\n\n"
        "For each field:\n"
        "- **should_summarize**: Set to false if the Q&A was superficial — quick "
        "clarifications, terminology lookups, no real exploration. Don't inflate "
        "shallow engagement.\n"
        "- **themes**: Group questions thematically (not chronologically). For each "
        "theme:\n"
        "  - explored: what was asked about\n"
        "  - learned: the factual takeaway\n"
        "  - surprise: what was non-obvious or counterintuitive? What would the "
        "user NOT have known before asking? If nothing was surprising, say so "
        "honestly.\n"
        "  - so_what: how does this change how the user should think about the "
        "topic? What assumption did this challenge or confirm?\n"
        "- **open_threads**: Things the answers mentioned but the user didn't "
        "follow up on. Be specific — reference the actual exchange. Empty array "
        "if none.\n"
        "- **gaps**: What the user didn't ask but should have, based on their "
        "exploration trajectory. E.g. \"asked about how X works but not why the "
        "paper chose X over Y — section 4 addresses this directly.\" Not generic "
        "coverage suggestions. Empty array if none.\n"
        "- **biggest_takeaway**: 1-2 sentences. The single most important insight.\n\n"
        "Keep it tight. Less is better. Ground every insight in the actual Q&A — "
        "if it can't be traced to a specific exchange, don't include it."
    )

    return "\n\n".join(sections)


SYNTHESIZE_SYSTEM_PROMPT = (
    "You are a research assistant. Your task is to find connections between "
    "insights the user derived from reading multiple papers. You are NOT "
    "comparing papers — you are comparing what the user learned from them "
    "through their Q&A history."
)

SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "paper_a": {"type": "string"},
                    "paper_b": {"type": "string"},
                    "relationship": {
                        "type": "string",
                        "enum": [
                            "builds_on",
                            "contradicts",
                            "shares_method",
                            "shares_finding",
                        ],
                    },
                    "insight": {
                        "type": "string",
                        "description": (
                            "1-2 sentences. Explain the connection, "
                            "grounded in the specific themes/takeaways "
                            "from the summaries."
                        ),
                    },
                },
                "required": ["paper_a", "paper_b", "relationship", "insight"],
            },
        },
        "overall_synthesis": {
            "type": "string",
            "description": (
                "1-3 sentences on the meta-insight across all papers. "
                "If no connections found, say 'No significant cross-paper "
                "connections found.'"
            ),
        },
    },
    "required": ["connections", "overall_synthesis"],
}


def build_synthesize_prompt(summaries: list[dict]) -> str:
    sections = ["## Paper Summaries"]

    for s in summaries:
        parts = [f"### Paper {s['index']}: {s['title']}"]

        for theme in s.get("themes", []):
            parts.append(f"- **{theme['name']}**: {theme['learned']} ({theme['so_what']})")

        if s.get("biggest_takeaway"):
            parts.append(f"**Biggest takeaway:** {s['biggest_takeaway']}")

        sections.append("\n".join(parts))

    sections.append("## Your task")
    sections.append(
        "Find connections between the insights the user derived from these papers. "
        "Only describe connections that genuinely exist — do not evaluate every pair. "
        "If few or no connections exist, return an empty connections array.\n\n"
        "For each connection:\n"
        "- paper_a / paper_b: the paper titles as given above\n"
        "- relationship: how they connect\n"
        "  - builds_on: insights from one extend/deepen insights from another\n"
        "  - contradicts: insights from one challenge/contradict insights from another\n"
        "  - shares_method: both papers use similar techniques the user explored\n"
        "  - shares_finding: both papers arrive at similar conclusions\n"
        "- insight: 1-2 sentences. Reference the actual themes/takeaways. Be specific "
        "— not \"both papers use attention\" but \"the user discovered multi-head is "
        "parameter-free in Paper A, and Paper B's efficient routing confirms this "
        "scales without cost.\"\n\n"
        "Do not invent connections. Empty connections array is a valid output.\n\n"
        "End with overall_synthesis: 1-3 sentences on the meta-insight across all "
        "papers. If no connections, say \"No significant cross-paper connections found.\""
    )

    return "\n\n".join(sections)


KNOWLEDGE_SYSTEM_PROMPT = (
    "You are a research assistant. Your task is to synthesize what a user has "
    "learned across all papers they've read in a research space. You are NOT "
    "summarizing papers — you are building a knowledge map of the user's "
    "evolving understanding, grounded in the insights they derived through "
    "Q&A with each paper."
)


KNOWLEDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "understanding": {
                        "type": "string",
                        "description": (
                            "What the user understands about this theme, "
                            "synthesized across all papers where it appeared. "
                            "Grounded in specific takeaways."
                        ),
                    },
                    "papers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Paper titles where this theme appeared.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["solid", "developing", "tentative"],
                        "description": (
                            "solid: user explored this thoroughly across "
                            "multiple papers. developing: explored in one "
                            "paper, not yet cross-referenced. tentative: "
                            "only touched on briefly."
                        ),
                    },
                },
                "required": ["name", "understanding", "papers", "confidence"],
            },
        },
        "key_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "source": {"type": "string", "description": "Paper title."},
                },
                "required": ["fact", "source"],
            },
            "description": (
                "Concrete factual learnings the user gained. Only include "
                "things the user genuinely didn't know before — not trivia "
                "or restatements of common knowledge."
            ),
        },
        "evolving_understanding": {
            "type": "string",
            "description": (
                "2-4 sentences on how the user's understanding has evolved "
                "across papers. What shifted? What deepened? What questions "
                "emerged that weren't there before? If only one paper, "
                "describe the state of understanding after engaging with it."
            ),
        },
        "overall_synthesis": {
            "type": "string",
            "description": (
                "1-2 sentences on the big picture of what this space knows. "
                "If only surface-level engagement exists across all papers, "
                "say so honestly."
            ),
        },
    },
    "required": ["themes", "key_facts", "evolving_understanding", "overall_synthesis"],
}


def build_knowledge_prompt(summaries: list[dict]) -> str:
    sections = ["## Paper Summaries"]

    for s in summaries:
        parts = [f"### {s['title']}"]

        for theme in s.get("themes", []):
            parts.append(f"- **{theme['name']}**: {theme['learned']}")
            if theme.get("surprise"):
                parts.append(f"  - Surprise: {theme['surprise']}")
            if theme.get("so_what"):
                parts.append(f"  - So what: {theme['so_what']}")

        if s.get("biggest_takeaway"):
            parts.append(f"**Biggest takeaway:** {s['biggest_takeaway']}")

        open_threads = s.get("open_threads", [])
        if open_threads:
            parts.append("**Open threads:**")
            for thread in open_threads:
                parts.append(f"  - {thread}")

        gaps = s.get("gaps", [])
        if gaps:
            parts.append("**Gaps:**")
            for gap in gaps:
                parts.append(f"  - {gap}")

        sections.append("\n".join(parts))

    sections.append("## Your task")
    sections.append(
        "Synthesize what the user has learned across all papers in this space.\n\n"
        "For each field:\n"
        "- **themes**: Group insights across papers into themes. A theme can "
        "span multiple papers (list all paper titles where it appeared). For "
        "each theme, describe the user's *current understanding* — not just "
        "what was learned, but how it fits together. Assign confidence based "
        "on depth of exploration.\n"
        "- **key_facts**: Concrete, specific facts the user gained that they "
        "likely didn't know before. Only include genuinely new information — "
        "not 'transformers use attention' (common knowledge) but 'scaled "
        "dot-product is preferred over additive because large dk values cause "
        "vanishing gradients in softmax' (specific insight from Q&A). Include "
        "the source paper.\n"
        "- **evolving_understanding**: How has the user's thinking changed "
        "across papers? What connected? What shifted? If only one paper, "
        "describe the state after engaging with it.\n"
        "- **overall_synthesis**: 1-2 sentences on the big picture.\n\n"
        "Ground everything in the actual summaries. If it can't be traced to "
        "a specific theme or takeaway, don't include it. Honesty over "
        "inflation — if engagement was shallow, say so."
    )

    return "\n\n".join(sections)


OPEN_QUESTIONS_SYSTEM_PROMPT = (
    "You are a research assistant. Your task is to curate a prioritized list of "
    "open questions and knowledge gaps from a user's reading history. These are "
    "things the user touched on but didn't fully explore, or should have asked "
    "but didn't. Your job is to deduplicate, synthesize, and prioritize them so "
    "the user knows what to revisit next."
)


OPEN_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "A clear, actionable question the user should "
                            "explore. Phrased as a question, not a statement."
                        ),
                    },
                    "type": {
                        "type": "string",
                        "enum": ["open_thread", "gap"],
                        "description": (
                            "open_thread: something the answers touched on "
                            "but the user didn't follow up. gap: something "
                            "the user didn't ask about but should have."
                        ),
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": (
                            "high: directly addresses a core concept the "
                            "user is missing or a thread central to their "
                            "exploration. medium: worth exploring but not "
                            "critical. low: tangential or niche."
                        ),
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "1-2 sentences. Why this question matters, "
                            "grounded in the specific Q&A or gap it came "
                            "from. What will the user learn by exploring it?"
                        ),
                    },
                    "papers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Paper titles where this question or gap "
                            "originated. May be multiple if the same "
                            "question emerged across papers."
                        ),
                    },
                },
                "required": ["question", "type", "priority", "context", "papers"],
            },
        },
    },
    "required": ["questions"],
}


def build_open_questions_prompt(summaries: list[dict]) -> str:
    sections = ["## Open Threads and Gaps by Paper"]

    for s in summaries:
        parts = [f"### {s['title']}"]

        open_threads = s.get("open_threads", [])
        if open_threads:
            parts.append("**Open threads (touched on but not followed up):**")
            for thread in open_threads:
                parts.append(f"  - {thread}")

        gaps = s.get("gaps", [])
        if gaps:
            parts.append("**Gaps (should have asked but didn't):**")
            for gap in gaps:
                parts.append(f"  - {gap}")

        if not open_threads and not gaps:
            parts.append("(no open threads or gaps)")

        sections.append("\n".join(parts))

    sections.append("## Your task")
    sections.append(
        "Curate a prioritized list of open questions from the threads and "
        "gaps above.\n\n"
        "For each question:\n"
        "- **question**: Rephrase as a clear, actionable question. Not "
        "'details about Figure 2' but 'How does the multi-head attention "
        "diagram in Figure 2 map to the mathematical formulation?'\n"
        "- **type**: open_thread or gap\n"
        "- **priority**: high/medium/low based on how central the missing "
        "knowledge is to the user's exploration trajectory\n"
        "- **context**: Why this matters, grounded in the specific thread "
        "or gap. What will the user gain by exploring it?\n"
        "- **papers**: Which paper(s) this came from\n\n"
        "Deduplicate: if the same question appears across multiple papers, "
        "merge into one entry with all paper titles. Synthesize: if related "
        "threads suggest a deeper question, combine them into a single, "
        "sharper question.\n\n"
        "Order questions by priority (high first). Empty questions array is "
        "valid if no meaningful open questions exist."
    )

    return "\n\n".join(sections)
