import hashlib
import re

from tickets.qr import generate_code, hash_code


def test_generate_code_has_vr1_prefix_and_is_uppercase_alnum():
    code = generate_code()
    assert code.startswith("VR1")
    assert re.fullmatch(r"VR1[A-Z0-9]+", code)


def test_generate_code_is_not_predictable():
    assert generate_code() != generate_code()


def test_hash_code_is_sha256_hex():
    assert hash_code("VR1ABC") == hashlib.sha256(b"VR1ABC").hexdigest()
