"""Formato de cartas de Bandai TCG+ (el de `cartas_dbs.json` de DragonBall-EnhancedAPI).

Cada registro es el detalle de una carta tal y como lo devuelve la API:

    {"id": 4, "card_number": "BT1-001", "card_name": "Champa", "card_text": "...",
     "image_url": "https://files.bandai-tcg-plus.com/card_image/DB-EN/BT1/BT1-001.png",
     "card_set": "Booster Pack ～GALACTIC BATTLE～ [DBS-B01]",
     "card_config": [{"config_name": "Type", "value": "LEADER"}, ...],
     "backcard_card_name": "...", "backcard_image_url": "...", "backcard_card_config": [...],
     "regulations": [{"id": 1, "title": "Constructed"}, ...]}
"""

import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_SET_CODE_RE = re.compile(r"^([A-Z]+\d*)-")

# card_config -> campo de Card. El resto de entradas va a `attributes`.
_CONFIG_FIELDS = {
    "Type": "card_type",
    "Color": "color",
    "Rarity": "rarity",
    "Energy": "cost",
    "Power": "power",
}


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def config_to_dict(config) -> dict[str, str]:
    """[{"config_name": "Type", "value": "LEADER"}, ...] -> {"Type": "LEADER"} (sin vacíos)."""
    return {
        item["config_name"]: _clean(item.get("value"))
        for item in config or []
        if item.get("config_name") and _clean(item.get("value"))
    }


def normalize_card(raw: dict) -> dict | None:
    """Convierte un registro de Bandai en kwargs de `Card`. None si no es válido."""
    bandai_id = raw.get("id")
    card_number = _clean(raw.get("card_number"))
    name = _clean(raw.get("card_name"))
    if not bandai_id or not card_number or not name:
        return None

    config = config_to_dict(raw.get("card_config"))
    data = {field: config.pop(key, "") for key, field in _CONFIG_FIELDS.items()}
    # Bandai mezcla 'BATTLE' y 'Battle', 'UNISON' y 'Unison'.
    data["card_type"] = data["card_type"].upper()
    match = _SET_CODE_RE.match(card_number)

    back_config = config_to_dict(raw.get("backcard_card_config"))
    attributes = dict(config)
    if back_config.get("Power"):
        attributes["Back Power"] = back_config["Power"]
    regulations = [r["title"] for r in raw.get("regulations") or [] if r.get("title")]
    if regulations:
        attributes["Regulations"] = regulations

    data.update(
        bandai_id=int(bandai_id),
        card_number=card_number,
        name=name,
        set_code=match.group(1) if match else "",
        set_name=_clean(raw.get("card_set")),
        text=_clean(raw.get("card_text")),
        image_url=_clean(raw.get("image_url")),
        back_name=_clean(raw.get("backcard_card_name")),
        back_text=_clean(raw.get("backcard_card_text")),
        image_back_url=_clean(raw.get("backcard_image_url")),
        attributes=attributes,
    )
    return data


def extract_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    for key in ("cards", "items", "results", "data", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_items(value)
            if nested:
                return nested
    return []


def fetch_cards():
    """Recorre el endpoint paginado de Bandai y produce registros en bruto.

    PENDIENTE: la API real requiere listado + detalle por carta y tiene WAF
    (ver dbs_cards_downloader.py en DragonBallTCG - EnhancedAPI). De momento la
    fuente fiable es `import_cards data/cartas_dbs.json`.
    """
    url = settings.BANDAI_API_URL
    if not url:
        raise RuntimeError("BANDAI_API_URL no está configurado")

    page_size = settings.BANDAI_PAGE_SIZE
    offset = 0
    session = requests.Session()
    session.headers["User-Agent"] = "dbs-card-identifier/1.0"
    while True:
        params = {"limit": page_size, "offset": offset}
        if settings.BANDAI_GAME_TITLE_ID:
            params["game_title_id"] = settings.BANDAI_GAME_TITLE_ID
        response = session.get(url, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        items = extract_items(response.json())
        logger.info("Bandai: offset=%s -> %s cartas", offset, len(items))
        yield from items
        if len(items) < page_size:
            break
        offset += page_size
