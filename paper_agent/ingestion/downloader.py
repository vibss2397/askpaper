import re
import tempfile
from pathlib import Path

import httpx

ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+)(v\d+)?")


def normalize_arxiv_url(url: str) -> str:
    m = ARXIV_RE.search(url)
    if m and "/abs/" in url:
        arxiv_id = m.group(1) + (m.group(2) or "")
        return f"https://arxiv.org/pdf/{arxiv_id}"
    return url


def extract_arxiv_id(url: str) -> str | None:
    m = ARXIV_RE.search(url)
    if m:
        return m.group(1) + (m.group(2) or "")
    return None


async def download_url(url: str) -> tuple[Path, str]:
    url = normalize_arxiv_url(url)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as f:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=60)
            resp.raise_for_status()
            f.write(resp.content)
            content_type = resp.headers.get("content-type", "").lower()

    temp_path = Path(f.name)

    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return temp_path, "pdf"
    return temp_path, "html"


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m paper_agent.ingestion.downloader <url>")
        sys.exit(1)

    path, ctype = asyncio.run(download_url(sys.argv[1]))
    print(f"Downloaded to: {path}")
    print(f"Content type: {ctype}")
    print(f"File size: {path.stat().st_size} bytes")
    path.unlink(missing_ok=True)
