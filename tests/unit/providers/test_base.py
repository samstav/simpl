# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest

import mock

from celery.task import task

from checkmate.exceptions import CheckmateResumableException
from checkmate.providers.base import (
    ProviderBasePlanningMixIn,
    ProviderBase,
    ProviderTask,
)
from checkmate.providers.rackspace import database


class TestProviderBasePlanningMixIn(unittest.TestCase):
    # Tests for generate_resource_tag
    def test_no_values_given(self):
        result = ProviderBasePlanningMixIn.generate_resource_tag()
        self.assertEquals(
            {'RAX-CHECKMATE': 'None/None/deployments/None/resources/None'},
            result
        )

    def test_with_good_values(self):
        result = ProviderBasePlanningMixIn.generate_resource_tag(
            base_url='http://blerp.com',
            tenant_id='T1',
            deployment_id='deba8c',
            resource_id='r0'
        )
        self.assertEquals(
                {'RAX-CHECKMATE':
                    'http://blerp.com/T1/deployments/deba8c/resources/r0'},
            result
        )


class TestProviderBase(unittest.TestCase):

    def test_translate_status_success(self):
        ''' Test checkmate status schema entry returned '''
        class Testing(ProviderBase):
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
        ''' Test checkmate status schema UNDEFINED returned '''
        class Testing(ProviderBase):
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
    '''Tests ProviderTask functionality.'''

    def setUp(self):
        self._run = do_something.run
        self._retry = do_something.retry
        self._callback = do_something.callback

    def tearDown(self):
        do_something.run = self._run
        do_something.retry = self._retry
        do_something.callback = self._callback
        
    def test_provider_task_success(self):
        '''Tests success run.'''
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}
        expected = {
            'api1': 'test_api',
            'name': 'test',
            'api2': 'test_api',
            'status': 'BLOCKED'
        }
        do_something.callback = mock.MagicMock(return_value=True)
        results = do_something(context, 'test', api='test_api')

        do_something.callback.assert_called_with(context, expected)
        self.assertEqual(results, expected)
        assert do_something.partial, 'Partial attr should be set'

    def test_provider_task_retry(self):
        '''Tests retry is called.'''
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}
        do_something.run = mock.Mock()
        do_something.retry = mock.MagicMock()
        do_something.run.side_effect = CheckmateResumableException(1, 2, 3)
        
        do_something(context, 'test', api='test_api')

        do_something.retry.assert_called_with(
            exc=do_something.run.side_effect)

    @mock.patch('checkmate.deployments.tasks')
    def test_provider_task_callback(self, mocked_lib):
        '''Validates postback data in callback.'''
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}

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

        mocked_lib.postback.assert_called_with({}, expected_postback)


@task(base=ProviderTask, provider=database.Provider)
def do_something(context, name, api):
    return {
        'api1': do_something.api,
        'name': name,
        'api2': api,
        'status': 'BLOCKED'
    }

if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
