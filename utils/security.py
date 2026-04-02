"""
Security utilities: password hashing and verification.
Uses hashlib.sha256 (built-in, no external dependencies).
"""

import hashlib
import os


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using SHA-256 with a random salt.
    Returns a string in the format: salt:hash
    """
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a plain-text password against a stored salt:hash string.
    Returns True if the password matches, False otherwise.
    """
    try:
        salt, hashed = stored_hash.split(":")
        check = hashlib.sha256((salt + password).encode()).hexdigest()
        return check == hashed
    except ValueError:
        return False
