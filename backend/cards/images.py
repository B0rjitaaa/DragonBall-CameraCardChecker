"""Caché local de imágenes oficiales de las cartas.

Las imágenes se guardan en CARD_IMAGES_DIR replicando la ruta del CDN
(`.../card_image/DB-EN/BT1/BT1-001.png` -> `DB-EN/BT1/BT1-001.png`), de modo
que se descargan una sola vez y la Pi puede recalcular fingerprints sin red.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_USER_AGENT = "dbs-card-identifier/1.0"
_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = _USER_AGENT
    return _local.session


def local_path(url: str) -> Path:
    path = urlparse(url).path
    relative = path.split("/card_image/", 1)[1] if "/card_image/" in path else path.lstrip("/")
    return Path(settings.CARD_IMAGES_DIR) / relative


def get_image(url: str) -> bytes:
    """Bytes de la imagen: desde la caché local o descargándola (y cacheándola)."""
    path = local_path(url)
    if path.exists():
        return path.read_bytes()
    return download(url)


def download(url: str) -> bytes:
    response = _session().get(url, timeout=_TIMEOUT)
    response.raise_for_status()
    path = local_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: un corte a medias no deja un PNG truncado en la caché.
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return response.content


def download_missing(urls, workers: int = 8, progress=None) -> tuple[int, int, int]:
    """Descarga las URLs que no están en caché. Devuelve (descargadas, ya_estaban, errores)."""
    urls = list(dict.fromkeys(u for u in urls if u))
    pending = [u for u in urls if not local_path(u).exists()]
    cached = len(urls) - len(pending)
    ok = errors = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download, url): url for url in pending}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                ok += 1
            except Exception as exc:  # noqa: BLE001 - una imagen rota no para el lote
                errors += 1
                logger.warning("Imagen %s falló: %s", futures[future], exc)
            if progress and (done % 250 == 0 or done == len(pending)):
                progress(done, len(pending), errors)
    return ok, cached, errors
