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

# pylint: disable=C0103,R0903

"""Unit Tests for Cloud Servers instance management.

These tests cover only the nova.py file using requests. The pre-existing code
using pyrax is tested elsewhere.
"""

import os
import re
import unittest
import uuid

import mock
import requests
import vcr

from checkmate import exceptions
from checkmate.providers.rackspace.compute import nova

SCRUB_URI_RE = re.compile(r'v2/[^/]*/')
SCRUB_URI_SUB = 'v2/redacted/'
URL = 'https://iad.servers.api.rackspacecloud.com/v2/redacted'


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
        response['body']['string'] = body
    return response


class TestNovaKeyPairsAPI(unittest.TestCase):

    """Test create, upload, list, then delete keypairs with recorded API calls.

    In order to re-record the API calls, run ths file providing real cloud
    credentials. If you have OpenStack configured in your environment, you can
    use the environmnet variables like this:

        python test_nova.py --record $OS_TENANT_ID $OS_USERNAME $OS_PASSWORD \
        $OS_REGION_NAME

    Otherwise, the pre-recorded responses will be used.

    A good time to re-record the calls and submit changed cassette files is
    when the APIs change.
    """

    region = u'IAD'
    tenant = u'redacted'
    token = u'some token'
    context = None
    delay = 0
    vcr_mode = 'none'  # Playback only

    def setUp(self):
        self.vcr = vcr.VCR(
            cassette_library_dir=os.path.join(os.path.dirname(__file__),
                                              'fixtures'),
            record_mode=self.vcr_mode,
            filter_headers=['X-Auth-Token', 'User-Agent'],
            before_record=before_record_cb,
            before_record_response=before_record_response_cb
        )
        if self.context is None:  # setting this on the class breaks nosetests
            self.context = {
                'auth_token': self.token,
                'tenant': self.tenant,
                'catalog': [{
                    'type': 'compute',
                    'name': nova.SERVICE_NAME,
                    'endpoints': [{
                        'publicURL': URL,
                        'region': self.region
                    }]
                }],
            }

    def test_successful_instance_create_retrieve_delete(self):
        """Successfully create/retrieve/delete a keypair."""
        name = "Public Key for Deployment %s" % uuid.uuid4().hex
        with self.vcr.use_cassette('vcr-nova-keypair-full.yaml'):
            create_response = nova.create_keypair(self.context, self.region,
                                                  name)
            #import ipdb;ipdb.set_trace()
            validated = nova.validate_keypair(create_response)
            self.assertEqual(validated, create_response)

            del_response = nova.delete_keypair(self.context, self.region,
                                               create_response['name'])
            self.assertEqual(u'202, Accepted', del_response)

    def test_bad_region(self):
        """Invalid region results in an HTTP error (vcrpy not needed)."""
        with self.assertRaises(exceptions.CheckmateException):
            nova.list_keypairs(self.context, u'YYZ')

    def test_bad_tenant(self):
        """Invalid tenant results in an HTTP error."""
        context = self.context.copy()
        context['tenant'] = 'invalid'
        with self.vcr.use_cassette('vcr-nova-keypair-tenant-invalid.yaml'):
            nova.list_keypairs(context, self.region)

    def test_bad_token(self):
        """Invalid token results in an HTTP error."""
        context = self.context.copy()
        context['auth_token'] = 'bah!'
        with self.vcr.use_cassette('vcr-nova-keypair-token-invalid.yaml'):
            with self.assertRaises(requests.HTTPError):
                nova.list_keypairs(context, self.region)


class TestNovaKeyPairs(unittest.TestCase):

    """Test the functions in the module."""

    @mock.patch.object(nova.requests, 'post')
    def test_max_limit_fail(self, mock_post):
        """Return meaningful text error when maximum reached."""
        response = mock.MagicMock()
        mock_post.return_value = response
        # Content and headers retrieved from real calls hitting the maximum
        response.headers = {
            'content-length': '78',
            'via': '1.1 Repose (Repose/6.2.1.2)',
            'x-compute-request-id': 'req-1861c5b1-9b3e-4d70-8c2e-e8f7f5aa3c5f',
            'server': 'Jetty(9.2.z-SNAPSHOT)',
            'date': 'Fri, 06 Mar 2015 12:00:57 GMT',
            'content-type': 'application/json; charset=UTF-8',
        }
        response.json.return_value = {
            "forbidden": {
                "message": "Quota exceeded, too many key pairs.",
                "code": 403,
            },
        }
        response.ok = False
        context = {
            'auth_token': 'fake_token',
            'tenant': 'tenantid',
            'username': 'john',
            'catalog': [{
                'type': 'compute',
                'name': 'cloudServersOpenStack',
                'endpoints': [{
                    'region': 'IAD',
                    'publicURL': 'foo'
                }]
            }],
        }
        with self.assertRaisesRegexp(requests.HTTPError,
                                     "Quota exceeded, too many key pairs."):
            nova.create_keypair(context, 'IAD', 'Test')


def main():
    """Run tests or record API calls."""
    import sys
    if len(sys.argv) > 5 and sys.argv[1] == '--record':
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
        sys.argv.pop()  # remove '--record'
        context = {
            'auth_token': token_id,
            'tenant': tenantid,
            'username': username,
            'catalog': token_object['access']['serviceCatalog'],
        }
        TestNovaKeyPairsAPI.token = token_id
        TestNovaKeyPairsAPI.tenant = tenantid
        TestNovaKeyPairsAPI.region = region
        TestNovaKeyPairsAPI.context = context
        TestNovaKeyPairsAPI.vcr_mode = 'all'  # (re-)record everything
    unittest.main()

if __name__ == "__main__":
    main()
