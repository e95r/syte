.PHONY: up down stop logs build lint format typecheck test check install-dev

up:
	DOCKER_BUILDKIT=1 docker compose up -d

stop:
	docker compose stop

down:
	docker compose down

logs:
	docker compose logs -f proxy backend worker

build:
	DOCKER_BUILDKIT=1 docker compose build

install-dev:
	python3 -m pip install --upgrade pip
	python3 -m pip install -r backend/requirements-dev.txt

format:
	ruff format backend

lint:
	ruff check backend

typecheck:
	cd backend && mypy

test:
	cd backend && pytest

check:
	ruff format --check backend
	ruff check backend
	cd backend && mypy
	cd backend && pytest
