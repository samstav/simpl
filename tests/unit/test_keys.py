# pylint: disable=C0103

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

"""Tests for Environments."""
import unittest

from checkmate import keys


class TestEnvironments(unittest.TestCase):
    def test_hashSHA512(self):
        hashed_value = keys.hash_SHA512('test', salt="abcdefgh")
        self.assertEqual(hashed_value, '$6$rounds=60000$abcdefgh$deeGhChT2CWz3'
                                       'emQf1CisUjqgaxE5tJdyzF1HH3aBHy3KuwJeLj'
                                       'LRIPJtPWr4Nu2sVZ3cvdM/ZRDRT.mtBIxr0')

    def test_hashMD5(self):
        hashed_value = keys.hash_MD5('test', salt="abcdefgh")
        self.assertEqual(hashed_value, '$1$abcdefgh$irWbblnpmw.5z7wgBnprh0')


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
