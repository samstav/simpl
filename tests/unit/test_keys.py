# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest

from checkmate import keys


class TestEnvironments(unittest.TestCase):
    def test_hashSHA512(self):
        """Test the get_setting function"""
        hashed_value = keys.hash_SHA512('test', salt="abcdefgh")
        self.assertEqual(hashed_value, '$6$rounds=60000$abcdefgh$deeGhChT2CWz3'
                                       'emQf1CisUjqgaxE5tJdyzF1HH3aBHy3KuwJeLj'
                                       'LRIPJtPWr4Nu2sVZ3cvdM/ZRDRT.mtBIxr0')

    def test_hashMD5(self):
        """Test the get_setting function"""
        hashed_value = keys.hash_MD5('test', salt="abcdefgh")
        self.assertEqual(hashed_value, '$1$abcdefgh$irWbblnpmw.5z7wgBnprh0')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
