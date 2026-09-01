import uvicorn

DEFAULT_PORT = 8765


def run(port: int = DEFAULT_PORT, reload: bool = False):
    print(f"paper-agent running on http://localhost:{port}")
    uvicorn.run(
        "paper_agent.api.server:app",
        host="127.0.0.1",
        port=port,
        reload=reload,
        log_level="info",
    )
