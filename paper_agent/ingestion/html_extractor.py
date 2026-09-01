import httpx
import trafilatura


def extract_html(url: str = "", html: str = "") -> tuple[str, str]:
    if url and not html:
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=30)
            if resp.status_code != 200:
                return "", ""
            html = resp.text
        except httpx.HTTPError:
            return "", ""

    if not html:
        return "", ""

    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )

    if not markdown:
        return "", ""

    metadata = trafilatura.extract_metadata(html)
    title = ""
    if metadata:
        title = getattr(metadata, "title", "") or ""

    return markdown, title


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m paper_agent.ingestion.html_extractor <url>")
        sys.exit(1)

    md, title = extract_html(url=sys.argv[1])
    print(f"Title: {title}")
    print("---")
    print(md[:500] if md else "(no content extracted)")
