# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Tests the Cache and CacheMethod decorators'''

import time
import unittest

import mox

from checkmate.common import caching


def sample_method(*args, **kwargs):
    return list(args), kwargs


class TestCaching(unittest.TestCase):
    def test_init_method(self):
        self.assertIsInstance(caching.Cache({}), caching.Cache)

    def test_is_green(self):
        self.assertEqual(caching.threading.__name__,
                         'eventlet.green.threading')

    def test_decorating(self):
        fxn = caching.Cache()(sample_method)
        args, kwargs = fxn(1, x='2')
        self.assertListEqual(args, [1])
        self.assertDictEqual(kwargs, dict(x='2'))

    def test_caching(self):

        def increment():
            '''For testing'''
            increment.counter += 1
            return increment.counter

        # No caching
        increment.counter = 0
        fxn = increment
        result1 = fxn()
        self.assertEqual(result1, 1)
        result2 = fxn()
        self.assertEqual(result2, 2)

        # With caching
        cache = caching.Cache()
        increment.counter = 0
        fxn = cache(increment)
        result1 = fxn()
        self.assertEqual(result1, 1)
        result2 = fxn()
        self.assertEqual(result2, 1)  # not incremented

        # Purge Cache
        cache.invalidate()
        result3 = fxn()
        self.assertEqual(result3, 2)  # now increments

    def test_caching_limits(self):

        def increment(x):
            '''For testing'''
            increment.counter += 1
            return increment.counter

        # With caching
        cache = caching.Cache(max_entries=2)
        increment.counter = 0
        fxn = cache(increment)
        # In second round, only last two will be called. First two are cached
        results = [fxn(i) for i in range(4)] + [fxn(i) for i in range(4)]
        self.assertEqual(increment.counter, 6)
        self.assertListEqual(results, [1, 2, 3, 4, 1, 2, 5, 6])

    def test_caching_timeout(self):

        def increment():
            '''For testing'''
            increment.counter += 1
            return increment.counter

        # With caching
        cache = caching.Cache(timeout=0)
        increment.counter = 0
        fxn = cache(increment)
        results = [fxn() for _ in range(4)]
        self.assertListEqual(results, [1, 2, 3, 4])  # none cached

        cache.max_age = 100
        results = [fxn() for _ in range(4)]
        self.assertListEqual(results, [4, 4, 4, 4])  # cached


class TestHashing(unittest.TestCase):
    def setUp(self):
        self.cache = caching.Cache({})

    def test_get_hash_blank(self):
        self.assertIsNotNone(self.cache.get_hash())

        one = self.cache.get_hash()
        two = self.cache.get_hash()
        self.assertEqual(one, two)

    def test_get_hash_arg(self):
        self.assertIsNotNone(self.cache.get_hash("A"))

        one = self.cache.get_hash("A")
        two = self.cache.get_hash("A")
        self.assertEqual(one, two)

        first = self.cache.get_hash("A")
        second = self.cache.get_hash("B")
        self.assertNotEqual(first, second)

    def test_get_hash_kwarg(self):
        self.assertIsNotNone(self.cache.get_hash(x="A"))

        one = self.cache.get_hash(x="A")
        two = self.cache.get_hash(x="A")
        self.assertEqual(one, two)

        first = self.cache.get_hash(x="A")
        second = self.cache.get_hash(x="B")
        self.assertNotEqual(first, second)

    def test_get_hash_both(self):
        self.assertIsNotNone(self.cache.get_hash("A", b=4))

        one = self.cache.get_hash("A", b=4)
        two = self.cache.get_hash("A", b=4)
        self.assertEqual(one, two)

        first = self.cache.get_hash(1, x="A")
        second = self.cache.get_hash(2, x="B")
        self.assertNotEqual(first, second)


class TestCachingMocked(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_caching_reaping(self):
        def increment():
            '''For testing'''
            increment.counter += 1
            return increment.counter

        # With caching
        store = {((), ()): (0, 1)}  # stale cache entry
        cache = caching.Cache(max_entries=2, timeout=100, store=store)
        mock_thread = self.mox.CreateMockAnything()
        self.mox.StubOutWithMock(caching.threading, 'Thread')
        caching.threading.Thread(target=cache.collect).AndReturn(mock_thread)
        mock_thread.setDaemon(False).AndReturn(None)
        mock_thread.start().AndReturn(None)
        increment.counter = 0
        fxn = cache(increment)
        # Make it look like it's been a while since we've cleaned up
        cache.last_reaping = time.time() - cache.cleaning_schedule
        self.mox.ReplayAll()
        fxn()
        self.mox.VerifyAll()


class TestSecretHashing(unittest.TestCase):
    def setUp(self):
        self.cache = caching.Cache(sensitive_args=[0],
                                      sensitive_kwargs=["x"])

    def test_get_hash_blank(self):
        self.assertIsNotNone(self.cache.get_hash())

        one = self.cache.get_hash()
        two = self.cache.get_hash()
        self.assertEqual(one, two)

    def test_get_hash_arg(self):
        self.assertIsNotNone(self.cache.get_hash("A"))

        one = self.cache.get_hash("A")
        two = self.cache.get_hash("A")
        self.assertEqual(one, two)

        first = self.cache.get_hash("A")
        second = self.cache.get_hash("B")
        self.assertNotEqual(first, second)

    def test_get_hash_kwarg(self):
        self.assertIsNotNone(self.cache.get_hash(x="A"))

        one = self.cache.get_hash(x="A")
        two = self.cache.get_hash(x="A")
        self.assertEqual(one, two)

        first = self.cache.get_hash(x="A")
        second = self.cache.get_hash(x="B")
        self.assertNotEqual(first, second)

    def test_get_hash_both(self):
        self.assertIsNotNone(self.cache.get_hash("A", x=4))

        one = self.cache.get_hash("A", x=4)
        two = self.cache.get_hash("A", x=4)
        self.assertEqual(one, two)

        first = self.cache.get_hash(1, x="A")
        second = self.cache.get_hash(2, x="B")
        self.assertNotEqual(first, second)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
