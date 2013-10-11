# pylint: disable=R0201,R0904
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
"""Tests for solo manager."""
import os
import shutil
import errno

import mock
import unittest

from checkmate import exceptions
from checkmate.providers.opscode.solo.manager import Manager


class TestCreateEnvironment(unittest.TestCase):
    def test_sim(self):
        expected = {
            'environment': '/var/tmp/name/',
            'kitchen': '/var/tmp/name/kitchen',
            'private_key_path': '/var/tmp/name/private.pem',
            'public_key_path': '/var/tmp/name/checkmate.pub',
        }
        results = Manager.create_environment("name", "service_name",
                                             simulation=True)
        self.assertEqual(results, expected)

    # def test_success(self):
    #     os.mkdir = mock.Mock()
    #     expected = {
    #         'environment': '/tmp/DEP_ID',
    #     }
    #     results = Manager.create_environment("DEP_ID", "kitchen", path="/tmp")
    #     self.assertEqual(results, expected)
    #     os.mkdir.assert_called_once_with("/tmp/DEP_ID", 0o770)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
