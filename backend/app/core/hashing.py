import hashlib
import bcrypt


def _prehash(password: str) -> bytes:
    # Pre-hash to avoid bcrypt 72-byte limit
    return hashlib.sha256(password.encode()).hexdigest().encode()

def hash_password(password: str):
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode()

def verify_password(plain_password: str, hashed_password: str):
    try:
        return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode())
    except ValueError:
        return False
