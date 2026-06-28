.PHONY: install playground run test

install:
	uv sync

playground:
	agents-cli playground --port 18081 --host 127.0.0.1 --no-reload_agents

run:
	uv run python -m app.fast_api_app

test:
	uv run pytest
