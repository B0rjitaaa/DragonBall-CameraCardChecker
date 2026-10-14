# data/

Montado en los contenedores como `/app/data` (solo lectura). - `cartas_dbs.json`: catálogo exportado de DragonBall-EnhancedAPI (formato Bandai TCG+).
- `card_images/`: caché de imágenes oficiales (`make images`), ignorada por git.

`make catalog` importa el JSON, descarga las imágenes y calcula los fingerprints.
