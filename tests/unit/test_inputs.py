# pylint: disable=E1101

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

"""Tests for Input class."""
import unittest

from checkmate import inputs as cminp


class TestInput(unittest.TestCase):
    def test_init_method(self):
        self.assertIsInstance(cminp.Input({}), cminp.Input)

    def test_string_functionality(self):
        self.assertEquals(cminp.Input('test'), 'test')
        self.assertTrue(cminp.Input('test').startswith('t'))
        self.assertEqual(cminp.Input('A') + cminp.Input('B'), 'AB')

    def test_integer_functionality(self):
        self.assertEquals(cminp.Input('1'), '1')
        self.assertIsInstance(cminp.Input(1), int)
        self.assertEqual(cminp.Input('1') + cminp.Input('2'), '12')
        self.assertEqual(cminp.Input(1) + cminp.Input(2), 3)

    def test_url_handling(self):
        data = {
            'url': 'http://example.com',
            'certificate': '----- BEGIN ....',
        }
        url = cminp.Input(data)
        self.assertEqual(url, 'http://example.com')

        self.assertTrue(hasattr(url, 'protocol'))
        self.assertEqual(url.protocol, 'http')

        self.assertTrue(hasattr(url, 'certificate'))
        self.assertEqual(url.certificate, '----- BEGIN ....')

    def test_url_parsing(self):
        url = cminp.Input('https://example.com:80/path')
        url.parse_url()
        self.assertEqual(url, 'https://example.com:80/path')

        self.assertTrue(hasattr(url, 'protocol'))
        self.assertEqual(url.protocol, 'https')

        self.assertTrue(hasattr(url, 'scheme'))
        self.assertEqual(url.protocol, 'https')

        self.assertTrue(hasattr(url, 'netloc'))
        self.assertEqual(url.netloc, 'example.com:80')

        self.assertTrue(hasattr(url, 'hostname'))
        self.assertEqual(url.hostname, 'example.com')

    def test_attribute_availability(self):
        url = cminp.Input({})
        self.assertTrue(hasattr(url, 'url'))
        self.assertTrue(hasattr(url, 'certificate'))
        self.assertTrue(hasattr(url, 'private_key'))
        self.assertTrue(hasattr(url, 'intermediate_key'))

    def test_non_standard_urls(self):
        url = cminp.Input('git://github.com')
        url.parse_url()
        self.assertTrue(hasattr(url, 'url'))
        self.assertEqual(url.url, 'git://github.com')

        self.assertTrue(hasattr(url, 'protocol'))
        self.assertEqual(url.protocol, 'git')


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
