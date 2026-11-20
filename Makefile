.PHONY: setup install run daemon-install daemon-uninstall daemon-log test clean

PYTHON := .venv/bin/python
UV := uv

# Create venv + install dependencies (Python managed by uv)
setup: install
	@echo "Done. Activate with: source .venv/bin/activate"

# Create venv with uv and sync dependencies from pyproject.toml/uv.lock
install:
	$(UV) venv --python 3.11
	$(UV) sync

# Run a command inside the venv without activating, e.g.: make run CMD="paper-agent --help"
run:
	$(UV) run $(CMD)

# Daemon as a LaunchAgent: the panel app starts it on launch (no RunAtLoad),
# launchd keeps it alive/restarts it on crash from then on
daemon-install:
	$(UV) run paper-agent daemon-install

daemon-uninstall:
	$(UV) run paper-agent daemon-uninstall

daemon-log:
	tail -F ~/Library/Logs/paper-agent/daemon.log

# API contract tests (fast, no network, tmp vault)
test:
	$(UV) run pytest -q

clean:
	rm -rf .venv
