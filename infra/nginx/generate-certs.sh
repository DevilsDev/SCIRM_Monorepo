#!/bin/bash
# Generate self-signed TLS certificates for development
# For production, use Let's Encrypt or your CA

CERT_DIR="$(dirname "$0")/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -subj "/C=US/ST=Dev/L=Local/O=SCIRM/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:*.scirm.local,IP:127.0.0.1"

echo "Certificates generated in $CERT_DIR"
echo "  - server.crt (certificate)"
echo "  - server.key (private key)"
