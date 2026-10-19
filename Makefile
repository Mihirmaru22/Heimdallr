# Common local tasks. Docker targets need Docker Compose v2; the others run natively.
.PHONY: up down logs admin test lint frontend-build sites

up:            ## start the whole stack on http://localhost:8080
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker

admin:         ## make EMAIL a platform admin (prompts for a password)
	docker compose exec api python -m app.cli create-admin $(EMAIL)

test:          ## backend tests (needs Postgres with the webdata_test database, and Redis)
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run typecheck

frontend-build:
	cd frontend && npm ci && npm run build

sites:         ## serve the offline test websites on :8765
	python3 test-sites/server.py --port 8765
