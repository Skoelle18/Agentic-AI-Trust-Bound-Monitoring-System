from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature


@dataclass(frozen=True)
class Keypair:
    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey


def _key_dir() -> str:
    return os.getenv("KEY_DIR", "/config/keys")


def _paths() -> tuple[str, str]:
    d = _key_dir()
    return (os.path.join(d, "private.pem"), os.path.join(d, "public.pem"))


def load_or_generate() -> Keypair:
    priv_path, pub_path = _paths()
    os.makedirs(os.path.dirname(priv_path), exist_ok=True)

    if os.path.exists(priv_path) and os.path.exists(pub_path):
        with open(priv_path, "rb") as f:
            private = serialization.load_pem_private_key(f.read(), password=None)
        with open(pub_path, "rb") as f:
            public = serialization.load_pem_public_key(f.read())
        return Keypair(private_key=private, public_key=public)

    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()

    priv_bytes = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(priv_path, "wb") as f:
        f.write(priv_bytes)
    with open(pub_path, "wb") as f:
        f.write(pub_bytes)

    return Keypair(private_key=private, public_key=public)


def sign_event_hash(private_key: ec.EllipticCurvePrivateKey, event_hash_hex: str) -> str:
    sig = private_key.sign(event_hash_hex.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(sig)
    return f"{r:x}.{s:x}"


def verify_signature(public_key: ec.EllipticCurvePublicKey, event_hash_hex: str, signature: str) -> bool:
    try:
        r_hex, s_hex = signature.split(".", 1)
        r = int(r_hex, 16)
        s = int(s_hex, 16)
        der = encode_dss_signature(r, s)
        public_key.verify(der, event_hash_hex.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False

