# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import mock
import unittest
import uuid

from checkmate.deployments import router
from checkmate.exceptions import CheckmateValidationException


class TestPostDeployment_content_to_deployment(unittest.TestCase):
    @staticmethod
    def expected_deployment(d_id='Dtest'):
        return {
            'status': 'NEW',
            'created': '2013-07-15 21:07:00 +0000',
            'created-by': 'Me',
            'id': d_id,
            'tenantId': 'Ttest'
        }

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_unwrap_needed(self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {'deployment': {'created-by': 'Me'}}
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        self.assertEquals(
            self.expected_deployment(),
            router._content_to_deployment(
                request=None, deployment_id='Dtest', tenant_id='Ttest')
        )

    @mock.patch('checkmate.deployments.router.uuid.uuid4')
    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_no_id_provided(
            self, mock_read_body, mock_get_time_string, mock_uuid):
        mock_read_body.return_value = {'created-by': 'Me'}
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        mock_uuid.return_value = uuid.UUID(
            '{12345678123456781234567812345678}')
        self.assertEquals(
            self.expected_deployment('12345678123456781234567812345678'),
            router._content_to_deployment(
                request=None, tenant_id='Ttest'))

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_id_with_invalid_start_character(
            self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {'deployment': {'created-by': 'Me'}}
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        with self.assertRaises(CheckmateValidationException) as expected:
            router._content_to_deployment(request=None, deployment_id='>test',
                                          tenant_id='Ttest')
        self.assertEqual("Invalid start character '>'. ID can start with any "
                         "of 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTU"
                         "VWXYZ0123456789'", str(expected.exception))

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_id_with_invalid_character(
            self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {'deployment': {'created-by': 'Me'}}
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        with self.assertRaises(CheckmateValidationException) as expected:
            router._content_to_deployment(request=None, deployment_id='t>est',
                                          tenant_id='Ttest')
        self.assertEqual("Invalid character '>'. Allowed characters are "
                         "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTU"
                         "VWXYZ0123456789-_.+~@'", str(expected.exception))

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_includes_is_stripped_from_request(
            self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {
            'deployment': {
                'created-by': 'Me',
                'includes': 'should be deleted'
            }
        }
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        self.assertEquals(
            self.expected_deployment(),
            router._content_to_deployment(
                request=None, deployment_id='Dtest', tenant_id='Ttest')
        )

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_unmatched_tenant_ids_raises_exception(
            self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {
            'deployment': {
                'created-by': 'Me',
                'tenantId': 'Tother',
                'includes': 'should be deleted'
            }
        }
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        with self.assertRaises(CheckmateValidationException) as expected:
            router._content_to_deployment(
                request=None, deployment_id='Dtest', tenant_id='Ttest')
        self.assertEqual('tenantId must match with current tenant ID',
                         str(expected.exception))

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_no_tenant_id_raises_exception(
            self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {
            'deployment': {
                'created-by': 'Me',
                'tenantId': 'Tother',
                'includes': 'should be deleted'
            }
        }
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        with self.assertRaises(AssertionError) as expected:
            router._content_to_deployment(
                request=None, deployment_id='Dtest')
        self.assertEqual('Tenant ID must be specified in deployment.',
                         str(expected.exception))

    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_created_by_added_if_not_provided(
            self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {
            'deployment': {
                'tenantId': 'Ttest',
                'includes': 'should be deleted'
            }
        }
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        mock_request = mock.Mock()
        mock_request.context.username = 'Me'
        self.assertEqual(
            self.expected_deployment(),
            router._content_to_deployment(
                request=mock_request, deployment_id='Dtest', tenant_id='Ttest')
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
