from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class RSAKeys:
    private_pem: bytes
    public_pem: bytes
    kid: str


def _key_dir() -> str:
    return os.getenv("REGISTRY_KEY_DIR", "/data/keys")


def load_or_generate_rsa() -> RSAKeys:
    os.makedirs(_key_dir(), exist_ok=True)
    priv_path = os.path.join(_key_dir(), "jwt_private.pem")
    pub_path = os.path.join(_key_dir(), "jwt_public.pem")

    if os.path.exists(priv_path) and os.path.exists(pub_path):
        with open(priv_path, "rb") as f:
            priv = f.read()
        with open(pub_path, "rb") as f:
            pub = f.read()
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with open(priv_path, "wb") as f:
            f.write(priv)
        with open(pub_path, "wb") as f:
            f.write(pub)

    kid = hashlib.sha256(pub).hexdigest()[:16]
    return RSAKeys(private_pem=priv, public_pem=pub, kid=kid)


def jwk_from_public_pem(public_pem: bytes, kid: str) -> dict[str, Any]:
    pub = serialization.load_pem_public_key(public_pem)
    if not isinstance(pub, rsa.RSAPublicKey):
        raise TypeError("Expected RSA public key")
    nums = pub.public_numbers()
    n = nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")
    e = nums.e.to_bytes((nums.e.bit_length() + 7) // 8, "big")
    return {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256", "n": _b64url(n), "e": _b64url(e)}


def issue_attestation_jwt(
    *,
    private_pem: bytes,
    kid: str,
    agent_id: str,
    tool_manifest: list[str],
    tags: list[str],
    ttl_seconds: int = 3600,
) -> tuple[str, int]:
    now = int(time.time())
    exp = now + ttl_seconds
    claims = {"agent_id": agent_id, "tool_manifest": tool_manifest, "tags": tags, "iat": now, "exp": exp}
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})
    return token, exp

