# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest
import mock

import bottle
import time

from checkmate.deployments import router


class TestPostDeployment_content_to_deployment(unittest.TestCase):
    @mock.patch('checkmate.deployment.get_time_string')
    @mock.patch('checkmate.deployments.router.utils.read_body')
    def test_unwrap_needed(self, mock_read_body, mock_get_time_string):
        mock_read_body.return_value = {'deployment': {'created-by': 'Me'}}
        mock_get_time_string.return_value = '2013-07-15 21:07:00 +0000'
        self.assertEquals(
            {
                'status': 'NEW',
                'created': '2013-07-15 21:07:00 +0000',
                'created-by': 'Me',
                'id': 'Dtest',
                'tenantId': 'Ttest'
            },
            router._content_to_deployment(
                request=None, deployment_id='Dtest', tenant_id='Ttest'))


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
