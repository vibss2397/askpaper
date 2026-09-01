import re
from pathlib import Path

from ..vault import get_vault_path, SPACES_DIR, list_spaces
from .writer import reading_session_path


def _parse_session_file(filepath: Path) -> list[dict]:
    qa_pairs = []
    if not filepath.exists():
        return qa_pairs

    content = filepath.read_text()

    q_blocks = re.split(r"(?=^### Q\d+$)", content, flags=re.MULTILINE)

    for block in q_blocks:
        block = block.strip()
        if not block:
            continue

        q_match = re.match(r"^### (Q\d+)$", block, re.MULTILINE)
        if not q_match:
            continue
        q_id = q_match.group(1)

        question = ""
        answer = ""
        context = ""
        source = ""
        paper_id = ""
        section = ""

        q_m = re.search(r"\*\*Q:\*\*\s*(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
        if q_m:
            question = q_m.group(1).strip()

        paper_m = re.search(r"\*\*Paper:\*\*\s*(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
        if paper_m:
            paper_id = paper_m.group(1).strip()

        section_m = re.search(r"\*\*Section:\*\*\s*(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
        if section_m:
            section = section_m.group(1).strip()

        ctx_m = re.search(r"\*\*Context:\*\*\s*\n>\s*(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
        if ctx_m:
            context = ctx_m.group(1).strip()

        src_m = re.search(r"\*\*Source:\*\*\s*(.+?)(?=\n\*\*|\n###|\Z)", block, re.DOTALL)
        if src_m:
            source = src_m.group(1).strip()

        a_m = re.search(r"\*\*A:\*\*\s*(.+)", block, re.DOTALL)
        if a_m:
            answer = a_m.group(1).strip()

        qa_pairs.append({
            "id": q_id,
            "question": question,
            "answer": answer,
            "context": context,
            "source": source,
            "paper_id": paper_id,
            "section": section,
            "file": str(filepath),
        })

    return qa_pairs


def get_history(space: str, n: int = 5) -> list[dict]:
    if space not in list_spaces():
        return []

    vault_path = get_vault_path()
    session_dir = vault_path / SPACES_DIR / space / "sessions"

    if not session_dir.exists():
        return []

    session_files = sorted(
        session_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    all_pairs = []
    for sf in session_files:
        pairs = _parse_session_file(sf)
        all_pairs.extend(pairs)
        if len(all_pairs) >= n:
            break

    return all_pairs[:n]


def get_session_by_date(space: str, date_str: str) -> list[dict]:
    if space not in list_spaces():
        return []

    vault_path = get_vault_path()
    session_dir = vault_path / SPACES_DIR / space / "sessions"

    if not session_dir.exists():
        return []

    for sf in session_dir.glob(f"*-{date_str}.md"):
        return _parse_session_file(sf)

    return []


def list_sessions(space: str) -> list[dict]:
    if space not in list_spaces():
        return []

    vault_path = get_vault_path()
    session_dir = vault_path / SPACES_DIR / space / "sessions"

    if not session_dir.exists():
        return []

    sessions = []
    for sf in sorted(session_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        pairs = _parse_session_file(sf)
        sessions.append({
            "file": sf.name,
            "path": str(sf),
            "qa_count": len(pairs),
            "modified": sf.stat().st_mtime,
        })

    return sessions


def get_qa_by_paper(space: str, paper_id: str) -> list[dict]:
    if space not in list_spaces():
        return []

    vault_path = get_vault_path()
    session_dir = vault_path / SPACES_DIR / space / "sessions"

    if not session_dir.exists():
        return []

    all_pairs = []
    for sf in sorted(session_dir.glob("*.md"), key=lambda p: p.stat().st_mtime):
        pairs = _parse_session_file(sf)
        all_pairs.extend(p for p in pairs if p.get("paper_id") == paper_id)

    return all_pairs


def get_session_by_filename(space: str, filename: str) -> list[dict]:
    if space not in list_spaces():
        return []
    vault_path = get_vault_path()
    return _parse_session_file(vault_path / SPACES_DIR / space / "sessions" / filename)


def get_recent_qa_for_paper(space: str, paper_id: str, n: int = 5) -> list[dict]:
    """Last N Q&A entries for a paper. Prefers the reading-session file,
    falls back to scanning all session files (legacy scattered entries)."""
    reading = reading_session_path(space, paper_id)
    if reading.exists():
        pairs = _parse_session_file(reading)
        if pairs:
            return pairs[-n:]

    return get_qa_by_paper(space, paper_id)[-n:]
