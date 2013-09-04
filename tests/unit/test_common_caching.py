# pylint: disable=R0904

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

"""Tests for caching."""
import time
import unittest

import mock

from checkmate.common import caching


def sample_method(*args, **kwargs):
    """Mock method to wrap with caching."""
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
            """Mock increment method."""
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
        def increment(unused):
            """Mock increment method."""
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
            """Mock increment method."""
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
    @mock.patch.object(caching.threading, 'Thread')
    def test_caching_reaping(self, mock_thread_class):
        def increment():
            """Mock increment method."""
            increment.counter += 1
            return increment.counter

        # With caching
        store = {((), ()): (0, 1)}  # stale cache entry
        cache = caching.Cache(max_entries=2, timeout=100, store=store)
        mock_thread = mock.Mock()
        mock_thread.setDaemon.return_value = None
        mock_thread.start.return_value = None
        mock_thread_class.return_value = mock_thread
        increment.counter = 0
        fxn = cache(increment)
        # Make it look like it's been a while since we've cleaned up
        cache.last_reaping = time.time() - cache.cleaning_schedule
        fxn()
        mock_thread_class.assert_called_once_with(target=cache.collect)
        mock_thread.setDaemon.assert_called_once_with(False)
        mock_thread.start.assert_called_once_with()


store = {}  # stale cache entry
@caching.Cache(max_entries=5, timeout=100, store=store, ignore_args=[0,1])
def example(ignore_num, unique):
    """Sample method for testing ignore_args."""
    return ignore_num


class TestCachingIgnoreArgs(unittest.TestCase):
    """Verifies methods and cache data with ignore_args set."""

    def test_ignore_args(self):
        """Verifies cache returns."""
        unique = '39285471287546'
        results1 = example(5, unique)
        results2 = example(7, unique)
        self.assertEqual(results1, 5)
        self.assertEqual(results2, 5)

@caching.Cache(store=store, ignore_kwargs=['ignore_num'])
def example2(ignore_num, unique):
    """Sample method for testing ignore_kwargs."""
    return ignore_num


class TestCachingIgnoreKwargs(unittest.TestCase):
    """Verifies cache returns on ignore_kwargs set."""

    def test_ignore_kwargs(self):
        """Verify results."""
        unique = '12897623875412'
        results1 = example2(ignore_num=3, unique=unique)
        results2 = example2(ignore_num=9, unique=unique)
        self.assertEqual(results1, 3)
        self.assertEqual(results2, 3)


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
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
