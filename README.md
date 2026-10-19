# DBS Card Identifier

Identificador de cartas de **Dragon Ball Super Card Game** por cámara. Todo corre en Docker, tanto en el portátil como en una Raspberry Pi 3 B+ con webcam USB.

## Servicios

| Servicio | Qué hace |
|---|---|
| `db` | PostgreSQL 16 (ajustado para 1 GB de RAM) |
| `redis` | Broker y result backend de Celery |
| `backend` | Django + DRF con Gunicorn (migra al arrancar) |
| `worker` | Celery (pool `solo` + beat embebido): identificación, fingerprints y tareas programadas |
| `frontend` | Nginx: SPA React, `/media` y proxy de `/api` y `/admin` |
| `camera` | *(profile `camera`)*: único dueño de `/dev/video0`; sirve el último frame por HTTP |

```
Navegador ─▶ frontend (Nginx :80) ─▶ backend (Gunicorn) ─▶ PostgreSQL
                                          │ encola
                                          ▼
                     camera ◀── HTTP ── worker (Celery) ◀─ Redis
```

## Arranque rápido (desarrollo)

```bash
make up            # crea .env desde .env.example y levanta todo
make test          # tests del backend (SQLite, sin red)
```

UI en `http://localhost` (o en el `HTTP_PORT` de `.env`). Admin en `/admin/`, con el usuario de `DJANGO_SUPERUSER_*`.

Sin el profile `camera`, el escáner funciona subiendo fotos y el preview responde 503.

## Cargar el catálogo

El catálogo viene de **DragonBall-EnhancedAPI** (`data/cartas_dbs.json`, formato Bandai TCG+: 8114 impresiones, 552 con reverso).

```bash
make catalog        # = make import images fingerprints
```

| Paso | Qué hace | Tiempo aprox. |
|---|---|---|
| `make import` | Crea o actualiza las cartas (clave: id de Bandai; las alt-art son cartas distintas) | segundos |
| `make images` | Descarga a `data/card_images/` las imágenes oficiales que falten (~1,3 GB, reanudable) | ~10 min |
| `make fingerprints` | Calcula pHash/dHash/ORB de cada cara desde la caché local | minutos |

`data/` está montado en los contenedores. `data/card_images/` no está en git: si la copias a la Pi, no hace falta volver a descargar las imágenes.

## Raspberry Pi 3 B+

### Instalación (una vez)

1. Instala **Raspberry Pi OS Lite 64-bit**. Todas las dependencias tienen wheels `aarch64`, así que nada se compila en la Pi.
2. Instala Docker: `curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER`.
3. Amplía el swap (al menos 1 GB) para el build del frontend: en `/etc/dphys-swapfile`, `CONF_SWAPSIZE=1024`, y después `sudo systemctl restart dphys-swapfile`.
4. Clona el repo, crea el `.env` y activa el hook de despliegue:

```bash
mkdir -p ~/Development && cd ~/Development
git clone https://github.com/B0rjitaaa/DragonBall-CameraCardChecker.git
cd DragonBall-CameraCardChecker
cp .env.example .env    # descomenta COMPOSE_PROFILES=camera y revisa DJANGO_SECRET_KEY,
                        # DJANGO_ALLOWED_HOSTS y DJANGO_CSRF_TRUSTED_ORIGINS
make hooks              # cada `git pull` en main despliega solo
make up
make catalog            # o restaura un pg_dump de cards_card + cards_cardfingerprint (más rápido)
```

### Flujo de trabajo

1. **En el Mac:** haz los cambios, `make test`, commit y `git push` a `main`.
2. **En la Pi:** `git pull`, o desde el Mac `make pi-deploy`, que hace el pull por SSH.

El hook `post-merge` ejecuta `scripts/deploy.sh`, que:
- reconstruye solo las imágenes de los directorios que han cambiado (`backend/`, `frontend/`, `camera/`). Con la caché de Docker, un cambio de código tarda segundos; si cambian `requirements.txt` o `package.json`, varios minutos.
- recrea los contenedores afectados y aplica las migraciones.
- borra las imágenes antiguas para no llenar la SD.

Para saltarse el hook puntualmente: `SKIP_DEPLOY_HOOK=1 git pull`. Para forzar una reconstrucción completa: `FORCE=1 make deploy`.

### HTTPS en la red local (cámara del móvil)

Los navegadores del móvil solo dejan usar la cámara en directo desde páginas HTTPS. Para tenerlo sin dominio ni servicios externos, el servidor crea su propia autoridad de certificación (CA):

```bash
scripts/local-https.sh 192.168.178.104 pcmint-OptiPlex-3020M.local   # IP y nombres del servidor
```

- Genera en `certs/` la CA (una sola vez) y el certificado del servidor, y reinicia el frontend: queda `https://<ip>` en el puerto `HTTPS_PORT` (443). El HTTP normal sigue funcionando.
- Sin certificados en `certs/` (Mac, Pi), Nginx arranca solo con HTTP.
- Añade las variantes `https://…` a `DJANGO_CSRF_TRUSTED_ORIGINS` en el `.env` (las necesita el admin).
- Instala la CA en cada dispositivo desde `http://<ip>/ca.crt`. En el iPhone: abrir la URL en Safari → Ajustes → **Perfil descargado** → Instalar, y después Ajustes → General → Información → **Confianza de certificados** → activar "DBS Card Identifier CA".
- La CA solo puede firmar para IPs privadas y nombres `.local`, y `certs/ca.key` no sale del servidor (está en `.gitignore`).

### Cámara

- Se puede desconectar y reconectar la webcam en caliente: el servicio reintenta cada 3 s. Mientras no hay cámara, los escaneos fallan con "La cámara no está disponible".
- Captura en 1920x1080 MJPEG (`CAMERA_*` en `.env`); la Trust QHD no ofrece 1280x720. 2K satura la CPU de la Pi 3.
- El servicio solo decodifica frames mientras alguien los pide (preview abierto o escaneo); en reposo apenas consume CPU.
- Enfoque y exposición fijos con `CAMERA_CONTROLS`, que se aplican al arrancar:

```bash
docker compose exec camera v4l2-ctl --list-ctrls      # controles disponibles
# en .env, p. ej.:
CAMERA_CONTROLS=focus_automatic_continuous=0,focus_absolute=300
docker compose up -d camera                           # aplicar
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/scans/` | Identifica: con `image` (multipart) usa la foto; sin ella, captura de la cámara. Devuelve 202 |
| `GET` | `/api/scans/{id}/` | Estado (`pending`/`processing`/`done`/`failed`), carta, confianza y candidatos |
| `GET` | `/api/scans/` | Histórico (`?needs_review=true` para las dudosas) |
| `GET` | `/api/cards/` | Búsqueda (`search`, `set_code`, `rarity`, `card_type`, `color`) |
| `GET` | `/api/cards/facets/` | Valores disponibles para los filtros |
| `GET/POST` | `/api/collection/` | Colección; un POST de una carta que ya existe suma cantidad |
| `GET` | `/api/camera/preview/` | Último frame JPEG |

## Cómo se identifica una carta

1. Se detecta el contorno de la carta (Canny y contornos), se corrige la perspectiva y se normaliza a 315×440.
2. Se calculan pHash y dHash y se comparan con todo el catálogo en memoria (numpy). También se prueba la carta girada 180°.
3. Si la distancia supera `MATCH_HASH_THRESHOLD` o el 2º candidato está muy cerca, se reordenan los `MATCH_ORB_CANDIDATES` mejores con ORB.
4. Si la confianza queda por debajo de `MATCH_MIN_CONFIDENCE`, el escaneo se marca `needs_review`.
