# pylint: disable=C0103,R0904

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

"""Unit Tests for Script class."""

import json
import os
import unittest

import mox
import yaml

from checkmate.common import templating
from checkmate import deployment as cm_dep

TEST_CERT = """-----BEGIN CERTIFICATE-----
MIICkjCCAfsCAgXeMA0GCSqGSIb3DQEBBQUAMIG2MQswCQYDVQQGEwJVUzEOMAwG
A1UECBMFVGV4YXMxFDASBgNVBAcTC1NhbiBBbnRvbmlvMRIwEAYDVQQKEwlSYWNr
c3BhY2UxHjAcBgNVBAsTFVN5c3RlbSBBZG1pbmlzdHJhdGlvbjEjMCEGA1UEAxMa
UmFja3NwYWNlIEludGVybmFsIFJvb3QgQ0ExKDAmBgkqhkiG9w0BCQEWGVNlcnZp
Y2VEZXNrQHJhY2tzcGFjZS5jb20wHhcNMTMwNTE2MDYxMDQ3WhcNMTQwNTE2MDYx
MDQ3WjBrMQswCQYDVQQGEwJVUzEOMAwGA1UECBMFVGV4YXMxEjAQBgNVBAoTCVJh
Y2tzcGFjZTEVMBMGA1UECxMMWmlhZCBTYXdhbGhhMSEwHwYDVQQDExhjaGVja21h
dGUuY2xvdWQuaW50ZXJuYWwwgZ8wDQYJKoZIhvcNAQEBBQADgY0AMIGJAoGBALin
K4gUwoQVt6mapFqmFBHAL1YUqabjWeyQNGD4Vt7L9XVgh6l1k+uqdzOKP7vlKh+T
diUnDh/VTpq8HZ+bHI8HhDLLIXG61+3LDa+CkgRi4RuwgWIUUY7rs9rUCnJ2HeYa
gRR+moptp+OK9rIwPv0k4O2Q29efBnZaL5Yyk3dPAgMBAAEwDQYJKoZIhvcNAQEF
BQADgYEAYxnk0LCk+kZB6M93Cr4Br0brE/NvNguJVoep8gb1sHI0bbnKY9yAfwvF
0qrcpuTvCS7ggfg1nCtXteJiYsRxZaleQeQSXBswXT3s3ZrUR9RSRPfGqJ9XiGlz
/YrPhnGGC24lpqLV8lBZkLsdnnoKwQfI+aRGbg0x2pi+Zh22H8U=
-----END CERTIFICATE-----"""


class TestTemplating(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_yaml_escaping_simple(self):
        template = "id: {{ setting('password') }}"
        deployment = cm_dep.Deployment({
            'inputs': {
                'password': "Password1",
            },
            'blueprint': {},
        })

        result = templating.parse(template, deployment=deployment)
        self.assertEqual(result, "id: Password1")
        data = yaml.safe_load(result)
        self.assertEqual(data, {'id': 'Password1'})

    def test_yaml_escaping_at(self):
        template = "id: {{ setting('password') }}"
        deployment = cm_dep.Deployment({
            'inputs': {
                'password': "@W#$%$^D%F^UGY",
            },
            'blueprint': {},
        })

        result = templating.parse(template, deployment=deployment)
        self.assertEqual(result, "id: '@W#$%$^D%F^UGY'")
        data = yaml.safe_load(result)
        self.assertEqual(data, {'id': '@W#$%$^D%F^UGY'})

    def test_parsing_functions_hash(self):
        template = "value: {{ hash('password', salt='ahem1234') }}"
        expected = ("value: $6$rounds=100000$ahem1234$WDinkd.aajNmGHPGJpdEnQwh"
                    "ipq3nDNSejs15KMCu/fYJ.0b.9ZC9oLicedLAU.rlBlNJcwGe/rOzh5.S"
                    "rJSv1")
        self.assertEqual(templating.parse(template), expected)

    def test_parsing_functions_parse_url(self):
        template = '''
            scheme: {{ parse_url('http://github.com').scheme }}
            netloc: {{ parse_url('http://github.com').netloc }}
            path: {{ parse_url('http://github.com/checkmate').path }}
            fragment: {{ parse_url('http://github.com/#master').fragment }}
        '''
        parsed = templating.parse(template)
        result = yaml.safe_load(parsed)
        expected = {
            'scheme': 'http',
            'netloc': 'github.com',
            'fragment': 'master',
            'path': '/checkmate',
        }
        self.assertEqual(result, expected)

    def test_parsing_functions_parse_url_Input(self):
        template = '''
            cert: {{ parse_url({'url': 'http://github.com', 'certificate': \
'SOME_CERT'}).certificate }}
            scheme: {{ parse_url({'url': 'http://github.com', 'certificate': \
'SOME_CERT'}).protocol }}
        '''
        parsed = templating.parse(template)
        result = yaml.safe_load(parsed)
        expected = {
            'scheme': 'http',
            'cert': 'SOME_CERT',
        }
        self.assertEqual(result, expected)

    def test_parsing_functions_url_certificate(self):
        deployment = cm_dep.Deployment({
            'inputs': {
                'blueprint': {
                    'url': {
                        'url': 'http://github.com',
                        'certificate': TEST_CERT,
                    },
                },
            },
            'blueprint': {},
        })
        template = """value: |
    {{ parse_url(setting('url')).certificate  | indent(4)}}"""
        result = templating.parse(template, deployment=deployment)
        data = yaml.safe_load(result)
        self.assertEqual(data['value'], TEST_CERT)

    def test_parsing_functions_bool_string(self):
        template = "value: {{ bool('foo') }}"
        expected = ("value: True")
        self.assertEqual(templating.parse(template), expected)

    def test_parsing_functions_bool_emptystring(self):
        template = "value: {{ bool('') }}"
        expected = ("value: False")
        self.assertEqual(templating.parse(template), expected)

    def test_parsing_functions_bool_none(self):
        template = "value: {{ bool(None) }}"
        expected = ("value: False")
        self.assertEqual(templating.parse(template), expected)

    def test_parsing_functions_bool_number(self):
        template = "value: {{ bool(1) }}"
        expected = ("value: True")
        self.assertEqual(templating.parse(template), expected)


class TestJsonYamlCoexistance(unittest.TestCase):

    """Test that we can use templating in JSON and YAML."""

    def test_preserve_linefeed_escaping(self):
        """preserve returns escaped linefeeds."""
        result = templating.parse('{{ "A\nB" | preserve }}')
        self.assertEqual(result, 'A\\nB')

    def test_json_certificate(self):
        """url.certificate works in json."""
        deployment = cm_dep.Deployment({
            'inputs': {
                'blueprint': {
                    'url': {
                        'url': 'http://github.com',
                        'certificate': TEST_CERT,
                    },
                },
            },
            'blueprint': {},
        })
        template = ('value: "{{ parse_url(setting("url")).certificate | '
                    'preserve }}" ')
        result = templating.parse(template, deployment=deployment)
        data = yaml.safe_load(result)
        self.assertEqual(data['value'], TEST_CERT)

        template = ('{"value": "{{ parse_url(setting("url")).certificate |'
                    ' preserve }}"}')
        result = templating.parse(template, deployment=deployment)
        data = json.loads(result)
        self.assertEqual(data['value'], TEST_CERT)

    def test_parsing_patterns(self):
        """patterns exist."""
        path = os.path.join(os.path.dirname(__file__),
                            os.path.pardir,  # tests
                            os.path.pardir,  # checkmate
                            'checkmate',
                            'patterns.yaml')
        patterns = yaml.safe_load(open(path, 'r'))
        value = patterns['regex']['linux_user']['optional']['value']
        template = "value: {{ patterns.regex.linux_user.optional.value }}"
        expected = ("value: %s" % value)
        self.assertEqual(templating.parse(template), expected)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
