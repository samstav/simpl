# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Caching module.

All Things Caching!

Function Caching Decorators and Caching Backends.

Usage:

    from checkmate.contrib import caching

    @caching.Cache
    def my_cached_function(arg, kwarg=None):
        ...
        return data

    class MyClass():
        @caching.CacheMethod
        def method(self, arg):
            ...
            return data


To specify where to store data use the 'store' kwarg:

    MY_CACHE = {}

    @caching.Cache(store=MY_CACHE)
    def my_cached_function(arg, kwarg=None):
        ...

To use a shared Redis cache also use the 'backing_store' kwarg:

    import redis
    MY_CACHE = {}

    REDIS_URL = 'redis://localhost:10000/3'

    @caching.Cache(store=MY_CACHE, backing_store=redis.from_url(REDIS_URL))
    def my_cached_function(arg, kwarg=None):
        ...

Note: to store multiple caches in one Redis database, use 'backing_store_key'
      to identify cache items uniquely. If no backing_store-key is supplied,
      one will be generated from the cached functions full, namespaced name.

Specify which arguments need to be hashed to protect them from being exposed:

    @caching.Cache(sensitive_args=[0])
    def my_cached_function(password):
        ...

    @caching.Cache(sensitive_kwargs=['encryption_key'])
    def my_cached_function(data, encryption_key=None):
        ...

Specify which arguments to ignore when generating the hash.

    @caching.Cache(ignore_args=[1,3]) or ignore_kwargs=['mutable1', 'mutable2']
    def my_cached_function(mutable1, not1, mutable2, not2):
        ...
    This prevents the mutable data from being used to gen the hash
Tune cache timeout and whether you also want exceptions cached:


    @caching.Cache(timeout=600, cache_exceptions=True)
    def my_cached_function():
        ...


Secondary cache is used to back the in-memory cache with a shared, remote
cache. The local in-memory cache acts as a write-through cache.

The secondary cache is expected to be a Redis cache (uses setex)

Note: avoid using arguments that cannot be used as a hash key (ex. an object)
      or the cache key generated for the call will never match other calls (or
      worse, will match an incorrect call by pure chance)

You can use the get_cache_backend and get_shared_cache_backend functions to get
a backing store to use with the decorators
"""
from __future__ import print_function

import copy
import cPickle as pickle
import functools
import hashlib
import inspect
import logging
import time
import urlparse

from eventlet.green import threading
import fakeredis
import redis
from redis.exceptions import ConnectionError  # noqa

from checkmate.common import statsd
from checkmate import utils

LOG = logging.getLogger(__name__)

# the default max allowed age of a cache entry (in seconds)
DEFAULT_TIMEOUT = 3600
SHARED_CACHE = {}


def funstr(fxn):
    """Return function name."""
    try:
        return inspect.getmodule(fxn).__name__, fxn.__name__
    except AttributeError:
        return '?', '?'


# catch generic exceptions and bypass caching - pylint: disable=W0703
class Cache(object):

    """Cache a function."""

    def __init__(self, max_entries=1000, timeout=DEFAULT_TIMEOUT,
                 sensitive_args=None, sensitive_kwargs=None, ignore_args=None,
                 ignore_kwargs=None, salt='a_salt', store=None,
                 cache_exceptions=False, backing_store=None,
                 backing_store_key=None):
        """Initialize cache."""
        self.max_entries = max_entries
        self.salt = salt
        self.max_age = timeout
        self.sensitive_args = sensitive_args
        self.sensitive_kwargs = sensitive_kwargs
        self.ignore_args = ignore_args
        self.ignore_kwargs = ignore_kwargs

        self.cleaning_schedule = int(timeout / 2) if timeout > 1 else 1
        self.limit_reached = False
        self._store = store or {}
        if isinstance(backing_store, DictRedis):
            self.backing_store = backing_store.client
        else:
            self.backing_store = backing_store or {}
        self.backing_store_key = backing_store_key
        self.reaper = None
        self.last_reaping = time.time()
        self.memorized_function = None
        self.cache_exceptions = cache_exceptions

    def __call__(self, func):
        """Return the wrapped function."""
        self.memorized_function = func
        if self.backing_store_key is None:
            self.backing_store_key = "%s.%s" % (func.__module__, func.__name__)

        @functools.wraps(func)
        def wrapped_f(*args, **kwargs):
            """The function to return in place of the cached function."""
            key, result = self.try_cache(*args, **kwargs)
            if key:
                if self.cache_exceptions and isinstance(result, Exception):
                    LOG.debug("Raising cached exception")
                    raise result
                else:
                    LOG.debug("Caching module hit for function: %s:%s",
                              *funstr(func))
                    return result
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                if self.cache_exceptions:
                    self.cache(exc, self.get_hash(*args, **kwargs))
                raise exc
            LOG.debug("Caching result from function: %s:%s",
                      *funstr(func))
            self.cache(result, self.get_hash(*args, **kwargs))
            return result

        wrapped_f.cache = self
        return wrapped_f

    def try_cache(self, *args, **kwargs):
        """Return cached value if it exists and isn't stale.

        Returns key, value as tuple

        """
        key = self.get_hash(*args, **kwargs)

        if key in self._store:
            birthday, data = self._store[key]
            age = time.time() - birthday
            if age < self.max_age:
                return key, data
            if (time.time() - self.last_reaping) > self.cleaning_schedule:
                self.start_collection()
        elif self.backing_store:
            try:
                value = self.backing_store[self._backing_store_key(key)]
                value = self._decode(value)
                self._cache_local(value, key)
                return key, value
            except ConnectionError as exc:
                LOG.warn("Error connecting to Redis: %s", exc)
            except KeyError:
                pass
            except Exception as exc:
                LOG.warn("Error accesing backing store: %s", exc)
        return None, None

    def cache(self, data, key):
        """Store return value in cache.

        Do not raise errors, just log and don't store the info.

        """
        try:
            self._cache_local(data, key)
        except Exception as exc:
            LOG.warn("Error caching locally: %s", exc)

        if self.backing_store:
            try:
                self._cache_backing(data, key)
            except Exception as exc:
                LOG.warn("Error caching to backing store: %s", exc)

    def _cache_local(self, data, key):
        """Cache item to local, in-memory store."""
        if self.max_entries == 0 or len(self._store) < self.max_entries:
            self._store[key] = (time.time(), data)
        elif self.limit_reached is not True:
            self.limit_reached = True
            LOG.warn("Maximum entries reached for %s", self.memorized_function)

    def _cache_backing(self, data, key):
        """Cache item to backing store (if it is configured)."""
        if self.backing_store:
            try:
                self.backing_store.setex(self._backing_store_key(key),
                                         self._encode(data), self.max_age)
            except ConnectionError as exc:
                LOG.warn("Error connecting to Redis: %s", exc)
            except Exception as exc:
                LOG.warn("Error storing value in backing store: %s", exc)

    def _backing_store_key(self, key):
        """Generate a key used for the backing store.

        Use key first since it should generate a more unique keyspace.
        """
        if self.backing_store_key is None:
            return key
        else:
            return '%s.%s' % (key, self.backing_store_key)

    def get_hash(self, *args, **kwargs):
        """Calculate a secure hash."""
        if (not self.sensitive_args and not self.sensitive_kwargs and not
                self.ignore_args and not self.ignore_kwargs):
            return utils.create_hashable((args,
                                          tuple(sorted(kwargs.items()))))
        clean_args = list(args[:])
        clean_kwargs = copy.copy(kwargs)
        secrets = []
        if self.sensitive_args:
            count = len(args)
            for index in self.sensitive_args:
                if index < count:
                    salt_str = "%s:%s" % (self.salt, str(clean_args[index]))
                    clean_args[index] = hashlib.md5(salt_str).hexdigest()
        if self.sensitive_kwargs:
            for key in self.sensitive_kwargs:
                if key in clean_kwargs:
                    value = clean_kwargs.pop(key)
                    secrets.append("%s|%s" % (key, value))
        if self.ignore_args:
            self.ignore_args = sorted(self.ignore_args, reverse=True)
            for arg in self.ignore_args:
                del clean_args[arg]
        if self.ignore_kwargs:
            for kwarg in self.ignore_kwargs:
                del clean_kwargs[kwarg]
        if secrets:
            hasher = hashlib.md5("%s:%s" % (self.salt, ':'.join(secrets)))
            secret_hash = hasher.hexdigest()
        else:
            secret_hash = None
        final_key = (tuple(clean_args), tuple(sorted(clean_kwargs.items())),
                     secret_hash)
        return utils.create_hashable(final_key)

    def invalidate(self):
        """Invalidate all cache entries for this function."""
        self._store.clear()

    def invalidate_one(self, *args, **kwargs):
        """Invalidate a specific cache entry."""
        key = self.get_hash(*args, **kwargs)
        if key in self._store:
            del self._store[key]

    def collect(self):
        """Clean out any cache entries that are older than allowed."""
        now = time.time()
        for key, entry in self._store.items():
            birthday, _ = entry
            if self.max_age > 0 and now - birthday > self.max_age:
                del self._store[key]
        after_size = utils.total_size(self._store)
        func_mod, func_name = funstr(self.memorized_function)
        statsd.gauge('local_store.%s-%s' % (func_mod, func_name), after_size)
        LOG.info("In-memory store size is %s after reaping for "
                 "function %s:%s", after_size, func_mod, func_name)
        self.reaper = None
        self.last_reaping = time.time()

    def start_collection(self):
        """Trigger the removal of stale cache items."""
        if self.reaper is None:
            try:
                self.reaper = threading.Thread(target=self.collect)
                self.reaper.setDaemon(False)
                before_size = utils.total_size(self._store)
                func_mod, func_name = funstr(self.memorized_function)
                LOG.info("In-memory store size is %s before reaping for "
                         "function %s:%s", before_size, func_mod, func_name)
                statsd.gauge('local_cache_store.%s-%s'
                             % (func_mod, func_name), before_size)
                LOG.debug("Reaping cache for %s:%s.", func_mod, func_name)
                self.reaper.start()
            except StandardError as exc:
                print("Exception: %s" % exc)
                raise

    @staticmethod
    def _encode(data):
        """Encode python data into format we can restore from Redis."""
        return encode(data)

    @staticmethod
    def _decode(data):
        """Decode our python data from the Redis string."""
        return decode(data)


def encode(data):
    """Encode python data into format we can restore from Redis."""
    return pickle.dumps(data, pickle.HIGHEST_PROTOCOL)


def decode(data):
    """Decode our python data from the Redis string."""
    return pickle.loads(data)


class CacheMethod(Cache):

    """Use this instead of @Cache with instance methods."""

    def __call__(self, func):
        """Return the wrapped method."""
        self.memorized_function = func
        if self.backing_store_key is None:
            self.backing_store_key = "%s.%s" % (func.__module__, func.__name__)

        @functools.wraps(func)
        def wrapped_f(itself, *args, **kwargs):
            """The function to return in place of the cached function."""
            key, result = self.try_cache(*args, **kwargs)
            if key:
                LOG.debug("Caching module hit for function: %s:%s",
                          *funstr(func))
                if self.cache_exceptions and isinstance(result, Exception):
                    LOG.debug("Raising cached exception")
                    raise result
                else:
                    return result
            try:
                result = func(itself, *args, **kwargs)
            except Exception as exc:
                if self.cache_exceptions:
                    self.cache(exc, self.get_hash(*args, **kwargs))
                raise exc
            LOG.debug("Caching result from function: %s:%s",
                      *funstr(func))
            self.cache(result, self.get_hash(*args, **kwargs))
            return result
        wrapped_f.cache = self
        return wrapped_f


class DictRedis(object):  # pylint: disable=R0924

    """Overrides get/set item and get() to handle pickling.

    Implements dict methods on top of Redis object to handle where Redis is not
    like a dict object (ex. pickling).
    """

    def __init__(self, client, default_timeout=None):
        """Initialize interface to redis through a dict-like object.

        :param client:              Redis client.
        :keyword default_timeout:   the default timeout for values that are
                                    set. The default is None.
        """
        self.client = client
        self.default_timeout = default_timeout

    def __setitem__(self, key, value):
        """Encode (pickle) the object before setting."""
        if self.default_timeout:
            self.client.setex(key, encode(value), self.default_timeout)
        else:
            self.client[key] = encode(value)

    def __getitem__(self, key):
        """Decode the item upon retrieval."""
        try:
            return decode(self.client[key])
        except pickle.UnpicklingError:
            self._clear(key)
            raise KeyError(key)

    def get(self, key, *args):
        """Same as dict.get()."""
        if key not in self.client and args:
            return args[0]
        else:
            try:
                return decode(self.client.get(key))
            except pickle.UnpicklingError:
                self._clear(key)
                if args:
                    return args[0]
                raise KeyError(key)

    def __contains__(self, key):
        """True if dictionary has key."""
        return key in self.client

    def _clear(self, key):
        """Remove a key from the cache.

        Don't raise an error. Use this to remove problem keys.
        """
        try:
            del self.client[key]
        except Exception:
            pass


class EncryptedDictRedis(DictRedis):  # pylint: disable=R0924

    """Overrides get/set item and get() to handle encryption and pickling.

    See DictRedis.
    """

    def __init__(self, client, passphrase, default_timeout=None):
        """Initialize interface to redis through an encrypted, dict-like object.

        :param client:              Redis client.
        :param passphrase:          secret passphrase used to encrypt &
                                    decrypt values passed in & out of redis
        :keyword default_timeout:   the default timeout for values that are
                                    set. The default is None.
        """
        super(EncryptedDictRedis, self).__init__(
            client, default_timeout=default_timeout)
        if not passphrase:
            LOG.warning("Passphrase cannot be null.")
        self.passphrase = passphrase

    def __setitem__(self, key, value):
        """Encrypt the value before setting."""
        value = utils.encrypt(encode(value), self.passphrase)
        if self.default_timeout:
            self.client.setex(key, value, self.default_timeout)
        else:
            self.client[key] = value

    def __getitem__(self, key):
        """Decrypt the item upon retrieval."""
        try:
            return decode(utils.decrypt(
                self.client[key], passphrase=self.passphrase))
        except pickle.UnpicklingError:
            self._clear(key)
            raise KeyError(key)

    def get(self, key, *args):
        """Same as dict.get()."""
        if key not in self.client and args:
            return args[0]
        else:
            try:
                return self[key]
            except KeyError:
                if args:
                    return args[0]
                raise


def get_redis_client(connection_string, verify=False):
    """Return a Redis cache object.

    :param connection_string: the url to the redis cache
    :keyword verify: make sure the cache works, else return FakeRedis
    :keyword default_timeout: the default timeout for values that are set. The
                              default is 10 minutes (600 seconds). Explicitely
                              specify None to make it permanent.
    :returns: Redis or FakeRedis instance
    """
    parsed = urlparse.urlparse(connection_string)
    if parsed.scheme == 'redis':
        if verify:
            try:
                test = redis.from_url(connection_string, socket_timeout=0.2)
                # ping test
                test.ping()
                result = redis.from_url(connection_string)
                # true test
                result.set('test', 'value', ex=1)
                LOG.info("get_cache() returning redis instance.")
            except Exception as exc:
                LOG.warn("No redis instance found at [%s], ERROR: %s | "
                         "Using fakeredis. Limitations apply.",
                         utils.hide_url_password(connection_string), exc)
                result = fakeredis.FakeStrictRedis()
        else:
            result = redis.from_url(connection_string)
    else:
        LOG.warn("Invalid redis connection string %s. "
                 "Using fakeredis. Limitations apply.",
                 utils.hide_url_password(connection_string))
        result = fakeredis.FakeStrictRedis()
    return result


def get_cache_backend(connection_string, verify=False, default_timeout=600):
    """Return a Redis cache object.

    :param connection_string: the url to the redis cache
    :keyword verify: make sure the cache works, else return FakeRedis
    :keyword default_timeout: the default timeout for values that are set. The
                              default is 10 minutes (600 seconds). Explicitly
                              specify None to make it permanent.
    :returns: Redis or FakeRedis instance wrapped in DictRedis
    """
    redisclient = get_redis_client(connection_string, verify=verify)
    return DictRedis(redisclient, default_timeout=default_timeout)


def get_encrypted_cache_backend(connection_string, passphrase, verify=False,
                                default_timeout=600):
    """Return a Redis cache object.

    :param connection_string: the url to the redis cache
    :param passphrase:  secret passphrase used to encrypt & decrypt values
                        passed in & out of redis
    :keyword verify: make sure the cache works, else return FakeRedis
    :keyword default_timeout: the default timeout for values that are set. The
                              default is 10 minutes (600 seconds). Explicitly
                              specify None to make it permanent.
    :returns: Redis or FakeRedis instance wrapped in DictRedis
    """
    redisclient = get_redis_client(connection_string, verify=verify)
    return EncryptedDictRedis(redisclient, passphrase,
                              default_timeout=default_timeout)


def get_shared_cache_backend(connection_string, default_timeout=600):
    """Return the same shared cache every time (given the same args).

    :param connection_string: the url to the redis cache
    :keyword default_timeout: the default timeout for values that are set. The
                              default is 10 minutes (600 seconds). Explicitly
                              specify None to make it permanent.
    """
    ident = hash("%s_%s" % (connection_string, default_timeout))
    plain_shared_cache = SHARED_CACHE.setdefault('plain', {})
    if ident not in plain_shared_cache:
        plain_shared_cache[ident] = get_cache_backend(
            connection_string, default_timeout=default_timeout)
    return plain_shared_cache[ident]


def get_encrypted_shared_cache_backend(connection_string, passphrase,
                                       default_timeout=600):
    """Return the same encrypted shared cache every time (given the same args).

    :param connection_string: the url to the redis cache
    :param passphrase:  secret passphrase used to encrypt & decrypt values
                        passed in & out of redis
    :keyword default_timeout: the default timeout for values that are set. The
                              default is 10 minutes (600 seconds). Explicitly
                              specify None to make it permanent.
    """
    ident = hash("%s_%s_%s"
                 % (connection_string, passphrase, default_timeout))
    encrypted_shared_cache = SHARED_CACHE.setdefault('encrypted', {})
    if ident not in encrypted_shared_cache:
        encrypted_shared_cache[ident] = get_encrypted_cache_backend(
            connection_string, passphrase, default_timeout=default_timeout)
    return encrypted_shared_cache[ident]
