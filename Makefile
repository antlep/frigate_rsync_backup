.PHONY: build run dev stop logs shell lint test init

# ---- Docker --------------------------------------------------------------- #

build:
	docker compose build

run:
	docker compose up -d

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
		echo "✓ Created config/config.yaml – edit it before running 'make run'"; \
	else \
		echo "config/config.yaml already exists, skipping."; \
	fi
	@if [ ! -f config/rclone.conf ]; then \
		echo "⚠  config/rclone.conf not found."; \
		echo "   Copy your existing rclone.conf to ./config/rclone.conf"; \
	fi

# ---- Dev helpers ---------------------------------------------------------- #

lint:
	ruff check src/ && mypy src/ --ignore-missing-imports

test:
	pytest tests/ -v
