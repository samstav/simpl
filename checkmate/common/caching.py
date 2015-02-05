# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Function Caching Decorators.

Usage:

    from checkmate.common import caching

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
      to identify cache items uniquely

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
cache. The local n-memory cache acts as a write-thru cache.

The secondary cache is expected to be a Redis cache (uses setex)

Note: avoid using arguments that cannot be used as a hash key (ex. an object)
      or the cache key generated for the call will never match other calls (or
      worse, will match an incorrect call by pure chance)
"""

import copy
import cPickle as pickle
import hashlib
import logging
import time

from eventlet.green import threading
from redis.exceptions import ConnectionError

LOG = logging.getLogger(__name__)

# the default max allowed age of a cache entry (in seconds)
DEFAULT_TIMEOUT = 3600


# catch generic exceptions and bypass caching - pylint: disable=W0703
class Cache:

    """Cache a function."""

    def __init__(self, max_entries=1000, timeout=DEFAULT_TIMEOUT,
                 sensitive_args=None, sensitive_kwargs=None, ignore_args=None,
                 ignore_kwargs=None, salt='a_salt', store=None,
                 cache_exceptions=False, backing_store=None,
                 backing_store_key=None):
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
        self.backing_store = backing_store or {}
        self.backing_store_key = backing_store_key
        self.reaper = None
        self.last_reaping = time.time()
        self.memorized_function = None
        self.cache_exceptions = cache_exceptions

    def __call__(self, func):
        self.memorized_function = func.__name__

        def wrapped_f(*args, **kwargs):
            """The function to return in place of the cached function."""
            key, result = self.try_cache(*args, **kwargs)
            if key:
                if self.cache_exceptions and isinstance(result, Exception):
                    LOG.debug("Raising cached exception")
                    raise result
                else:
                    return result
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                if self.cache_exceptions:
                    self.cache(exc, self.get_hash(*args, **kwargs))
                raise exc
            self.cache(result, self.get_hash(*args, **kwargs))
            return result

        return wrapped_f

    def try_cache(self, *args, **kwargs):
        """Return cached value if it exists and isn't stale

        Returns key, value as tuple
        """
        key = self.get_hash(*args, **kwargs)
        if key in self._store:
            birthday, data = self._store[key]
            age = time.time() - birthday
            if age < self.max_age:
                LOG.debug("Cache hit in %s", self.memorized_function)
                return key, data
            if time.time() - self.last_reaping > self.cleaning_schedule:
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
        """Cache item to local, in-momory store."""
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
        """Generate a key used for the backing store."""
        if self.backing_store_key is None:
            return key
        else:
            return '%s.%s' % (key, self.backing_store_key)

    def get_hash(self, *args, **kwargs):
        """Calculate a secure hash."""
        if (not self.sensitive_args and not self.sensitive_kwargs and not
                self.ignore_args and not self.ignore_kwargs):
            return (args, tuple(sorted(kwargs.items())))
        clean_args = list(copy.deepcopy(args))
        clean_kwargs = copy.deepcopy(kwargs)
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
        return (tuple(clean_args), tuple(sorted(clean_kwargs.items())),
                secret_hash)

    def invalidate(self):
        "Invalidate all cache entries for this function"
        self._store.clear()

    def invalidate_one(self, *args, **kwargs):
        "Invalidate a specific cache entry"
        key = self.get_hash(*args, **kwargs)
        if key in self._store:
            del self._store[key]

    def collect(self):
        """Clean out any cache entries

        Cleans cache entries in this store that are currently older than
        allowed.
        """
        now = time.time()
        for key, entry in self._store.items():
            birthday, _ = entry
            if self.max_age > 0 and now - birthday > self.max_age:
                del self._store[key]
        self.reaper = None
        self.last_reaping = time.time()

    def start_collection(self):
        """Initizate the removal of stale cache items."""
        if self.reaper is None:
            try:
                self.reaper = threading.Thread(target=self.collect)
                self.reaper.setDaemon(False)
                LOG.debug("Reaping cache for %s", self.memorized_function)
                self.reaper.start()
            except StandardError as exc:
                print("Exception: %s" % exc)
                raise exc

    @staticmethod
    def _encode(data):
        """Encode python data into format we can restore from Redis."""
        return pickle.dumps(data, pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _decode(data):
        """Decode our python data from the Redis string."""
        return pickle.loads(data)


class CacheMethod(Cache):
    """Use this instead of @Cache with instance methods."""
    def __call__(self, func):
        self.memorized_function = func.__name__

        def wrapped_f(itself, *args, **kwargs):
            """The function to return in place of the cached function."""
            key, result = self.try_cache(*args, **kwargs)
            if key:
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
                raise
            self.cache(result, self.get_hash(*args, **kwargs))
            return result
        return wrapped_f
