# pylint: disable=C0103,R0904

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
"""Unit Tests for Script class."""
import unittest

from checkmate import exceptions
from checkmate.providers.core.script import manager


class TestScriptClass(unittest.TestCase):
    """Tests core.script Script class that handles script manager."""

    def test_instantiation_no_arg(self):
        """Script() requires an argument."""
        with self.assertRaises(Exception):
            manager.Script()

    def test_simple_string(self):
        """Script() accepts simple file."""
        text = "#!/bin/python"
        script = manager.Script(text)
        self.assertEqual(script.body, text)
        self.assertTrue(hasattr(script, "name"))
        self.assertTrue(hasattr(script, "type"))

    def test_dict(self):
        """Script() accepts dict."""
        data = {
            'body': "#!/bin/python",
            'name': 'install.sh',
            'type': 'sh',
            'parameters': {},
        }
        script = manager.Script(data)
        self.assertEqual(script.body, data['body'])
        self.assertEqual(script.name, data['name'])
        self.assertEqual(script.parameters, data['parameters'])
        self.assertTrue(hasattr(script, "type"))

    def test_bad_param(self):
        """Script() rejects unsupported params."""
        data = {
            'body': "#!/bin/python",
            'name': 'install.sh',
            'type': 'sh',
            'foo': "Don't foo",
        }
        with self.assertRaises(exceptions.CheckmateValidationException):
            manager.Script(data)

    def test_bad_type(self):
        """Script() rejects unsupported type."""
        with self.assertRaises(exceptions.CheckmateValidationException):
            manager.Script(1)


class TestScriptFileTypeDetection(unittest.TestCase):
    """Tests core.script Script class detection of script types."""

    def test_detect_bash_extension(self):
        """Script detects bash extension."""
        data = {
            'body': "#!/bin/python",
            'name': 'install.sh',
        }
        script = manager.Script(data)
        self.assertTrue(hasattr(script, "type"))
        self.assertTrue(script.type, "bash")

    def test_detect_powershell_extension(self):
        """Script detects powershell extension."""
        data = {
            'body': "# powershell script",
            'name': 'install.ps1',
        }
        script = manager.Script(data)
        self.assertTrue(hasattr(script, "type"))
        self.assertTrue(script.type, "powershell")


class TestTemplating(unittest.TestCase):
    """Test Jinja manager of scripts."""

    def test_simple_template(self):
        """Basic Jinja template works."""
        data = {
            'template': '#!/bin/python\nprint "{{"hello"}}"',
            'type': 'sh',
        }
        script = manager.Script(data)
        self.assertTrue(hasattr(script, "template"))
        self.assertEqual(script.body, '#!/bin/python\nprint "hello"')


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
