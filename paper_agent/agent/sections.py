import re

# Characters that PDF/browser extraction renders differently than pymupdf4llm output.
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u2010": "-",
    "\u2011": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
}

_PROBE_LEN = 80


def normalize(text: str) -> str:
    for char, replacement in _LIGATURES.items():
        text = text.replace(char, replacement)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Punctuation-insensitive: PDF/browser extraction rarely agrees on
    # punctuation with the converted markdown, so compare words only.
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_sections(paper_markdown: str) -> list[dict]:
    """Split paper.md into sections keyed by heading path.

    Returns a list of {"path": "3. Method > 3.2 Attention", "text": raw_body}
    in document order. Content before the first heading gets path "".
    """
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    stack: list[tuple[int, str]] = []
    sections: list[dict] = [{"path": "", "lines": []}]
    in_code_block = False

    for line in paper_markdown.split("\n"):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            sections[-1]["lines"].append(line)
            continue
        if not in_code_block:
            m = heading_re.match(line)
            if m:
                level, title = len(m.group(1)), m.group(2).strip()
                title = title.strip("*_").strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                sections.append({"path": " > ".join(t for _, t in stack), "lines": []})
                continue
        sections[-1]["lines"].append(line)

    result = []
    for s in sections:
        text = "\n".join(s["lines"]).strip()
        if text:
            result.append({"path": s["path"], "text": text})
    return result


def find_section(paper_markdown: str, selected_text: str) -> str:
    """Locate selected text within paper.md, return its heading path.

    Returns "" when no paper or no match (caller applies fallback rules).
    Tries the full selection first, then an 80-char probe from the start.
    """
    if not paper_markdown or not selected_text.strip():
        return ""

    norm_selection = normalize(selected_text)
    if not norm_selection:
        return ""

    probes = [norm_selection]
    short_probe = norm_selection[:_PROBE_LEN]
    if short_probe and short_probe != norm_selection:
        probes.append(short_probe)

    sections = parse_sections(paper_markdown)
    normalized_cache = [(s["path"], normalize(s["text"])) for s in sections]

    for probe in probes:
        for path, norm_body in normalized_cache:
            if probe in norm_body:
                return path
    return ""


def deepest(path: str) -> str:
    """'3. Method > 3.2 Attention' -> '3.2 Attention' (for display)."""
    return path.split(" > ")[-1] if path else ""
