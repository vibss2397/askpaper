import re
from datetime import datetime, timezone
from pathlib import Path

import fitz
import yaml

from ..vault import (
    SPACES_DIR,
    get_paper_metadata,
    get_vault_path,
    list_papers,
    list_spaces,
)
from .downloader import download_url, extract_arxiv_id
from .html_extractor import extract_html
from .pdf_converter import convert_pdf


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-")


def _slug_from_title(title: str, fallback: str = "") -> str:
    if title:
        slug = _slugify(title)
        if slug:
            return slug[:60]
    if fallback:
        stem = fallback.rsplit(".", 1)[0] if "." in fallback else fallback
        slug = _slugify(stem)
        if slug:
            return slug[:60]
    return "untitled"


def _count_pages(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count


async def ingest(space: str, source: str) -> dict:
    if space not in list_spaces():
        raise ValueError(f"Space '{space}' does not exist.")

    is_url = source.startswith("http://") or source.startswith("https://")
    temp_path = None
    source_url = ""
    cleanup_temp = False

    try:
        if is_url:
            source_url = source
            temp_path, content_type = await download_url(source)
            cleanup_temp = True
        else:
            local = Path(source).expanduser()
            if not local.exists():
                raise FileNotFoundError(f"File not found: {source}")
            content_type = "pdf" if local.suffix.lower() == ".pdf" else "html"
            temp_path = local

        if content_type == "pdf":
            markdown, title = convert_pdf(temp_path)
            conversion_method = "pymupdf4llm"
            page_count = _count_pages(temp_path)
        else:
            html = temp_path.read_text(errors="replace")
            markdown, title = extract_html(html=html)
            conversion_method = "trafilatura"
            page_count = None

        if not markdown or not markdown.strip():
            raise ValueError("No content could be extracted from the source.")

        fallback_name = (
            source_url.rsplit("/", 1)[-1] if source_url else Path(source).name
        )
        slug = _slug_from_title(title, fallback=fallback_name)

        vault_path = get_vault_path()
        paper_dir = vault_path / SPACES_DIR / space / "papers" / slug
        paper_dir.mkdir(parents=True, exist_ok=True)

        (paper_dir / "paper.md").write_text(markdown)

        metadata = {
            "title": title or slug,
            "source_url": source_url,
            "type": content_type,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "conversion_method": conversion_method,
        }
        if page_count is not None:
            metadata["page_count"] = page_count

        with open(paper_dir / "metadata.yaml", "w") as f:
            yaml.dump(metadata, f)

        metadata["slug"] = slug
        return metadata

    finally:
        if cleanup_temp and temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def find_paper_by_url(space: str, url: str) -> str | None:
    arxiv_id = extract_arxiv_id(url)

    for paper_id in list_papers(space):
        meta = get_paper_metadata(space, paper_id)
        stored_url = meta.get("source_url", "")
        if not stored_url:
            continue

        if arxiv_id:
            stored_arxiv_id = extract_arxiv_id(stored_url)
            if stored_arxiv_id and stored_arxiv_id == arxiv_id:
                return paper_id
        elif stored_url == url:
            return paper_id

    return None


def find_paper_anywhere(url: str, prefer_space: str | None = None) -> tuple[str, str] | None:
    """Cross-space URL lookup. Returns (space, paper_id) or None.

    If prefer_space is given and it contains a match, that wins —
    avoids a space flip when the paper exists in multiple spaces.
    """
    if prefer_space:
        paper_id = find_paper_by_url(prefer_space, url)
        if paper_id:
            return prefer_space, paper_id

    for space in list_spaces():
        paper_id = find_paper_by_url(space, url)
        if paper_id:
            return space, paper_id

    return None


if __name__ == "__main__":
    import asyncio
    import json
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m paper_agent.ingestion.pipeline <space> <url_or_path>")
        sys.exit(1)

    result = asyncio.run(ingest(sys.argv[1], sys.argv[2]))
    print(json.dumps(result, indent=2))
