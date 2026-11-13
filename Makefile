.PHONY: install dev frontend test eval up down lint sample bench

install:
	pip install -e ".[dev]"

install-all:
	pip install -e ".[dev,ml,ocr,frontend]"

dev:
	uvicorn automind.api.main:app --reload --port 8000

frontend:
	streamlit run frontend/app.py

test:
	pytest

eval:
	python -m automind.evaluation.run_eval --output docs/results.md

sample:
	python scripts/ingest_sample.py

bench:
	python scripts/benchmark.py

lint:
	ruff check src tests scripts

up:
	docker compose up --build

down:
	docker compose down
