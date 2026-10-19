#!/usr/bin/env bash
# Copia de seguridad de las bases de datos de los proyectos (por defecto este y
# DragonBall-EnhancedAPI) y de sus volúmenes de datos (fotos de los escaneos),
# con verificación, rotación y copia opcional a otro equipo.
#
# Uso:    scripts/backup.sh          (o `make backup`; a diario lo lanza dbs-backup.timer)
# Config: variables de entorno o ~/.config/dbs-backup.env
#   BACKUP_DIR       carpeta de las copias              (~/backups/dbs)
#   BACKUP_PROJECTS  clones a respaldar, separados por espacios
#                    (~/Development/DragonBall-CameraCardChecker ~/Development/DragonBall-EnhancedAPI)
#   KEEP_DAILY       copias diarias a conservar          (7)
#   KEEP_WEEKLY      copias semanales (domingos)         (4)
#   BACKUP_REMOTE    destino rsync fuera del equipo, p. ej. usuario@192.168.178.83:  (vacío = no)
#   BACKUP_SSH_KEY   clave SSH para BACKUP_REMOTE        (~/.ssh/dbs_backup_ed25519)
#
# Restaurar: ver README ("Copias de seguridad").
set -euo pipefail

CONF="${DBS_BACKUP_CONF:-$HOME/.config/dbs-backup.env}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/dbs}"
BACKUP_PROJECTS="${BACKUP_PROJECTS:-$HOME/Development/DragonBall-CameraCardChecker $HOME/Development/DragonBall-EnhancedAPI}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
BACKUP_SSH_KEY="${BACKUP_SSH_KEY:-$HOME/.ssh/dbs_backup_ed25519}"

log() { echo "$*"; logger -t dbs-backup "$*" 2>/dev/null || true; }
env_value() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' || true; }

STAMP="$(date +%Y-%m-%d_%H%M)"
TARGET="$BACKUP_DIR/daily/$STAMP"
mkdir -p "$TARGET"
chmod 700 "$BACKUP_DIR"

for dir in $BACKUP_PROJECTS; do
    name="$(basename "$dir")"
    cd "$dir"
    user="$(env_value POSTGRES_USER)"; user="${user:-dbs}"
    db="$(env_value POSTGRES_DB)"; db="${db:-dbs}"

    # Base de datos: formato custom de pg_dump (comprimido, restaurable con pg_restore).
    docker compose exec -T db pg_dump -U "$user" -d "$db" -Fc > "$TARGET/$name.dump"
    # Verificación: el volcado se puede leer entero.
    docker compose exec -T db pg_restore -l < "$TARGET/$name.dump" > /dev/null
    log "$name: base de datos $(du -h "$TARGET/$name.dump" | cut -f1)"

    # Volúmenes de datos (p. ej. fotos de los escaneos). La BD y Redis no: la BD
    # ya va en el volcado y Redis solo tiene datos temporales.
    project="$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
    for vol in $(docker compose config --volumes); do
        case "$vol" in pgdata|redisdata) continue ;; esac
        docker run --rm -v "${project}_${vol}:/data:ro" alpine:3.20 tar czf - -C /data . > "$TARGET/$name-$vol.tgz"
        tar tzf "$TARGET/$name-$vol.tgz" > /dev/null
        log "$name: volumen $vol $(du -h "$TARGET/$name-$vol.tgz" | cut -f1)"
    done
done

# Copia semanal (domingos), con enlaces duros: no ocupa espacio extra.
if [ "$(date +%u)" = "7" ]; then
    mkdir -p "$BACKUP_DIR/weekly"
    cp -al "$TARGET" "$BACKUP_DIR/weekly/$STAMP"
fi

# Rotación
prune() {
    local keep="$1" folder="$2"
    [ -d "$folder" ] || return 0
    ls -1d "$folder"/*/ 2>/dev/null | sort | head -n "-$keep" | xargs -r rm -rf
}
prune "$KEEP_DAILY" "$BACKUP_DIR/daily"
prune "$KEEP_WEEKLY" "$BACKUP_DIR/weekly"

# Copia fuera del equipo
if [ -n "$BACKUP_REMOTE" ]; then
    rsync -aH --delete -e "ssh -i $BACKUP_SSH_KEY -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
        "$BACKUP_DIR/" "$BACKUP_REMOTE"
    log "copia remota a $BACKUP_REMOTE"
fi

log "copia completa: $TARGET ($(du -sh "$TARGET" | cut -f1))"
