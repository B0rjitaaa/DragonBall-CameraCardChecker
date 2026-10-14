COMPOSE ?= docker compose

# Raspberry Pi (para los atajos que se lanzan desde el Mac por SSH)
PI ?= raspi-j4r3tz@192.168.178.83
PI_DIR ?= Development/DragonBall-CameraCardChecker

.PHONY: env up down logs ps build test shell superuser migrate deploy hooks \
	import images fingerprints catalog sync pi-deploy pi-logs

env:
	@test -f .env || cp .env.example .env && echo ".env listo"

up: env          ## Levanta todo (en la Pi incluye la cámara si COMPOSE_PROFILES=camera)
	$(COMPOSE) up -d --build

down:            ## Para los contenedores (los datos se conservan)
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

build: env
	$(COMPOSE) build

test: env        ## Tests del backend (SQLite, sin red)
	$(COMPOSE) run --rm --no-deps -e POSTGRES_HOST= -e CELERY_TASK_ALWAYS_EAGER=1 backend python manage.py test

shell:
	$(COMPOSE) exec backend python manage.py shell

superuser:
	$(COMPOSE) exec backend python manage.py createsuperuser

migrate:         ## Aplica migraciones pendientes
	$(COMPOSE) exec backend python manage.py migrate

# --- Despliegue (en la Raspberry Pi) ---
deploy:          ## git pull + rebuild de lo que cambie + migraciones
	bash scripts/deploy.sh

hooks:           ## Activa el hook: cada `git pull` en main ejecuta scripts/deploy.sh
	git config core.hooksPath .githooks
	@echo "Hook post-merge activado en este clon."

# --- Atajos desde el Mac ---
pi-deploy:       ## Hace `git pull` en la Pi (el hook despliega). Antes: commit + push a main
	ssh $(PI) 'cd $(PI_DIR) && git pull --ff-only'

pi-logs:
	ssh $(PI) 'cd $(PI_DIR) && docker compose logs -f --tail=100'

# --- Catálogo ---
# Catálogo exportado de DragonBall-EnhancedAPI (formato Bandai TCG+).
FILE ?= data/cartas_dbs.json
import:          ## Importa el JSON de cartas (inserta o actualiza)
	$(COMPOSE) exec backend python manage.py import_cards /app/$(FILE)

images:          ## Descarga a data/card_images las imágenes oficiales que falten
	$(COMPOSE) exec backend python manage.py download_card_images

fingerprints:    ## Calcula los fingerprints pendientes
	$(COMPOSE) exec backend python manage.py build_fingerprints

catalog: import images fingerprints   ## Todo el catálogo desde cero

sync:            ## Sincroniza con Bandai (PENDIENTE: ver cards/bandai.py)
	$(COMPOSE) exec backend python manage.py sync_cards
