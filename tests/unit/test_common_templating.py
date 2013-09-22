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

import mox
import yaml

from checkmate.common import templating
from checkmate import deployment as cm_dep


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


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
