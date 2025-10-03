#!/bin/sh
set -eu

CERT_DIR=/etc/nginx/certs
CERT_FILE="$CERT_DIR/dev.crt"
KEY_FILE="$CERT_DIR/dev.key"

if [ "${GENERATE_DEV_CERT:-0}" = "0" ]; then
    exit 0
fi

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    exit 0
fi

mkdir -p "$CERT_DIR"
openssl req -x509 -nodes -newkey rsa:2048 \
    -subj "/CN=localhost" \
    -days "${DEV_CERT_DAYS:-365}" \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE"
