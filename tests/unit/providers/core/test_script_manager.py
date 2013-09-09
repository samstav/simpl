# pylint: disable=R0904,C0103
# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#
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

"""Module for testing script.manager."""

import mock
import unittest

from checkmate import exceptions
from checkmate.providers.core.script import Manager


class TestCreateReqource(unittest.TestCase):
    """Class for testing Script.Manager."""

    def setUp(self):
        self.api = mock.MagicMock()
        self.callback = mock.MagicMock()

    def test_simulation(self):
        expected = {'instance': {'A': 1}}
        manager = Manager(api=self.api, callback=self.callback, simulate=True)
        results = manager.create_resource({}, 'D1', {'desired': {'A': 1}},
                                          'localhost', 'root')
        self.assertEqual(expected, results)

    def test_success(self):
        """Verifies method calls and results."""
        self.api.remote_execute.return_value = {
            'stdout': 'OK',
            'stderr': None,
        }
        expected = {'instance': {'A': 1}}
        manager = Manager(api=self.api, callback=self.callback)
        results = manager.create_resource({}, 'D1', {'desired': {'A': 1}},
                                          'localhost', 'root',
                                          install_script="apt get update")
        self.assertEqual(results, expected)
        self.api.remote_execute.assert_called_with('localhost',
                                                   "apt get update", 'root',
                                                   private_key=None,
                                                   password=None, timeout=60)

    def test_ssh_get_exception(self):
        """Verifies CheckmateException raised when caught SSH Exception."""
        manager = Manager(api=self.api, callback=self.callback)
        self.api.remote_execute.side_effect = Exception("Fail")
        expected = ("('Fail', 'Exception', 'There was an unexpected error "
                    "executing your deployment - Please contact support', '')")
        self.assertRaisesRegexp(exceptions.CheckmateRetriableException,
                                expected,
                                manager.create_resource, {}, 'D1',
                                {'desired': {'A': 1}}, 'localhost', 'root',
                                install_script="apt get update")


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
