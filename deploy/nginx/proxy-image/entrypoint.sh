#!/bin/sh
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"
DAYS="${SELF_SIGNED_CERT_DAYS:-365}"
CN="${SELF_SIGNED_CERT_CN:-localhost}"

mkdir -p "$CERT_DIR"

if [ ! -s "$CERT_FILE" ] || [ ! -s "$KEY_FILE" ]; then
  echo "[proxy-entrypoint] TLS cert/key missing. Generating self-signed certificate for CN=$CN"
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days "$DAYS" \
    -subj "/CN=$CN"
else
  echo "[proxy-entrypoint] Using provided TLS certificate files."
fi

exec "$@"
