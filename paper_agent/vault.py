from pathlib import Path

import re
import shutil

import yaml

from . import config

SPACES_DIR = "spaces"

SPACE_SUBDIRS = [
    "papers",
    "sessions",
    "summaries",
]


def get_vault_path() -> Path:
    cfg = config.load_config()
    return Path(cfg.get("vault_path", str(config.DEFAULT_VAULT_PATH))).expanduser()


def get_spaces_dir() -> Path:
    vault = get_vault_path()
    return vault / SPACES_DIR


def list_spaces() -> list[str]:
    spaces_dir = get_spaces_dir()
    if not spaces_dir.exists():
        return []
    return sorted(
        d.name for d in spaces_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def create_space(name: str) -> Path:
    cfg = config.ensure_config_exists()
    vault_path = get_vault_path()
    space_path = vault_path / SPACES_DIR / name

    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / config.CONFIG_DIR).mkdir(parents=True, exist_ok=True)

    space_path.mkdir(parents=True, exist_ok=True)
    for subdir in SPACE_SUBDIRS:
        (space_path / subdir).mkdir(exist_ok=True)

    return space_path


def init_vault_and_space(space_name: str) -> Path:
    cfg = config.ensure_config_exists()
    space_path = create_space(space_name)
    return space_path


def list_papers(space: str) -> list[str]:
    vault_path = get_vault_path()
    papers_dir = vault_path / SPACES_DIR / space / "papers"
    if not papers_dir.exists():
        return []
    return sorted(
        d.name for d in papers_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def get_paper_path(space: str, paper_id: str) -> Path:
    vault_path = get_vault_path()
    return vault_path / SPACES_DIR / space / "papers" / paper_id


def get_paper_metadata(space: str, paper_id: str) -> dict:
    metadata_path = get_paper_path(space, paper_id) / "metadata.yaml"
    if not metadata_path.exists():
        return {}
    with open(metadata_path) as f:
        return yaml.safe_load(f) or {}


def purge_space(space: str) -> dict:
    space_path = get_spaces_dir() / space
    if not space_path.exists():
        raise FileNotFoundError(f"Space '{space}' does not exist.")

    purged = {}
    for subdir in SPACE_SUBDIRS:
        subdir_path = space_path / subdir
        if not subdir_path.exists():
            continue
        items = list(subdir_path.iterdir())
        purged[subdir] = len(items)
        for item in items:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    index_path = space_path / "index.md"
    if index_path.exists():
        index_path.unlink()

    return purged


def delete_space(space: str) -> None:
    space_path = get_spaces_dir() / space
    if not space_path.exists():
        raise FileNotFoundError(f"Space '{space}' does not exist.")

    for subdir in SPACE_SUBDIRS:
        subdir_path = space_path / subdir
        if subdir_path.exists():
            remaining = list(subdir_path.iterdir())
            if remaining:
                names = ", ".join(item.name for item in remaining[:5])
                raise RuntimeError(
                    f"Space '{space}' is not empty. "
                    f"{subdir}/ contains {len(remaining)} items: {names}... "
                    f"Run 'paper-agent purge --space {space}' first."
                )

    shutil.rmtree(space_path)


def regenerate_index(space: str) -> None:
    space_path = get_spaces_dir() / space
    if not space_path.exists():
        return

    parts = [f"# {space}", ""]

    # Papers
    papers = list_papers(space)
    if papers:
        parts.append("## Papers")
        for paper_id in papers:
            meta = get_paper_metadata(space, paper_id)
            title = meta.get("title", paper_id)
            page_count = meta.get("page_count")
            paper_type = meta.get("type", "")

            label = title
            suffix_parts = []
            if page_count:
                suffix_parts.append(f"{page_count} pages")
            if paper_type:
                suffix_parts.append(paper_type)
            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""

            summary_path = space_path / "papers" / paper_id / "summary.md"
            if summary_path.exists():
                parts.append(
                    f"- [{title}](papers/{paper_id}/paper.md) — "
                    f"[summary](papers/{paper_id}/summary.md){suffix}"
                )
            else:
                parts.append(f"- [{title}](papers/{paper_id}/paper.md){suffix}")
        parts.append("")

    # Sessions
    sessions_dir = space_path / "sessions"
    if sessions_dir.exists():
        session_files = sorted(sessions_dir.glob("*.md"), key=lambda p: p.name, reverse=True)
        if session_files:
            parts.append("## Sessions")
            for sf in session_files:
                slug, date = _parse_session_filename(sf.name)
                qa_count = _count_questions(sf)
                date_display = date if date else sf.stem
                qa_label = f"Q{qa_count}" if qa_count else ""
                meta = f" — {date_display} ({qa_label})" if qa_label else f" — {date_display}"
                parts.append(f"- [{slug}](sessions/{sf.name}){meta}")
            parts.append("")

    # Knowledge artifacts
    knowledge_links = []
    knowledge_path = space_path / "knowledge.md"
    if knowledge_path.exists():
        knowledge_links.append("- [knowledge.md](knowledge.md)")
    questions_path = space_path / "open-questions.md"
    if questions_path.exists():
        knowledge_links.append("- [open-questions.md](open-questions.md)")
    insights_path = space_path / "summaries" / "cross-paper-insights.md"
    if insights_path.exists():
        knowledge_links.append("- [cross-paper-insights.md](summaries/cross-paper-insights.md)")
    if knowledge_links:
        parts.append("## Knowledge")
        parts.extend(knowledge_links)
        parts.append("")

    index_path = space_path / "index.md"
    index_path.write_text("\n".join(parts))


def _parse_session_filename(filename: str) -> tuple[str, str]:
    m = re.match(r"^(.+)-(\d{8})\.md$", filename)
    if m:
        slug = m.group(1)
        date_str = m.group(2)
        date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return slug, date_iso
    return "", ""


def _count_questions(filepath: Path) -> int:
    if not filepath.exists():
        return 0
    content = filepath.read_text()
    return len(re.findall(r"^### Q\d+", content, re.MULTILINE))
