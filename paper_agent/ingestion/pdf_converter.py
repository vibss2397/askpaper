import re
from pathlib import Path

import fitz
import pymupdf4llm

_H1_RE = re.compile(r"^#\s+(.+)$")


def _extract_title_from_markdown(markdown: str) -> str:
    for line in markdown.split("\n"):
        line = line.strip()
        m = _H1_RE.match(line)
        if m:
            title = m.group(1).strip()
            title = title.replace("**", "").replace("*", "").replace("__", "").strip()
            if len(title) > 5:
                return title
    return ""


def convert_pdf(pdf_path: Path) -> tuple[str, str]:
    doc = fitz.open(str(pdf_path))

    title = ""
    metadata = doc.metadata or {}
    raw_title = metadata.get("title", "").strip()
    if raw_title and not raw_title.lower().endswith(".pdf") and "/" not in raw_title:
        title = raw_title

    doc.close()

    markdown = pymupdf4llm.to_markdown(str(pdf_path))

    if not title:
        title = _extract_title_from_markdown(markdown)

    return markdown, title


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m paper_agent.ingestion.pdf_converter <pdf_path>")
        sys.exit(1)

    md, title = convert_pdf(Path(sys.argv[1]))
    print(f"Title: {title}")
    print("---")
    print(md[:500])
