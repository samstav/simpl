from passlib.hash import sha512_crypt


def HashSHA512(value, salt=None):
    if not salt:
        return sha512_crypt.encrypt(value)
    return sha512_crypt.encrypt(value, salt=salt)
