# pylint: disable=C0103,R0201,R0904,W0212,W0613

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

"""Unit Tests for the core script provider tasks."""

import logging

import mock
import unittest


from checkmate import middleware
from checkmate.providers.core.script import tasks

LOG = logging.getLogger(__name__)


class TestScriptTasks(unittest.TestCase):
    """Class to test core.script celery tasks."""
    def test_create_resource_simulation(self):
        api = mock.Mock()
        tasks.create_resource.provider = mock.Mock(return_value=api)
        tasks.create_resource.callback = mock.Mock(return_value=None)
        context = {
            'simulation': True,
            'region': 'NOOP',
            'resource_key': '0',
        }
        context = middleware.RequestContext(**context)
        expected_result = {'instance:0': {'A': 1, 'status': 'ACTIVE'}}
        results = tasks.create_resource(
            context, 'D1', {'desired': {'A': 1}}, 'localhost', 'root')
        self.assertEqual(expected_result, results)
        tasks.create_resource.callback.assert_called_with(
            context, {'A': 1, 'status': 'ACTIVE'})


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
