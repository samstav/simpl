#!/usr/bin/env python
import logging

from Crypto.PublicKey import RSA  # pip install pycrypto
from Crypto.Hash import SHA512, MD5
from Crypto import Random

LOG = logging.getLogger(__name__)


def generate_key_pair(bits=2048):
    """Generates a private/public key pair.

    returns them as a private, public tuple of dicts. The dicts have key,
    and PEM values. The public key also has an ssh value in it"""
    Random.atfork()
    key = RSA.generate(bits)
    private_string = key.exportKey('PEM')
    public = key.publickey()
    public_string = public.exportKey('PEM')
    ssh = public.exportKey('OpenSSH')
    return (dict(key=key, PEM=private_string),
            dict(key=public, PEM=public_string, ssh=ssh))


def get_ssh_public_key(private_key):
    """Generates an ssh public key from a private key string"""
    key = RSA.importKey(private_key)
    return key.publickey().exportKey('OpenSSH')


def get_public_key(private_key):
    """Generates a PEM public key from a private key string"""
    key = RSA.importKey(private_key)
    return key.publickey().exportKey('PEM')


def hash_SHA512(value, salt=None):
    """Create random SHA512 hashed value"""
    if not salt:
        Random.atfork()
        salt = Random.get_random_bytes(8).encode('base64').strip()
    new_hash = SHA512.new(salt)
    new_hash.update(value)
    return "$6$%s$%s" % (salt, new_hash.hexdigest())


def hash_MD5(value, salt=None):
    """Create random MD5 hashed value"""
    if not salt:
        salt = Random.get_random_bytes(8).encode('base64').strip()
    new_hash = MD5.new(salt)
    new_hash.update(value)
    return "$1$%s$%s" % (salt, new_hash.hexdigest())
