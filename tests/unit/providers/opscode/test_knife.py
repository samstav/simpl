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
"""Test knife.py"""
import unittest

from checkmate.providers.opscode import knife


class TestWriteDatabag(unittest.TestCase):

    def test_none_contents_simulated(self):
        results = knife.write_databag("simulateA", "prada", "lipstick", None,
                                      {'index': '0', 'hosted_on': '1'})
        self.assertEqual(results, {})

    def test_no_contents_simulated(self):
        results = knife.write_databag("simulateA", "prada", "lipstick", {},
                                      {'index': '0', 'hosted_on': '1'})
        self.assertEqual(results, {})


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    test.run_with_params()
