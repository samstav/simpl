# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate import keys


class TestEnvironments(unittest.TestCase):
    def test_hashSHA512(self):
        """Test the get_setting function"""
        hashed_value = keys.hash_SHA512('test', salt="abcdef")
        self.assertEqual(hashed_value, '$6$abcdef$4bf7fed2ef99ba9306d90239d423'
                                       'ba85e4a4732293497cbcd8927a2c405e96f18f'
                                       'b454b5204afdf4e1b2591df883216b9117b8a6'
                                       '3010300414bc1abbb92c6641')

    def test_hashMD5(self):
        """Test the get_setting function"""
        hashed_value = keys.hash_MD5('test', salt="abcdef")
        self.assertEqual(hashed_value, '$1$abcdef$307d25203d209e1f7747885dc45c'
                                       '9b65')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import os
    import sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
