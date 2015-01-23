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

"""Unit Tests for Cloud Block Storage instance management."""

import os
import re
import unittest

import requests
import vcr

from checkmate import exceptions
from checkmate.providers.rackspace.block import cbs

SCRUB_URI_RE = re.compile(r'v1/[^/]*/')
SCRUB_URI_SUB = 'v1/redacted/'
SCRUB_PASSWD_RE = re.compile(r'"password": "[^"]*"')
SCRUB_PASSWD_SUB = '"password": "redacted"'
SCRUB_HOST_RE = re.compile(r'"hostname": "[^"]*"')
SCRUB_HOST_SUB = '"hostname": "redacted"'
URL = 'https://iad.blockstorage.api.rackspacecloud.com/v1/redacted'


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


class TestCloudBlockStorage(unittest.TestCase):

    """Create block volume, check status, then delete."""

    region = u'IAD'
    tenant = u'redacted'
    token = u'some token'
    context = {
        'auth_token': token,
        'tenant': tenant,
        'catalog': [{
            'type': 'volume',
            'name': 'cloudBlockStorage',
            'endpoints': [{
                'publicURL': URL,
                'region': region
            }]
        }],
    }
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
        """Successfully create/retrieve/delete a block volume."""
        with self.vcr.use_cassette('vcr-cbs-full.yaml'):
            create_response = cbs.create_volume(self.context, self.region,
                                                101)
            validated = cbs.validate_volume(create_response)
            self.assertEqual(validated, create_response)

            del_response = cbs.delete_volume(self.context, self.region,
                                             create_response.get('id'))
            self.assertEqual(u'202, Accepted', del_response)

    def test_bad_region(self):
        """Invalid region results in an HTTP error (vcrpy not needed)."""
        with self.assertRaises(exceptions.CheckmateException):
            cbs.list_volumes(self.context, u'YYZ')

    def test_bad_tenant(self):
        """Invalid tenant results in an HTTP error."""
        context = self.context.copy()
        context['tenant'] = 'invalid'
        with self.vcr.use_cassette('vcr-cbs-tenant-invalid.yaml'):
            cbs.list_volumes(context, self.region)

    def test_bad_token(self):
        """Invalid token results in an HTTP error."""
        context = self.context.copy()
        context['auth_token'] = 'bah!'
        with self.vcr.use_cassette('vcr-cbs-token-invalid.yaml'):
            with self.assertRaises(requests.HTTPError):
                cbs.list_volumes(context, self.region)


def main():
    """Run tests or record API calls."""
    import sys
    if len(sys.argv) > 4:
        # Force vcrpy into record mode
        # If an option is provided, all are required
        # tenant, username, password, and region args must be last and in that
        # order
        from checkmate.middleware.os_auth import identity
        region = unicode(sys.argv.pop())
        token_id, tenantid, username, token_object = identity.authenticate({
            'password': unicode(sys.argv.pop()),
            'username': unicode(sys.argv.pop()),
            'tenant_id': unicode(sys.argv.pop()),
        })
        context = {
            'auth_token': token_id,
            'tenant': tenantid,
            'username': username,
            'catalog': token_object['access']['serviceCatalog'],
        }
        TestCloudBlockStorage.token = token_id
        TestCloudBlockStorage.tenant = tenantid
        TestCloudBlockStorage.region = region
        TestCloudBlockStorage.context = context
        TestCloudBlockStorage.delay = 30
        TestCloudBlockStorage.vcr_mode = 'all'  # (re-)record everything
    unittest.main()

if __name__ == "__main__":
    main()
