.PHONY: install dev test eval eval-quick eval-no-judge build-embeddings docker-up docker-down

install:
	uv sync --extra dev

dev:
	uv run uvicorn cv_evaluator.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest tests/ -v

eval:
	uv run python -m cv_evaluator.evals.runner

eval-no-judge:
	uv run python -m cv_evaluator.evals.runner --no-judge

eval-quick:
	uv run python -m cv_evaluator.evals.runner --limit 3 --no-judge

build-embeddings:
	uv run python scripts/build_embeddings.py

docker-up:
	cd .. && docker-compose up --build

docker-down:
	cd .. && docker-compose down
