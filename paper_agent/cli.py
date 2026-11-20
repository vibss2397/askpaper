import asyncio

import click

from . import config, vault, daemon


@click.group()
def cli():
    """paper-agent — interactive research paper agent."""


@cli.command()
@click.option("--space", required=True, help="Name of the space to create (e.g. ml-research)")
def init(space: str):
    """Initialize the vault and create a space."""
    cfg = config.ensure_config_exists()
    space_path = vault.init_vault_and_space(space)
    vault_path = vault.get_vault_path()
    click.echo(f"Vault initialized at {vault_path}")
    click.echo(f"Space created: {space}")
    click.echo(f"  papers/    → {space_path / 'papers'}")
    click.echo(f"  sessions/  → {space_path / 'sessions'}")
    click.echo(f"  summaries/ → {space_path / 'summaries'}")


@cli.command()
def status():
    """Show current vault path, spaces, provider/model, and API key status."""
    vault_path = vault.get_vault_path()
    spaces = vault.list_spaces()
    llm = config.get_llm_settings()

    click.echo(f"vault at {vault_path}")
    if spaces:
        click.echo(f"spaces: {', '.join(spaces)}")
    else:
        click.echo("spaces: (none)")
    click.echo(f"provider: {llm['provider']}")
    if llm["reasoning_effort"]:
        click.echo(f"model: {llm['model']} (reasoning: {llm['reasoning_effort']})")
    else:
        click.echo(f"model: {llm['model']}")
    structured = config.get_structured_llm_settings()
    if structured["model"] != llm["model"] or (
        structured["reasoning_effort"] != llm["reasoning_effort"]
    ):
        effort = structured["reasoning_effort"] or "default"
        click.echo(
            f"structured model: {structured['model']} (reasoning: {effort})"
        )
    if llm["base_url"]:
        click.echo(f"base_url: {llm['base_url']}")
    click.echo(f"API key ({llm['key_env']}): {'✓' if llm['api_key'] else '✗'}")


@cli.command()
@click.argument("question")
@click.option("--space", required=True, help="Space to use (e.g. ml-research)")
@click.option("--selected", default="", help="Selected text from the paper")
@click.option("--source-app", default="", help="Source application (e.g. Chrome, Safari)")
@click.option("--source-title", default="", help="Source title (e.g. paper title)")
@click.option("--source-url", default="", help="Source URL (e.g. arxiv link)")
@click.option("--paper", default=None, help="Paper ID to ground the answer in")
@click.option("--fresh", is_flag=True, default=False, help="Skip conversation history even if the section matches")
def ask(question: str, space: str, selected: str, source_app: str, source_title: str, source_url: str, paper: str | None, fresh: bool):
    """Ask a question about your research. Streams the answer from the configured LLM."""
    from .agent import PaperAgentError
    from .agent.ask import ask as run_ask
    from . import context

    async def _run():
        try:
            async for token in run_ask(
                space=space,
                question=question,
                selected_text=selected,
                source_app=source_app,
                source_title=source_title,
                source_url=source_url,
                paper_id=paper,
                fresh=fresh,
            ):
                if token.startswith('{"status"'):
                    import json as _json
                    try:
                        event = _json.loads(token)
                        msg = event.get("message") or event.get("status", "")
                        click.echo(f"\n[{msg}]\n", err=True)
                        continue
                    except _json.JSONDecodeError:
                        pass
                click.echo(token, nl=False)
            click.echo()
            session = context.get_last_session_file()
            if session:
                click.echo(f"Saved to {session}")
        except PaperAgentError as e:
            raise click.ClickException(str(e))

    asyncio.run(_run())


@cli.command()
@click.option("--port", default=daemon.DEFAULT_PORT, help="Port to listen on")
@click.option("--reload", is_flag=True, help="Enable auto-reload on code changes")
@click.option("--log-file", default=None, help="Also write logs to this rotated file (used by the LaunchAgent)")
def serve(port: int, reload: bool, log_file: str | None):
    """Start the paper-agent daemon. No-op if one is already running on the port."""
    daemon.run(port=port, reload=reload, log_file=log_file)


@cli.command(name="daemon-install")
@click.option("--port", default=daemon.DEFAULT_PORT, help="Port the daemon listens on")
def daemon_install(port: int):
    """Install a LaunchAgent so the daemon starts at login and restarts on crash."""
    daemon.install_launchagent(port)


@cli.command(name="daemon-uninstall")
def daemon_uninstall():
    """Remove the daemon LaunchAgent."""
    daemon.uninstall_launchagent()


@cli.command(name="daemon-log")
def daemon_log():
    """Tail the daemon's rotated log file."""
    log_file = daemon.LOG_DIR / "daemon.log"
    if not log_file.exists():
        raise click.ClickException(f"No daemon log yet at {log_file} — installed? (paper-agent daemon-install)")
    import subprocess as _sp

    click.echo(f"Tailing {log_file} (Ctrl-C to stop)")
    _sp.run(["tail", "-F", str(log_file)])


@cli.command()
@click.option("--space", required=True, help="Space to ingest into")
@click.option("--url", default=None, help="URL to download (arxiv, blog, direct PDF)")
@click.argument("pdf_path", required=False)
def ingest(space: str, url: str | None, pdf_path: str | None):
    """Ingest a paper from a URL or local PDF file. Converts to markdown and saves to the vault."""
    if not url and not pdf_path:
        raise click.ClickException("Provide either --url or a PDF file path")
    if url and pdf_path:
        raise click.ClickException("Provide either --url or a PDF file path, not both")

    from .ingestion.pipeline import ingest as run_ingest
    from . import context

    source = url or pdf_path

    async def _run():
        try:
            metadata = await run_ingest(space, source)
            click.echo(f"Ingested: {metadata.get('title', metadata['slug'])}")
            click.echo(f"  paper_id: {metadata['slug']}")
            click.echo(f"  type: {metadata.get('type', 'unknown')}")
            if metadata.get("page_count"):
                click.echo(f"  pages: {metadata['page_count']}")
            click.echo(f"  method: {metadata.get('conversion_method', 'unknown')}")
            if metadata.get("source_url"):
                click.echo(f"  source: {metadata['source_url']}")
            context.update_context(space=space, paper_id=metadata["slug"])
        except FileNotFoundError as e:
            raise click.ClickException(str(e))
        except Exception as e:
            raise click.ClickException(str(e))

    asyncio.run(_run())


@cli.command()
@click.option("--space", required=True, help="Space to purge")
@click.option("--secret", required=True, help="Secret key (PAPER_AGENT_SECRET)")
def purge(space: str, secret: str):
    """Delete all contents of a space (papers, sessions, summaries). Keeps the space itself."""
    expected = config.get_secret_key()
    if not expected:
        raise click.ClickException("PAPER_AGENT_SECRET is not configured in .env")
    if secret != expected:
        raise click.ClickException("Invalid secret key")
    try:
        result = vault.purge_space(space)
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    click.echo(f"Purged space '{space}':")
    for subdir, count in result.items():
        click.echo(f"  {subdir}/: {count} items deleted")


@cli.command()
@click.option("--space", required=True, help="Space to delete")
@click.option("--secret", required=True, help="Secret key (PAPER_AGENT_SECRET)")
def delete_space(space: str, secret: str):
    """Delete a space. The space must be empty (purge first)."""
    expected = config.get_secret_key()
    if not expected:
        raise click.ClickException("PAPER_AGENT_SECRET is not configured in .env")
    if secret != expected:
        raise click.ClickException("Invalid secret key")
    try:
        vault.delete_space(space)
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except RuntimeError as e:
        raise click.ClickException(str(e))
    click.echo(f"Space '{space}' deleted.")


@cli.command()
@click.option("--space", required=True, help="Space the paper belongs to")
@click.option("--paper", required=True, help="Paper ID to summarize")
def summarize(space: str, paper: str):
    """Distill Q&A insights for a paper into a reading summary."""
    from .agent import PaperAgentError
    from .agent.summarize import summarize as run_summarize

    async def _run():
        try:
            result = await run_summarize(space, paper)
            if result is None:
                click.echo("Q&A was too superficial — no summary generated.")
                return
            theme_count = len(result.get("themes", []))
            paper_dir = vault.get_paper_path(space, paper)
            summary_path = paper_dir / "summary.md"
            click.echo(f"Summary written to {summary_path} ({theme_count} themes)")
            if result.get("open_threads"):
                click.echo(f"  open threads: {len(result['open_threads'])}")
            if result.get("gaps"):
                click.echo(f"  gaps: {len(result['gaps'])}")
        except PaperAgentError as e:
            raise click.ClickException(str(e))

    asyncio.run(_run())


@cli.command()
@click.option("--space", required=True, help="Space to synthesize across")
def synthesize(space: str):
    """Find cross-paper connections from Q&A insight summaries."""
    from .agent import PaperAgentError
    from .agent.synthesize import synthesize as run_synthesize

    async def _run():
        try:
            result = await run_synthesize(space)
            if result is None:
                click.echo("No cross-paper connections found.")
                return
            conn_count = len(result.get("connections", []))
            vault_path = vault.get_vault_path()
            insights_path = vault_path / vault.SPACES_DIR / space / "summaries" / "cross-paper-insights.md"
            click.echo(f"Cross-paper insights written to {insights_path} ({conn_count} connections)")
            overall = result.get("overall_synthesis", "")
            if overall:
                click.echo(f"\n{overall}")
        except PaperAgentError as e:
            raise click.ClickException(str(e))

    asyncio.run(_run())


@cli.command()
@click.option("--space", required=True, help="Space to build knowledge for")
def knowledge(space: str):
    """Synthesize what you've learned across all papers in a space into a knowledge map."""
    from .agent import PaperAgentError
    from .agent.knowledge import update_knowledge as run_knowledge

    async def _run():
        try:
            result = await run_knowledge(space)
            theme_count = len(result.get("themes", []))
            fact_count = len(result.get("key_facts", []))
            vault_path = vault.get_vault_path()
            knowledge_path = vault_path / vault.SPACES_DIR / space / "knowledge.md"
            click.echo(f"Knowledge written to {knowledge_path} ({theme_count} themes, {fact_count} key facts)")
            overall = result.get("overall_synthesis", "")
            if overall:
                click.echo(f"\n{overall}")
        except PaperAgentError as e:
            raise click.ClickException(str(e))

    asyncio.run(_run())


@cli.command(name="open-questions")
@click.option("--space", required=True, help="Space to generate open questions for")
def open_questions(space: str):
    """Curate prioritized open questions and knowledge gaps from your reading history."""
    from .agent import PaperAgentError
    from .agent.knowledge import update_open_questions as run_open_questions

    async def _run():
        try:
            result = await run_open_questions(space)
            if result is None:
                click.echo("No open questions or gaps found. All threads resolved.")
                return
            questions = result.get("questions", [])
            vault_path = vault.get_vault_path()
            questions_path = vault_path / vault.SPACES_DIR / space / "open-questions.md"
            high = sum(1 for q in questions if q.get("priority") == "high")
            medium = sum(1 for q in questions if q.get("priority") == "medium")
            low = sum(1 for q in questions if q.get("priority") == "low")
            click.echo(f"Open questions written to {questions_path} ({len(questions)} questions)")
            click.echo(f"  high: {high}, medium: {medium}, low: {low}")
        except PaperAgentError as e:
            raise click.ClickException(str(e))

    asyncio.run(_run())
