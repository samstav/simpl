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

"""Test critical and unusual dependencies."""
import sys
import unittest


class TestDependencies(unittest.TestCase):
    """Test critical and unusual dependencies

    Unusual = forks of public projects, depedencies that need complicated
              libraries (like openssh), etc...
    """
    def test_python_version(self):
        self.assertGreaterEqual(sys.version_info, (2, 7, 1), "Checkmate needs "
                                "python version 2.7.1 or later")

    def test_pycrypto_version(self):
        import Crypto
        self.assertGreaterEqual(Crypto.version_info, (2, 6), "Checkmate "
                                "expects pycrypto version 2.6 or later")

    def test_paramiko_version(self):
        import paramiko
        try:
            # new syntax is a string
            version = tuple(int(v) for v in paramiko.__version__.split('.'))
        except AttributeError:
            version = paramiko.__version_info__  # older syntax
        self.assertGreaterEqual(version, (1, 7, 7, 1),
                                "Checkmate expects paramiko version 1.7.7.1 "
                                "or later")

    def test_pam_version(self):
        import pam

    def test_celery_version(self):
        import celery
        version = [int(part) for part in celery.__version__.split(".")]
        self.assertGreaterEqual(version, [3, 0, 9], "Checkmate expects celery "
                                "version 3.0.9 or later")

    def test_yaml_version(self):
        import yaml
        version = [int(part) for part in yaml.__version__.split(".")]
        self.assertGreaterEqual(version, [3, 10], "Checkmate expects PyYAML "
                                "version 3.10 or later")

    def test_spiff_version(self):
        import SpiffWorkflow
        version_info = SpiffWorkflow.version()
        self.assertIn("rackspace internal", version_info, "Checkmate needs "
                      "the Rackspace-extended version of SpiffWorkflow")
        version, _ = SpiffWorkflow.version().split('-')[0:2]
        version = [int(part) for part in version.split(".")]
        self.assertGreaterEqual(version, [0, 3, 2], "Checkmate expects "
                                "SpiffWorkflow version 0.3.2 or later")

    def test_jinja_version(self):
        import jinja2
        version = [int(part) for part in jinja2.__version__.split(".")]
        self.assertEqual(version, [2, 6],
                         "Checkmate expects Jinja2 version 2.6")


if __name__ == '__main__':
    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
