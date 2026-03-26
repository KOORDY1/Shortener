PYTHON := ./.venv/bin/python
RUFF := ./.venv/bin/ruff

.PHONY: lint format smoke

lint:
	$(RUFF) check app scripts alembic

format:
	$(RUFF) format app scripts alembic

smoke:
	$(PYTHON) scripts/smoke_test.py
