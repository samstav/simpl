import crypt
from Crypto import Random


def HashSHA512(value, salt=None):
    if not salt:
        Random.atfork()
        salt = "$6$" + Random.get_random_bytes(6).encode('base64')[:-1].replace('+', '.') + "$"
    else:
        salt = "$6$" + salt + "$"
    return crypt.crypt(value, salt)
