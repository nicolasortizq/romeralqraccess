import hashlib
import secrets
import string


def generate_code() -> str:
    """
    Generate a QR code for a ticket.

    Returns a string with prefix 'VR1' followed by 22 random uppercase
    letters and digits. Format: VR1[A-Z0-9]{22}
    """
    charset = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(charset) for _ in range(22))
    return "VR1" + random_part


def hash_code(code: str) -> str:
    """
    Hash a QR code using SHA-256.

    Args:
        code: The QR code string to hash.

    Returns:
        The SHA-256 hex digest of the code.
    """
    return hashlib.sha256(code.encode()).hexdigest()
