# pylint: disable=R0904,W0212

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

"""Tests for Redis caching."""
import cPickle as pickle
import time
import unittest

import mock
from redis import exceptions

try:
    import fakeredis
    SKIP = False
    REASON = ""
except ImportError:
    SKIP = True
    REASON = "'fakeredis' not installed"

from checkmate.common import caching


def sample_method(*args, **kwargs):
    """Mock method used to test caching."""
    return list(args), kwargs


@unittest.skipIf(SKIP, REASON)
class TestRedisFunctionality(unittest.TestCase):
    """Test that Redis operates as we expect it to."""
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
        value = cache._decode(self.redis[key])
        self.assertEqual(value, (args, kwargs))

    def test_shared_caching(self):

        def increment():
            """Helper method to test caching."""
            increment.calls += 1
            return increment.calls

        def increment2():
            """Helper method to test caching."""
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

    def test_shared_caching_unique(self):
        """Test that we can use extra key data to separate Redis caches."""

        def increment():
            """Helper method to test caching."""
            increment.calls += 1
            return increment.calls

        def increment2():
            """Helper method to test caching."""
            return 0

        # No caching
        increment.calls = 0
        fxn = increment
        result1 = fxn()
        self.assertEqual(result1, 1)
        result2 = fxn()
        self.assertEqual(result2, 2)

        # With caching
        cache = caching.Cache(backing_store=self.redis, backing_store_key='A')
        increment.calls = 0
        fxn = cache(increment)
        result1 = fxn()
        self.assertEqual(result1, 1)
        result2 = fxn()
        self.assertEqual(result2, 1)  # not incremented

        # With shared caching, but seperate key
        cache2 = caching.Cache(backing_store=self.redis, backing_store_key='B')
        fxn = cache2(increment2)
        result1 = fxn()
        self.assertEqual(result1, 0)  # incremented (shared cache unique)

        # Shared cache should populate local cache
        key = cache2.get_hash()
        self.assertIn(key, cache2._store)

    @mock.patch.object(caching.Cache, '_encode')
    def test_bypass_on_pickle_error(self, mock_encode):
        mock_encode.side_effect = [pickle.PickleError, pickle.PickleError]

        def increment(amount=1):
            """Helper method to test caching."""
            increment.calls += amount
            return increment.calls

        # No caching
        increment.calls = 0
        fxn = increment
        result1 = fxn(1)
        self.assertEqual(result1, 1)
        result2 = fxn(1)
        self.assertEqual(result2, 2)

        # With caching
        cache = caching.Cache(backing_store=self.redis, backing_store_key='C')
        increment.calls = 0
        fxn = cache(increment)
        result1 = fxn(1)
        self.assertEqual(result1, 1)
        result2 = fxn(1)
        self.assertEqual(result2, 1)  # still caches locally

        # Shared cache should not have populated the key
        key = cache.get_hash()
        self.assertNotIn(key, cache._store)

    def test_bypass_on_connection_error(self):
        mock_redis = mock.Mock()
        mock_redis.side_effect = [exceptions.ConnectionError,
                                  exceptions.ConnectionError]

        def increment(amount=1):
            """Helper method to test caching."""
            increment.calls += amount
            return increment.calls

        # No caching
        increment.calls = 0
        fxn = increment
        result1 = fxn(1)
        self.assertEqual(result1, 1)
        result2 = fxn(1)
        self.assertEqual(result2, 2)

        # With caching
        cache = caching.Cache(backing_store=mock_redis, backing_store_key='C')
        increment.calls = 0
        fxn = cache(increment)
        result1 = fxn(1)
        self.assertEqual(result1, 1)
        result2 = fxn(1)
        self.assertEqual(result2, 1)  # still caches locally


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
