.PHONY: up down build logs migrate seed ml-test backend-test frontend-test smoke-test

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -m app.scripts.seed_demo

ml-test:
	cd ml && .venv/Scripts/python -m pytest

backend-test:
	docker compose exec backend pytest

frontend-test:
	cd frontend && npm test

smoke-test:
	docker compose exec backend python -m app.scripts.smoke_test_training
