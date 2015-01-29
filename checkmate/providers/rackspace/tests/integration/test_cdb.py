# Copyright (c) 2011-2015 Rackspace US, Inc.
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

# pylint: disable=C0103

"""Unit Tests for Cloud Database Redis instance management."""

import os
import re
import time
import unittest

import requests
import vcr

from checkmate import exceptions
from checkmate.providers.rackspace.database import dbaas
from checkmate.providers.rackspace.tests import common

SCRUB_URI_RE = re.compile(r'v1\.0/[^/]*/')
SCRUB_URI_SUB = 'v1.0/redacted/'
SCRUB_PASSWD_RE = re.compile(r'"password": "[^"]*"')
SCRUB_PASSWD_SUB = '"password": "redacted"'
SCRUB_HOST_RE = re.compile(r'"hostname": "[^"]*"')
SCRUB_HOST_SUB = '"hostname": "redacted"'


def before_record_cb(request):
    """Callback function to scrub request data before saving."""
    request.uri = re.sub(SCRUB_URI_RE, SCRUB_URI_SUB, request.uri)
    if request.body:
        request.body = re.sub(SCRUB_URI_RE, SCRUB_URI_SUB, request.body)
    return request


def before_record_response_cb(response):
    """Callback function to scrub response data before saving."""
    body = response.get('body').get('string')
    if body:
        body = re.sub(SCRUB_URI_RE, SCRUB_URI_SUB, body)
        body = re.sub(SCRUB_PASSWD_RE, SCRUB_PASSWD_SUB, body)
        body = re.sub(SCRUB_HOST_RE, SCRUB_HOST_SUB, body)
        response['body']['string'] = body
    return response


class TestCloudDatabases(unittest.TestCase):
    """Create DB, check status, then delete DB."""
    region = u'IAD'
    tenant = u'redacted'
    token = u'some token'
    delay = 0
    vcr_mode = 'none'  # Playback only

    def setUp(self):
        self.vcr = vcr.VCR(
            cassette_library_dir=os.path.dirname(__file__) + '/fixtures',
            record_mode=self.vcr_mode,
            filter_headers=['X-Auth-Token', 'User-Agent'],
            before_record=before_record_cb,
            before_record_response=before_record_response_cb
        )

    def test_successful_instance_create_retrieve_delete(self):
        """Successfully create/retrieve/delete a database instance."""
        context = common.MockContext(self.region, self.tenant, self.token)
        with self.vcr.use_cassette('vcr-cdb-full.yaml'):
            create_resp = dbaas.create_instance(context, 'test-delete-me', 101)
            validated = dbaas.validate_instance_details(create_resp)
            self.assertEqual(validated, create_resp)

            status = create_resp.get('status')
            timeout = time.time() + 60 * 5  # 5 minutes
            while status != u'ACTIVE' and time.time() < timeout:
                time.sleep(self.delay)
                get_response = dbaas.get_instance(context,
                                                  create_resp.get('id'))
                if 'instance' in get_response:
                    status = get_response['instance'].get('status')

            del_response = dbaas.delete_instance(context,
                                                 create_resp.get('id'))
            self.assertEqual(u'202, Accepted', del_response)

    def test_successful_configuration_create_retrieve_delete(self):
        """Successfully create/retrieve/delete a database configuration."""
        context = common.MockContext(self.region, self.tenant, self.token)
        values = {'connect_timeout': 60, 'expire_logs_days': 90}
        with self.vcr.use_cassette('vcr-cdb-db-config.yaml'):
            create_response = dbaas.create_configuration(context, 'mysql',
                                                         '5.6', values)
            validated = dbaas.validate_db_config(create_response)
            self.assertEqual(validated, create_response)
            config_id = create_response['configuration']['id']

            get_response = dbaas.get_configuration(context, config_id)
            self.assertEqual(create_response, get_response)

            delete_response = dbaas.delete_configuration(context, config_id)
            self.assertEqual(u'202, Accepted', delete_response)

    def test_get_config_params(self):
        """Retrieve config params for MySQL version 5.6."""
        context = common.MockContext(self.region, self.tenant, self.token)
        with self.vcr.use_cassette('vcr-cdb-get-config-params.yaml'):
            get_response = dbaas.get_config_params(context, 'mysql', '5.6')
            self.assertTrue(isinstance(get_response, list))

    def test_datastore_version_id(self):
        """Retrieve datastore version id for MySQL version 5.6."""
        context = common.MockContext(self.region, self.tenant, self.token)
        with self.vcr.use_cassette('vcr-cdb-get-datastore-version-id.yaml'):
            get_response = dbaas.get_dstore_ids(context, 'mysql', '5.6')
            expected = {
                'datastore_id': u'10000000-0000-0000-0000-000000000001',
                'version_id': u'14069833-2efd-4d3a-b7e7-d57b51fc7dc4'
            }
            self.assertEqual(expected, get_response)

    def test_bad_region(self):
        """Invalid region results in an HTTP error (vcrpy not needed)."""
        context = common.MockContext('YYZ', self.tenant, self.token)
        with self.assertRaises(requests.ConnectionError):
            dbaas.get_instances(context)

    def test_bad_tenant(self):
        """Invalid tenant results in an HTTP error."""
        context = common.MockContext(self.region, 'invalid', self.token)
        with self.vcr.use_cassette('vcr-cdb-tenant-invalid.yaml'):
            dbaas.get_instances(context)

    def test_bad_token(self):
        """Invalid token results in an HTTP error."""
        context = common.MockContext(self.region, self.tenant, 'invalid')
        with self.vcr.use_cassette('vcr-cdb-token-invalid.yaml'):
            dbaas.get_instances(context)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 3:
        # Force vcrpy into record mode
        # If an option is provided, all are required
        # region, tenant, token args must be last and in that order
        TestCloudDatabases.token = unicode(sys.argv.pop())
        TestCloudDatabases.tenant = unicode(sys.argv.pop())
        TestCloudDatabases.region = unicode(sys.argv.pop())
        TestCloudDatabases.delay = 30
        TestCloudDatabases.vcr_mode = 'all'  # (re-)record everything

    unittest.main()
