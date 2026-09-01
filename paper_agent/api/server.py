import json
import logging
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paper-agent")
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .. import config, vault, context
from ..agent import PaperAgentError
from ..agent.ask import ask as run_ask
from ..agent.summarize import summarize as run_summarize
from ..agent.synthesize import synthesize as run_synthesize
from ..agent.knowledge import update_knowledge as run_knowledge
from ..agent.knowledge import update_open_questions as run_open_questions
from ..ingestion.pipeline import ingest as run_ingest
from ..session import reader as session_reader


class AskRequest(BaseModel):
    question: str
    selected_text: str = ""
    source_app: str = ""
    source_title: str = ""
    source_url: str = ""
    paper_id: str | None = None
    fresh: bool = False


class ContextUpdate(BaseModel):
    space: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    source_app: str | None = None
    paper_id: str | None = None


class IngestURLRequest(BaseModel):
    url: str


class SummarizeRequest(BaseModel):
    paper_id: str


app = FastAPI(title="paper-agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_session_filename(filename: str) -> tuple[str, str]:
    if filename.startswith("reading-"):
        return filename[len("reading-") : -len(".md")], ""
    m = re.match(r"^(.+)-(\d{8})\.md$", filename)
    if m:
        slug = m.group(1)
        date_str = m.group(2)
        date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return slug, date_iso
    return "", ""


def _verify_space(space_name: str) -> None:
    if space_name not in vault.list_spaces():
        raise HTTPException(status_code=404, detail=f"Space '{space_name}' not found")


def _verify_secret(secret: str | None) -> None:
    expected = config.get_secret_key()
    if not expected:
        raise HTTPException(status_code=503, detail="PAPER_AGENT_SECRET is not configured")
    if secret != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing secret key")


@app.get("/api/spaces")
def list_spaces_api():
    spaces = []
    for name in vault.list_spaces():
        sessions = session_reader.list_sessions(name)
        spaces.append({"name": name, "sessions": len(sessions)})
    return spaces


@app.post("/api/spaces/{space_name}/ask")
async def ask_api(space_name: str, body: AskRequest):
    _verify_space(space_name)

    log.info(
        "ASK space=%s question=%r selected_text=%r source_app=%r source_title=%r source_url=%r paper_id=%r",
        space_name, body.question, body.selected_text,
        body.source_app, body.source_title, body.source_url, body.paper_id,
    )

    llm = config.get_llm_settings()
    if not llm["api_key"]:
        raise HTTPException(status_code=503, detail=llm["key_error"])

    async def event_generator():
        try:
            async for token in run_ask(
                space=space_name,
                question=body.question,
                selected_text=body.selected_text,
                source_app=body.source_app,
                source_title=body.source_title,
                source_url=body.source_url,
                paper_id=body.paper_id,
                fresh=body.fresh,
            ):
                yield {"data": token}

            yield {"data": "[DONE]"}

            session_path = context.get_last_session_file()
            if session_path:
                yield {"data": json.dumps({"session_path": session_path})}
        except PaperAgentError as e:
            yield {"data": "[ERROR]"}
            yield {"data": json.dumps({"error": str(e)})}
        except Exception as e:
            yield {"data": "[ERROR]"}
            yield {"data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_generator())


@app.get("/api/spaces/{space_name}/sessions")
def list_sessions_api(space_name: str):
    _verify_space(space_name)
    sessions = session_reader.list_sessions(space_name)
    result = []
    for s in sessions:
        slug, date = _parse_session_filename(s["file"])
        result.append({
            "file": s["file"],
            "path": s["path"],
            "qa_count": s["qa_count"],
            "modified": s["modified"],
            "slug": slug,
            "date": date,
        })
    return result


@app.get("/api/spaces/{space_name}/sessions/{date}")
def get_session_api(space_name: str, date: str):
    _verify_space(space_name)
    compact_date = date.replace("-", "")
    pairs = session_reader.get_session_by_date(space_name, compact_date)
    if not pairs:
        raise HTTPException(
            status_code=404,
            detail=f"No session found for date '{date}' in space '{space_name}'",
        )
    return pairs


@app.get("/api/spaces/{space_name}/session-files/{filename}")
def get_session_file_api(space_name: str, filename: str):
    _verify_space(space_name)
    if "/" in filename or ".." in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    pairs = session_reader.get_session_by_filename(space_name, filename)
    if not pairs:
        raise HTTPException(
            status_code=404,
            detail=f"Session file '{filename}' not found in space '{space_name}'",
        )
    return pairs


@app.get("/api/context")
def get_context_api():
    src = context.get_last_source()
    return {
        "last_space": context.get_last_space(),
        "last_source_url": src.get("url", ""),
        "last_source_title": src.get("title", ""),
        "last_source_app": src.get("app", ""),
        "active_paper_id": context.get_active_paper_id(),
        "last_session_file": context.get_last_session_file(),
    }


@app.put("/api/context")
def update_context_api(body: ContextUpdate):
    context.update_context(
        space=body.space,
        source_url=body.source_url,
        source_title=body.source_title,
        source_app=body.source_app,
        paper_id=body.paper_id,
    )
    return {"status": "ok"}


@app.get("/api/spaces/{space_name}/papers")
def list_papers_api(space_name: str):
    _verify_space(space_name)
    papers = []
    for paper_id in vault.list_papers(space_name):
        meta = vault.get_paper_metadata(space_name, paper_id)
        papers.append({
            "paper_id": paper_id,
            "title": meta.get("title", ""),
            "type": meta.get("type", ""),
            "source_url": meta.get("source_url", ""),
            "ingested_at": meta.get("ingested_at", ""),
            "page_count": meta.get("page_count"),
            "conversion_method": meta.get("conversion_method", ""),
        })
    return papers


@app.post("/api/spaces/{space_name}/papers")
async def ingest_paper_api(
    space_name: str,
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    _verify_space(space_name)

    if not url and not file:
        raise HTTPException(status_code=400, detail="Provide either 'url' or 'file'")

    try:
        if url:
            log.info("INGEST space=%s url=%s", space_name, url)
            metadata = await run_ingest(space_name, url)
        else:
            suffix = Path(file.filename).suffix if file.filename else ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await file.read())
                tmp_path = tmp.name
            log.info("INGEST space=%s file=%s", space_name, file.filename)
            metadata = await run_ingest(space_name, tmp_path)
            Path(tmp_path).unlink(missing_ok=True)

        context.update_context(space=space_name, paper_id=metadata["slug"])
        return metadata
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ResolveRequest(BaseModel):
    source_url: str = ""
    selected_text: str = ""
    space: str | None = None


@app.post("/api/resolve")
def resolve_api(body: ResolveRequest):
    """Cross-space URL lookup + thread-state preview. No side effects, no LLM.

    Returns the owning space, paper, recent Q&A, and whether the next ask
    would continue the thread (same section) or start fresh — so clients
    can show the state before the user asks anything.

    No URL and no selection: assumes continuation of the last active
    paper's thread (mirrors ask()'s fallback).
    """
    from ..agent.ask import _should_continue
    from ..agent.sections import deepest, find_section
    from ..ingestion.pipeline import find_paper_anywhere

    if not body.source_url:
        if body.selected_text.strip():
            # selection but no URL: selection-only question, no paper context
            return {"found": False, "thread_state": "no_paper", "section": ""}

        active = context.get_active_paper_id()
        if not active:
            return {"found": False, "thread_state": "no_paper", "section": ""}

        owning = None
        for candidate in dict.fromkeys([body.space or "", context.get_last_space() or ""]):
            if candidate and (vault.get_paper_path(candidate, active) / "paper.md").exists():
                owning = candidate
                break
        if owning is None:
            return {"found": False, "thread_state": "no_paper", "section": ""}
        space, paper_id = owning, active
    else:
        match = find_paper_anywhere(body.source_url, prefer_space=body.space)
        if not match:
            return {"found": False, "thread_state": "new_paper", "section": ""}
        space, paper_id = match

    meta = vault.get_paper_metadata(space, paper_id)
    recent = session_reader.get_recent_qa_for_paper(space, paper_id, n=10)

    state = "fresh"
    section = ""
    if recent:
        paper_md_path = vault.get_paper_path(space, paper_id) / "paper.md"
        paper_md = paper_md_path.read_text() if paper_md_path.exists() else ""
        raw_section = find_section(paper_md, body.selected_text) if paper_md else ""
        continued = _should_continue(raw_section, recent, bool(body.selected_text.strip()))
        state = "continuing" if continued else "fresh"
        # inherit the last question's section when continuing without a match
        display = raw_section
        if continued and not display:
            display = recent[-1].get("section", "")
        section = deepest(display)

    return {
        "found": True,
        "space": space,
        "paper_id": paper_id,
        "title": meta.get("title", paper_id),
        "qa_count": len(recent),
        "recent_qa": [
            {
                "id": qa["id"],
                "question": qa["question"],
                "answer": qa["answer"],
                "section": qa.get("section", ""),
            }
            for qa in recent
        ],
        "thread_state": state,
        "section": section,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/spaces/{space_name}/summarize")
async def summarize_api(space_name: str, body: SummarizeRequest):
    _verify_space(space_name)
    llm = config.get_llm_settings()
    if not llm["api_key"]:
        raise HTTPException(status_code=503, detail=llm["key_error"])

    try:
        result = await run_summarize(space_name, body.paper_id)
    except PaperAgentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        return {"status": "skipped", "reason": "Q&A was too superficial to summarize"}

    paper_dir = vault.get_paper_path(space_name, body.paper_id)
    summary_path = paper_dir / "summary.md"
    markdown = summary_path.read_text() if summary_path.exists() else ""
    return {
        "status": "ok",
        "summary_path": str(summary_path),
        "markdown": markdown,
        "themes": len(result.get("themes", [])),
        "open_threads": len(result.get("open_threads", [])),
        "gaps": len(result.get("gaps", [])),
    }


@app.post("/api/spaces/{space_name}/synthesize")
async def synthesize_api(space_name: str):
    _verify_space(space_name)
    llm = config.get_llm_settings()
    if not llm["api_key"]:
        raise HTTPException(status_code=503, detail=llm["key_error"])

    try:
        result = await run_synthesize(space_name)
    except PaperAgentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        return {"status": "skipped", "reason": "No cross-paper connections found"}

    vault_path = vault.get_vault_path()
    insights_path = vault_path / vault.SPACES_DIR / space_name / "summaries" / "cross-paper-insights.md"
    markdown = insights_path.read_text() if insights_path.exists() else ""
    return {
        "status": "ok",
        "insights_path": str(insights_path),
        "markdown": markdown,
        "connections": len(result.get("connections", [])),
    }


@app.post("/api/spaces/{space_name}/knowledge")
async def knowledge_api(space_name: str):
    _verify_space(space_name)
    llm = config.get_llm_settings()
    if not llm["api_key"]:
        raise HTTPException(status_code=503, detail=llm["key_error"])

    try:
        result = await run_knowledge(space_name)
    except PaperAgentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    vault_path = vault.get_vault_path()
    knowledge_path = vault_path / vault.SPACES_DIR / space_name / "knowledge.md"
    markdown = knowledge_path.read_text() if knowledge_path.exists() else ""
    return {
        "status": "ok",
        "knowledge_path": str(knowledge_path),
        "markdown": markdown,
        "themes": len(result.get("themes", [])),
        "key_facts": len(result.get("key_facts", [])),
    }


@app.post("/api/spaces/{space_name}/open-questions")
async def open_questions_api(space_name: str):
    _verify_space(space_name)
    llm = config.get_llm_settings()
    if not llm["api_key"]:
        raise HTTPException(status_code=503, detail=llm["key_error"])

    try:
        result = await run_open_questions(space_name)
    except PaperAgentError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        return {"status": "skipped", "reason": "No open questions or gaps found"}

    vault_path = vault.get_vault_path()
    questions_path = vault_path / vault.SPACES_DIR / space_name / "open-questions.md"
    markdown = questions_path.read_text() if questions_path.exists() else ""
    questions = result.get("questions", [])
    return {
        "status": "ok",
        "questions_path": str(questions_path),
        "markdown": markdown,
        "questions": len(questions),
    }


@app.delete("/api/spaces/{space_name}/contents")
def purge_space_api(space_name: str, x_paper_agent_secret: str | None = Header(None)):
    _verify_space(space_name)
    _verify_secret(x_paper_agent_secret)
    try:
        purged = vault.purge_space(space_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    log.info("PURGE space=%s purged=%s", space_name, purged)
    return {"status": "ok", "purged": purged}


@app.delete("/api/spaces/{space_name}")
def delete_space_api(space_name: str, x_paper_agent_secret: str | None = Header(None)):
    _verify_space(space_name)
    _verify_secret(x_paper_agent_secret)
    try:
        vault.delete_space(space_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    log.info("DELETE space=%s", space_name)
    return {"status": "ok"}
