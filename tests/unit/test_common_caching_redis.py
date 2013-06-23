# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Tests the Cache and CacheMethod decorators'''
import time
import unittest2 as unittest

try:
    import fakeredis
    SKIP = False
    REASON = ""
except ImportError:
    SKIP = True
    REASON = "'fakeredis' not installed"

from checkmate.common import caching


def sample_method(*args, **kwargs):
    return list(args), kwargs


@unittest.skipIf(SKIP, REASON)
class TestRedisFunctionality(unittest.TestCase):
    '''Test that Redis operates as we expect it to'''
    def setUp(self):
        self.redis = fakeredis.FakeRedis()

    def test_contains(self):
        timestamp = time.time()
        self.redis['A'] = (timestamp)
        self.assertIn('A', self.redis)

    def test_stores_ints(self):
        self.redis['A'] = 10
        self.assertEqual(self.redis['A'], 10)

    def test_stores_strings(self):
        self.redis['A'] = 'B'
        self.assertEqual(self.redis['A'], 'B')

    def test_stores_lists(self):
        self.redis['A'] = [1, 2, 'A', {}]
        self.assertEqual(self.redis['A'], [1, 2, 'A', {}])

    def test_stores_dicts(self):
        self.redis['A'] = {"A": 1, "B": {}}
        self.assertEqual(self.redis['A'], {"A": 1, "B": {}})


@unittest.skipIf(SKIP, REASON)
class TestRedisCache(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis()

    def test_redis_store(self):
        store = {}
        cache = caching.Cache(store=store, backing_store=self.redis)
        fxn = cache(sample_method)
        args, kwargs = fxn(1, x='2')
        key = cache.get_hash(1, x='2')
        self.assertIn(key, self.redis)
        self.assertEqual(self.redis[key], (args, kwargs))

    def test_shared_caching(self):

        def increment():
            '''For testing'''
            increment.calls += 1
            return increment.calls

        def increment2():
            '''For testing'''
            return 0

        # No caching
        increment.calls = 0
        fxn = increment
        result1 = fxn()
        self.assertEqual(result1, 1)
        result2 = fxn()
        self.assertEqual(result2, 2)

        # With caching
        cache = caching.Cache(backing_store=self.redis)
        increment.calls = 0
        fxn = cache(increment)
        result1 = fxn()
        self.assertEqual(result1, 1)
        result2 = fxn()
        self.assertEqual(result2, 1)  # not incremented

        # With shared caching
        cache2 = caching.Cache(backing_store=self.redis)
        fxn = cache2(increment2)
        result1 = fxn()
        self.assertEqual(result1, 1)  # not incremented (shared cache)

        # Shared cache should populate local cache
        key = cache2.get_hash()
        self.assertIn(key, cache2._store)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
