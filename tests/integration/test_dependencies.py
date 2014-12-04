# pylint: disable=R0904
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
        version = sys.version_info
        self.assertGreaterEqual(version, (2, 7, 1), "Checkmate needs "
                                "python version 2.7.1 or later. Found %s" %
                                '.'.join([str(d) for d in version]))

    def test_pycrypto_version(self):
        import Crypto
        version = Crypto.version_info
        self.assertGreaterEqual(version, (2, 6), "Checkmate "
                                "expects pycrypto version 2.6 or later. Found "
                                "%s" % '.'.join([str(d) for d in version]))

    def test_paramiko_version(self):
        import paramiko
        try:
            # new syntax is a string
            version = tuple(int(v) for v in paramiko.__version__.split('.'))
        except AttributeError:
            # older syntax
            version = paramiko.__version_info__   # pylint: disable=E1101
        self.assertGreaterEqual(version, (1, 7, 7, 2),
                                "Checkmate expects paramiko version 1.7.7.2 "
                                "or later. Found %s" %
                                '.'.join([str(d) for d in version]))

    def test_celery_version(self):
        import celery
        version = [int(part) for part in celery.__version__.split(".")]
        self.assertGreaterEqual(version, [3, 1, 17], "Checkmate expects "
                                "celery version 3.1.17 or later. Found %s" %
                                '.'.join([str(d) for d in version]))

    def test_yaml_version(self):
        import yaml
        version = [int(part) for part in yaml.__version__.split(".")]
        self.assertGreaterEqual(version, [3, 10], "Checkmate expects PyYAML "
                                "version 3.10 or later. Found %s" %
                                '.'.join([str(d) for d in version]))

    def test_spiff_version(self):
        import SpiffWorkflow
        version_info = SpiffWorkflow.version()
        self.assertIn("rackspace internal", version_info, "Checkmate needs "
                      "the Rackspace-extended version of SpiffWorkflow")
        version, _ = SpiffWorkflow.version().split('-')[0:2]
        version = [int(part) for part in version.split(".")]
        self.assertGreaterEqual(version, [0, 3, 2], "Checkmate expects "
                                "SpiffWorkflow version 0.3.2 or later. Found "
                                "%s" % '.'.join([str(d) for d in version]))

    def test_jinja_version(self):
        import jinja2
        version = [int(part) for part in jinja2.__version__.split(".")]
        self.assertEqual(version, [2, 7, 1],
                         "Checkmate expects Jinja2 version 2.7.1. Found %s" %
                         '.'.join([str(d) for d in version]))

    def test_bottle_version(self):
        import bottle
        version = [int(d) for d in bottle.__version__.split('.')]
        self.assertEqual(version, [0, 11, 6],
                         "Checkmate expects bottle version 0.11.6. Found %s" %
                         '.'.join([str(d) for d in version]))

    def test_eventlet_version(self):
        import eventlet
        version = [int(d) for d in eventlet.__version__.split('.')]
        self.assertEqual(version, [0, 15, 2],
                         "Checkmate expects eventlet version 0.15.2. Found %s"
                         % '.'.join([str(d) for d in version]))

    def test_pymongo_version(self):
        import pymongo
        version = [int(d) for d in pymongo.version.split('.')]
        self.assertEqual(version, [2, 6, 2],
                         "Checkmate expects pymongo version 2.6.2. Found %s"
                         % '.'.join([str(d) for d in version]))

if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
