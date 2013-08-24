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

"""Test core provider package."""
import unittest

from checkmate.providers import base
from checkmate.providers import core


class TestPackage(unittest.TestCase):
    def test_package_registration(self):
        base.PROVIDER_CLASSES = {}
        core.register()
        self.assertIn('core.script', base.PROVIDER_CLASSES)
        self.assertEqual(len(base.PROVIDER_CLASSES), 1, msg="Check that all "
                         "your providers are registered and tested for")


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
