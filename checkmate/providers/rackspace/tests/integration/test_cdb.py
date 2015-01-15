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

"""Unit Tests for Cloud Database Redis instance management."""

import os
import re
import time
import unittest

import requests
import vcr

from checkmate.providers.rackspace.database import dbaas

SCRUB_URI_RE = re.compile(r'v1\.0/[^/]*/')
SCRUB_URI_SUB = 'v1.0/redacted/'
SCRUB_PASSWD_RE = re.compile(r'"password": "[^"]*"')
SCRUB_PASSWD_SUB = '"password": "redacted"'
SCRUB_HOST_RE = re.compile(r'"hostname": "[^"]*"')
SCRUB_HOST_SUB = '"hostname": "redacted"'


def before_record_cb(request):
    request.uri = re.sub(SCRUB_URI_RE, SCRUB_URI_SUB, request.uri)
    if request.body:
        request.body = re.sub(SCRUB_URI_RE, SCRUB_URI_SUB, request.body)
    return request


def before_record_response_cb(response):
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
        with self.vcr.use_cassette('vcr-cdb-full.yaml'):
            create_response = dbaas.create_instance(self.region, self.tenant,
                                                    self.token,
                                                    u'test-delete-me', 101)
            validated = dbaas.validate_instance(create_response)
            self.assertEqual(validated, create_response)

            status = create_response.get('status')
            timeout = time.time() + 60 * 5  # 5 minutes
            while status != u'ACTIVE' and time.time() < timeout:
                time.sleep(self.delay)
                get_response = dbaas.get_instance(self.region, self.tenant,
                                                  self.token,
                                                  create_response.get('id'))
                if 'instance' in get_response:
                    status = get_response['instance'].get('status')


            del_response = dbaas.delete_instance(self.region,
                                                 self.tenant, self.token,
                                                 create_response.get('id'))
            self.assertEqual(u'202, Accepted', del_response)

    def test_successful_configuration_create_retrieve_delete(self):
        """Successfully create/retrieve/delete a database configuration."""
        details = {
            'datastore': {'type': 'mysql', 'version': '5.6'},
            'description': 'Created by integration test. Please delete!',
            'name': 'integration-test-please-delete',
            'values': {'connect_timeout': 60, 'expire_logs_days': 90}
        }
        with self.vcr.use_cassette('vcr-cdb-db-config.yaml'):
            create_response = dbaas.create_configuration(self.region,
                                                         self.tenant,
                                                         self.token,
                                                         details)
            validated = dbaas.validate_db_config(create_response)
            self.assertEqual(validated, create_response)
            config_id = create_response['configuration']['id']

            get_response = dbaas.get_configuration(self.region, self.tenant,
                                                   self.token, config_id)
            self.assertEqual(create_response, get_response)

            delete_response = dbaas.delete_configuration(self.region,
                                                         self.tenant,
                                                         self.token,
                                                         config_id)
            self.assertEqual(u'202, Accepted', delete_response)

    def test_bad_region(self):
        """Invalid region results in an HTTP error (vcrpy not needed)."""
        with self.assertRaises(requests.ConnectionError) as expected:
            dbaas.get_instances(u'YYZ', self.tenant, self.token)

    def test_bad_tenant(self):
        """Invalid tenant results in an HTTP error."""
        with self.vcr.use_cassette('vcr-cdb-tenant-invalid.yaml'):
            dbaas.get_instances(self.region, 'invalid', self.token)

    def test_bad_token(self):
        """Invalid token results in an HTTP error."""
        with self.vcr.use_cassette('vcr-cdb-token-invalid.yaml'):
            dbaas.get_instances(self.region, self.tenant, 'invalid')


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
