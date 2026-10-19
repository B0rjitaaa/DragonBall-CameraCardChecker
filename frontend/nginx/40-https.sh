#!/bin/sh
# Activa el servidor HTTPS solo si hay certificados montados en /etc/nginx/certs.
# Sin ellos (Mac, Pi), Nginx arranca únicamente con HTTP, como siempre.
if [ -f /etc/nginx/certs/server.crt ] && [ -f /etc/nginx/certs/server.key ]; then
    cp /etc/nginx/https.conf.available /etc/nginx/conf.d/https.conf
    echo "40-https: HTTPS activado (puerto 443)"
else
    rm -f /etc/nginx/conf.d/https.conf
    echo "40-https: sin certificados en /etc/nginx/certs, solo HTTP"
fi
