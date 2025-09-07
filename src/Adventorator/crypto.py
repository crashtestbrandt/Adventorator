# crypto.py

import nacl.exceptions
import nacl.signing


def verify_ed25519(public_key_hex: str, timestamp: str, body: bytes, signature_hex: str) -> bool:
    try:
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(public_key_hex))
        message = timestamp.encode() + body
        verify_key.verify(message, bytes.fromhex(signature_hex))
        return True
    except (ValueError, nacl.exceptions.BadSignatureError):
        return False
