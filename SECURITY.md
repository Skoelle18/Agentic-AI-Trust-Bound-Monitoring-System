# Security Notes (ATBMS)

This repository contains a security monitoring platform. Treat **keys, tokens, and audit data** as sensitive.

## Do not commit

- `config/keys/private.pem` (ECDSA signing key for audit events)
- Any RSA JWT signing private key (e.g. `jwt_private.pem` if generated/used)
- Any `.env` files (use `.env.example` only)
- `data/` (SQLite databases and audit logs)
- `node_modules/`, build outputs (`dist/`)

These are excluded by `atbms/.gitignore`.

## Key rotation guidance

### Audit ECDSA key (`config/keys/private.pem`)

Rotating this key changes signatures for newly written events. Old signatures can still be verified with the historical public key.

Recommended approach:
- Keep a copy of the **old** public key (version it in a secure location)
- Replace `config/keys/private.pem` + `config/keys/public.pem`
- Restart the `audit` service

### Registry JWT RSA keys

If you rotate the registry JWT signing key:
- All existing agent JWTs will stop verifying at the proxy once they expire (TTL is 1 hour)
- The proxy pulls JWKS from `registry /jwks.json`, so no proxy restart should be required

## Production hardening checklist (high-level)

- Put services behind TLS (gateway / ingress)
- Restrict CORS to your dashboard domain(s)
- Add authentication to dashboard + admin endpoints
- Prefer Postgres over SQLite for multi-instance deployments
- Lock down who can call `proxy /mcp` (network ACL, auth, or both)

