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
from checkmate.deployments import tasks as dep_tasks

LOG = logging.getLogger(__name__)


class TestScriptTasks(unittest.TestCase):

    """Class to test core.script celery tasks."""

    @mock.patch.object(dep_tasks, 'postback')
    @mock.patch.object(tasks.create_resource, 'provider')
    def test_create_resource_simulation(self, mock_provider, mock_postback):
        api = mock.Mock()
        mock_provider.return_value = api
        mock_provider.translate_status.return_value = 'ACTIVE'
        context = {
            'simulation': True,
            'region': 'NOOP',
            'resource_key': '0',
            'deployment_id': 'DX'
        }
        context = middleware.RequestContext(**context)
        expected = {
            'resources': {
                '0': {
                    'instance': {'A': 1, 'status': 'ACTIVE'},
                    'status': 'ACTIVE'
                }
            }
        }
        results = tasks.create_resource(
            context, 'D1', {'desired-state': {'A': 1}}, 'localhost', 'root')
        self.assertEqual(expected, results)
        mock_postback.assert_called_with(context['deployment_id'], expected)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
