#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${ROOT_DIR}/config/keys" "${ROOT_DIR}/data/audit" "${ROOT_DIR}/data/registry" "${ROOT_DIR}/data/policy" "${ROOT_DIR}/data/anomaly"

if [[ ! -f "${ROOT_DIR}/config/keys/private.pem" || ! -f "${ROOT_DIR}/config/keys/public.pem" ]]; then
  echo "Generating ECDSA P-256 keypair in config/keys/"
  openssl ecparam -name prime256v1 -genkey -noout -out "${ROOT_DIR}/config/keys/private.pem"
  openssl ec -in "${ROOT_DIR}/config/keys/private.pem" -pubout -out "${ROOT_DIR}/config/keys/public.pem" >/dev/null 2>&1
fi

if [[ -d "${ROOT_DIR}/frontend" ]]; then
  echo "Installing frontend dependencies (npm install)"
  (cd "${ROOT_DIR}/frontend" && npm install)
fi

echo "Setup complete. Run:"
echo "  cd atbms && docker compose up --build"

