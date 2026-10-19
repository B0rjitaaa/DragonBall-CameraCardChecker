#!/usr/bin/env bash
# HTTPS en la red local con una CA propia (sin dominio ni servicios externos).
#
# Uso (en el servidor):  scripts/local-https.sh 192.168.178.104 [nombre.local ...]
#
# Genera en certs/:
#   ca.key / ca.crt          CA local (se crea una vez y se reutiliza)
#   server.key / server.crt  certificado de este servidor para esas IPs/nombres
# y reinicia el frontend para activar HTTPS en el puerto 443.
#
# Después, instala ca.crt en cada dispositivo (se descarga en http://<ip>/ca.crt).
# En el iPhone: abrir esa URL en Safari → Ajustes → Perfil descargado → Instalar,
# y activarlo en Ajustes → General → Información → Confianza de certificados.
#
# La CA está limitada (name constraints) a IPs privadas y nombres .local: aunque
# alguien obtuviera ca.key, no podría suplantar webs de Internet en tus equipos.
# Aun así, ca.key no debe salir de este servidor.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
    echo "Uso: $0 <ip-o-nombre.local> [más IPs o nombres .local]" >&2
    exit 1
fi

DIR=certs
mkdir -p "$DIR"
# 755: los workers de Nginx (usuario nginx) tienen que poder leer ca.crt para
# servirlo en /ca.crt. Las claves privadas quedan en 600 (solo las lee el
# proceso maestro de Nginx, que corre como root).
chmod 755 "$DIR"

if [ ! -f "$DIR/ca.key" ]; then
    echo "→ Creando la CA local…"
    openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 3650 \
        -keyout "$DIR/ca.key" -out "$DIR/ca.crt" \
        -subj "/CN=DBS Card Identifier CA ($(hostname))" \
        -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "nameConstraints=critical,permitted;IP:192.168.0.0/255.255.0.0,permitted;IP:10.0.0.0/255.0.0.0,permitted;IP:172.16.0.0/255.240.0.0,permitted;DNS:.local,permitted;DNS:localhost" \
        2>/dev/null
    chmod 600 "$DIR/ca.key"
else
    echo "→ Reutilizando la CA existente ($DIR/ca.crt)"
fi

SAN=""
for name in "$@"; do
    if [[ "$name" =~ ^[0-9.]+$ ]]; then SAN+="IP:$name,"; else SAN+="DNS:$name,"; fi
done
SAN="${SAN%,}"

echo "→ Generando el certificado del servidor para: $SAN"
openssl req -newkey rsa:2048 -nodes -sha256 \
    -keyout "$DIR/server.key" -out "$DIR/server.csr" -subj "/CN=$1" 2>/dev/null
# iOS exige SAN, extendedKeyUsage=serverAuth y validez <= 825 días.
openssl x509 -req -sha256 -days 825 -in "$DIR/server.csr" \
    -CA "$DIR/ca.crt" -CAkey "$DIR/ca.key" -CAcreateserial -out "$DIR/server.crt" \
    -extfile <(printf '%s\n' \
        "subjectAltName=$SAN" \
        "basicConstraints=critical,CA:FALSE" \
        "keyUsage=critical,digitalSignature,keyEncipherment" \
        "extendedKeyUsage=serverAuth") 2>/dev/null
rm -f "$DIR/server.csr"
chmod 600 "$DIR/server.key"
chmod 644 "$DIR/ca.crt" "$DIR/server.crt"

openssl verify -CAfile "$DIR/ca.crt" "$DIR/server.crt" >/dev/null && echo "→ Certificado verificado con la CA"

if command -v docker >/dev/null 2>&1 && docker compose ps --services 2>/dev/null | grep -qx frontend; then
    echo "→ Reiniciando el frontend para activar HTTPS…"
    docker compose up -d --force-recreate frontend >/dev/null
fi

cat <<MSG

✔ HTTPS listo: https://$1
  Instala la CA en cada dispositivo desde http://$1/ca.crt
  (iPhone: Safari → Instalar perfil → Ajustes → General → Información →
   Confianza de certificados → activar "DBS Card Identifier CA").
MSG
