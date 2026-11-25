from ninja.security import APIKeyHeader

from tickets.models import Terminal
from tickets.qr import hash_code as hash_key

# hash_key reuses qr.hash_code rather than duplicating it: both are a plain
# SHA-256 hex digest of an opaque string, with no algorithm-specific
# semantics tying either one to QR codes. If the two ever need different
# algorithms (e.g. a salted hash for terminal keys), split this back out
# into its own implementation.


class TerminalKeyAuth(APIKeyHeader):
    """Authenticates a gate terminal from the X-Terminal-Key header.

    Looks up the active Terminal whose stored hash matches the presented
    key's hash. Returns the Terminal instance on success, None otherwise
    (Django Ninja then responds 401).
    """

    param_name = "X-Terminal-Key"

    def authenticate(self, request, key):
        if not key:
            return None
        return Terminal.objects.filter(
            api_key_hash=hash_key(key), is_active=True
        ).first()
