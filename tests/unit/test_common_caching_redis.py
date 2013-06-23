# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Tests the Cache and CacheMethod decorators'''
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
class TestRedisCache(unittest.TestCase):
    def test_redis_store(self):
        r = fakeredis.FakeStrictRedis()
        fxn = caching.Cache(store=r)(sample_method)
        args, kwargs = fxn(1, x='2')
        print args, kwargs


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
