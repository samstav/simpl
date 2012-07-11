from Crypto import Random
from Crypto.Hash import SHA512


def HashSHA512(value, salt=None):
    if not salt:
        salt = Random.get_random_bytes(8).encode('base64').strip()
    h = SHA512.new(salt)
    h.update(value)
    return "$6$%s$%s" % (salt, h.hexdigest())
