'''
Function Caching Decorators
'''
import copy
import hashlib
import logging
import time

from eventlet.green import threading

LOG = logging.getLogger(__name__)

# the default max allowed age of a cache entry (in seconds)
DEFAULT_TIMEOUT = 3600


class Memorize:
    '''Cache a function'''

    def __init__(self, max_entries=1000, timeout=DEFAULT_TIMEOUT,
                 sensitive_args=None, sensitive_kwargs=None, salt='a_salt',
                 store=None, cache_exceptions=False):
        self.max_entries = max_entries
        self.salt = salt
        self.max_age = timeout
        self.sensitive_args = sensitive_args
        self.sensitive_kwargs = sensitive_kwargs

        self.cleaning_schedule = int(timeout / 2) if timeout > 1 else 1
        self.limit_reached = False
        self._store = store or {}
        self.reaper = None
        self.last_reaping = time.time()
        self.memorized_function = None
        self.cache_exceptions = cache_exceptions

    def __call__(self, func):
        self.memorized_function = func.__name__

        def wrapped_f(*args, **kwargs):
            '''The function to return in place of the cached function'''
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
        '''Return cached value if it exists and isn't stale'''
        key = self.get_hash(*args, **kwargs)
        if key in self._store:
            birthday, data = self._store[key]
            age = time.time() - birthday
            if age < self.max_age:
                LOG.debug("Cache hit in %s", self.memorized_function)
                return key, data
            if time.time() - self.last_reaping > self.cleaning_schedule:
                self.start_collection()

        return None, None

    def cache(self, data, key):
        '''Store return value in cache'''
        if self.max_entries == 0 or len(self._store) < self.max_entries:
            self._store[key] = (time.time(), data)
        elif self.limit_reached is not True:
            self.limit_reached = True
            LOG.warn("Maximum entries reached for %s", self.memorized_function)

    def get_hash(self, *args, **kwargs):
        '''Calculate a secure hash'''
        if not self.sensitive_args and not self.sensitive_kwargs:
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
        hasher = hashlib.md5("%s:%s" % (self.salt, ':'.join(secrets)))
        secret_hash = hasher.hexdigest()
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
        '''Clean out any cache entries in this store that are currently older
        than allowed'''
        now = time.time()
        for key, entry in self._store.items():
            birthday, _ = entry
            if self.max_age > 0 and now - birthday > self.max_age:
                del self._store[key]
        self.reaper = None
        self.last_reaping = time.time()

    def start_collection(self):
        '''Initizate the removal of stale cache items'''
        if self.reaper is None:
            self.reaper = threading.Thread(target=self.collect)
            self.reaper.setDaemon(False)
            LOG.debug("Reaping cache for %s", self.memorized_function)
            self.reaper.start()


class MemorizeMethod(Memorize):
    '''Use this instead of @Memorize with instance methods'''
    def __call__(self, func):
        self.memorized_function = func.__name__

        def wrapped_f(itself, *args, **kwargs):
            '''The function to return in place of the cached function'''
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
                raise exc
            self.cache(result, self.get_hash(*args, **kwargs))
            return result
        return wrapped_f
