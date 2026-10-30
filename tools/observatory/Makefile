up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose build --no-cache
	docker compose up -d

# Dashboard, receiver and analysis suites
test:
	npm test
	cd receiver && npm test
	cd analysis && node --test --experimental-strip-types test/*.test.ts

.PHONY: up down logs rebuild test
