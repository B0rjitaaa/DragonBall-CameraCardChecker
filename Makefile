COMPOSE ?= docker compose
PI_COMPOSE = $(COMPOSE) --profile camera

.PHONY: env up up-pi down logs build test shell superuser sync fingerprints import images catalog deploy-pi

env:
	@test -f .env || cp .env.example .env && echo ".env listo"

up: env
	$(COMPOSE) up -d --build

up-pi: env
	$(PI_COMPOSE) up -d --build

down:
	$(PI_COMPOSE) down

logs:
	$(PI_COMPOSE) logs -f --tail=100

build: env
	$(PI_COMPOSE) build

test: env
	$(COMPOSE) run --rm --no-deps -e POSTGRES_HOST= -e CELERY_TASK_ALWAYS_EAGER=1 backend python manage.py test

shell:
	$(COMPOSE) exec backend python manage.py shell

superuser:
	$(COMPOSE) exec backend python manage.py createsuperuser

# Sincroniza el catálogo con Bandai y encola el cálculo de fingerprints.
sync:
	$(COMPOSE) exec backend python manage.py sync_cards

fingerprints:
	$(COMPOSE) exec backend python manage.py build_fingerprints

# Catálogo exportado de DragonBall-EnhancedAPI (formato Bandai TCG+).
FILE ?= data/cartas_dbs.json
import:
	$(COMPOSE) exec backend python manage.py import_cards /app/$(FILE)

# Descarga a data/card_images las imágenes oficiales que falten (reanudable).
images:
	$(COMPOSE) exec backend python manage.py download_card_images

# Todo el catálogo desde cero: importar + imágenes + fingerprints.
catalog: import images fingerprints

# --- Despliegue en la Raspberry Pi ---
# Las imágenes se construyen en este equipo (arm64, como la Pi) y se envían ya
# hechas: compilarlas en una Pi 3 con 1 GB de RAM es lentísimo.
PI ?= raspi-j4r3tz@192.168.178.83
PI_DIR ?= DragonBall-CardCameraApp
RSYNC_EXCLUDES = --exclude .env --exclude 'data/card_images/' --exclude node_modules \
	--exclude __pycache__ --exclude 'backend/media/' --exclude 'backend/db.sqlite3'

deploy-pi:
	$(PI_COMPOSE) build
	rsync -az $(RSYNC_EXCLUDES) ./ $(PI):$(PI_DIR)/
	docker save dbs-identifier-backend:latest dbs-identifier-frontend:latest dbs-identifier-camera:latest \
		| gzip -1 | ssh $(PI) 'gunzip | docker load'
	ssh $(PI) 'cd $(PI_DIR) && docker compose --profile camera up -d --no-build'
