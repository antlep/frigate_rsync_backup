.PHONY: build run dev stop logs shell lint test init

# ---- Docker --------------------------------------------------------------- #

build:
	docker compose build

run:
	docker compose up -d

# Dev local (Mac) : charge automatiquement docker compose.override.yml
dev:
	docker compose up

stop:
	docker compose down

logs:
	docker compose logs -f

shell:
	docker compose exec frigate-gdrive-sync bash

# ---- First-time setup ----------------------------------------------------- #

init:
	@if [ ! -f config/config.yaml ]; then \
		cp config/config.example.yaml config/config.yaml; \
		echo "✓ Created config/config.yaml – edit frigate.host_fallback and mqtt.host_fallback"; \
	else \
		echo "config/config.yaml already exists, skipping."; \
	fi
	@if [ ! -f config/rclone.conf ]; then \
		echo "⚠  config/rclone.conf not found."; \
		echo "   Copy your existing rclone.conf to ./config/rclone.conf"; \
	fi
	@if [ ! -f docker compose.override.yml ]; then \
		cp docker compose.override.yml.example docker compose.override.yml; \
		echo "✓ Created docker compose.override.yml – edit the IPs before running 'make dev'"; \
	fi

# ---- Dev helpers ---------------------------------------------------------- #

lint:
	ruff check src/ && mypy src/ --ignore-missing-imports

test:
	./scripts/test.sh

clean-db:
	docker compose exec frigate-gdrive-sync sqlite3 /data/events.db 		"DELETE FROM events WHERE status IN ('done','failed'); SELECT changes() || ' events deleted';"