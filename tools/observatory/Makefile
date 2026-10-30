up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose build --no-cache
	docker compose up -d

test:
	npm test

.PHONY: up down logs rebuild test
