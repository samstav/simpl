# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232

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

import celery
import mock
import unittest

from checkmate import exceptions as cmexc
from checkmate import middleware
from checkmate.providers import base as cm_base
from checkmate.providers.rackspace import database


class TestProviderBasePlanningMixIn(unittest.TestCase):
    # Tests for generate_resource_tag
    def test_no_values_given(self):
        result = cm_base.ProviderBasePlanningMixIn.generate_resource_tag()
        self.assertEquals(
            {'RAX-CHECKMATE': 'None/None/deployments/None/resources/None'},
            result
        )

    def test_with_good_values(self):
        result = cm_base.ProviderBasePlanningMixIn.generate_resource_tag(
            base_url='http://blerp.com',
            tenant_id='T1',
            deployment_id='deba8c',
            resource_id='r0'
        )
        self.assertEquals({
            'RAX-CHECKMATE':
            'http://blerp.com/T1/deployments/deba8c/resources/r0'}, result)


class TestProviderBase(unittest.TestCase):

    def test_translate_status_success(self):
        """Test checkmate status schema entry returned."""
        class Testing(cm_base.ProviderBase):
            __status_mapping__ = {
                'ACTIVE': 'ACTIVE',
                'BUILD': 'BUILD',
                'DELETED': 'DELETED',
                'ERROR': 'ERROR',
                'PENDING_UPDATE': 'CONFIGURE',
                'PENDING_DELETE': 'DELETING',
                'SUSPENDED': 'ERROR'
            }
        results = Testing.translate_status('SUSPENDED')
        self.assertEqual('ERROR', results)

    def test_translate_status_fail(self):
        """Test checkmate status schema UNDEFINED returned."""
        class Testing(cm_base.ProviderBase):
            __status_mapping__ = {
                'ACTIVE': 'ACTIVE',
                'BUILD': 'BUILD',
                'DELETED': 'DELETED',
                'ERROR': 'ERROR',
                'PENDING_UPDATE': 'CONFIGURE',
                'PENDING_DELETE': 'DELETING',
                'SUSPENDED': 'ERROR'
            }
        results = Testing.translate_status('MISSING')
        self.assertEqual('UNDEFINED', results)


class TestProviderTask(unittest.TestCase):
    """Tests ProviderTask functionality."""

    def setUp(self):
        self._run = do_something.run
        self._retry = do_something.retry
        self._callback = do_something.callback

    def tearDown(self):
        do_something.run = self._run
        do_something.retry = self._retry
        do_something.callback = self._callback

    def test_provider_task_success(self):
        context = middleware.RequestContext(**{'region': 'ORD',
                                            'resource_key': '1',
                                            'deployment': {}})
        expected = {
            'instance:1': {
                'api1': 'test_api',
                'name': 'test',
                'api2': 'test_api',
                'status': 'BLOCKED'
            }
        }
        do_something.callback = mock.MagicMock(return_value=True)
        results = do_something(context, 'test', api='test_api')

        do_something.callback.assert_called_with(
            context, expected['instance:1'])
        self.assertEqual(results, expected)
        assert do_something.partial, 'Partial attr should be set'

    def test_provider_task_retry(self):
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}
        do_something.run = mock.Mock()
        do_something.retry = mock.MagicMock()
        do_something.run.side_effect = cmexc.CheckmateException(
            1, 2, cmexc.CAN_RESUME)

        do_something(context, 'test', api='test_api')

        do_something.retry.assert_called_with(
            exc=do_something.run.side_effect)

    def test_provider_task_invalid_context(self):
        context = 'invalid'
        try:
            do_something(context, 'test', 'api')
        except cmexc.CheckmateException as exc:
            self.assertEqual(str(exc), "Context passed into ProviderTask is "
                             "an unsupported type <type 'str'>.")

    def test_provider_task_context_region_kwargs(self):
        context = middleware.RequestContext(**{})
        do_something.run = mock.Mock()
        do_something.callback = mock.MagicMock(return_value=True)

        do_something(context, 'test', api='api', region='ORD')
        self.assertEqual(context.region, 'ORD')
        do_something.run.assert_called_with(context, 'test',
                                            api='api', region='ORD')

    @mock.patch('checkmate.deployments.tasks')
    def test_provider_task_callback(self, mocked_lib):
        context = {
            'region': 'ORD',
            'resource_key': 1,
            'deployment_id': 'DEP_ID'}

        expected_postback = {
            'resources': {
                1: {
                    'status': 'ERROR',
                    'instance': {
                        'status': 'BLOCKED',
                        'api1': 'test_api',
                        'api2': 'test_api',
                        'name': 'test'
                    }
                }
            }
        }
        mocked_lib.postback = mock.MagicMock()

        do_something(context, 'test', api='test_api')

        mocked_lib.postback.assert_called_with('DEP_ID', expected_postback)


@celery.task.task(base=cm_base.ProviderTask, provider=database.Provider)
def do_something(context, name, api, region=None):
    return {
        'api1': do_something.api,
        'name': name,
        'api2': api,
        'status': 'BLOCKED'
    }


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
