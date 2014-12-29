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

"""Tests for Schema module."""

import os
import unittest

import yaml

from checkmate.common import schema
from checkmate import utils


class TestSchema(unittest.TestCase):
    """Test various schema related functions."""

    def test_translation_apache(self):
        self.assertEqual(schema.translate('apache2'), 'apache')

    def test_translation_exists(self):
        self.assertEqual(schema.translate('username'), 'username')

    def test_translation_alias(self):
        self.assertEqual(schema.translate('db'), 'database')

    def test_translation_unknown(self):
        self.assertEqual(schema.translate('foo'), 'foo')

    def test_translation_edge_cases(self):
        self.assertEqual(schema.translate(None), None)
        self.assertEqual(schema.translate('/'), '/')

    def test_validate(self):
        errors = schema.validate(
            {
                "label": "foo",
            },
            schema.OPTION_SCHEMA)
        self.assertEqual([], errors)

    def test_validate_negative(self):
        errors = schema.validate(
            {
                "name": "deprecated",
            },
            schema.OPTION_SCHEMA)
        self.assertEqual(len(errors), 1)

    def test_validate_option(self):
        errors = schema.validate_option("any",
                                        {
                                            "label": "foo",
                                            "type": "string",
                                            "default": "None",
                                            "display-hints": {
                                                "group": "test group",
                                                "weight": 5,
                                                'choice': [],
                                            },
                                            'help': "Here's how...",
                                            'description': "Yada yada",
                                            'required': False,
                                            'constrains': [],
                                            'constraints': [],
                                        })
        self.assertEqual([], errors)

    def test_validate_option_negative(self):
        errors = schema.validate_option("key",
                                        {
                                            "name": "deprecated",
                                            "type": "foo",
                                        })
        self.assertEqual(len(errors), 2, msg=errors)

    def test_translation_path(self):
        self.assertEqual(schema.translate('db/hostname'), 'database/host')

    def test_validate_inputs(self):
        """Test that known input formats all pass validation."""
        deployment = utils.yaml_to_dict("""
            blueprint:
              options:
                my_simple_url:
                  type: url
                my_complex_url:
                  type: url
                my_int:
                  type: integer
                my_boolean:
                  type: boolean
                my_string:
                  type: string
            inputs:
              blueprint:
                my_simple_url: http://domain.com
                my_complex_url:
                  url: https://secure.domain.com
                  certificate: |
                    ----- BEGIN ....
                my_int: 1
                my_boolean: true
                my_string: Hello!
            """)
        self.assertListEqual(schema.validate_inputs(deployment), [])

    def test_bad_url_is_invalid(self):
        """Test that bad url input formats don't pass validation."""
        deployment = utils.yaml_to_dict("""
            blueprint:
              options:
                try_list:
                  type: url
                bad_fields:
                  type: url
                try_int:
                  type: url
                try_boolean:
                  type: url
            inputs:
              blueprint:
                try_list:
                - url: http://domain.com
                - certificate: blah
                bad_fields:
                  foo: https://secure.domain.com
                  bar: |
                    ----- BEGIN ....
                try_int: 1
                try_boolean: true
            """)
        expected = [
            "extra keys not allowed @ data['bar']",
            "extra keys not allowed @ data['foo']",
            ("Option 'try_list' should be a string or valid url mapping. It "
             "is a 'list' which is not valid"),
            ("Option 'try_int' should be a string or valid url mapping. It is "
             "a 'int' which is not valid"),
            ("Option 'try_boolean' should be a string or valid url mapping. "
             "It is a 'bool' which is not valid"),
        ]
        results = schema.validate_inputs(deployment)
        results.sort()
        expected.sort()
        self.assertListEqual(results, expected)


class TestUICatalog(unittest.TestCase):

    def test_catalog(self):
        rel_path = '../../ui/rook/static/scripts/common/services/catalog.yml'
        path = os.path.join(os.path.dirname(__file__), rel_path)
        with open(path) as fh:
            components = fh.read()

        for doc in yaml.safe_load_all(components):
            schema.COMPONENT_SCHEMA(doc)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
