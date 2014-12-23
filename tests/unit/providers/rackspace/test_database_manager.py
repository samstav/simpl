# pylint: disable=R0904,C0103,W0212,E1103
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

"""Module for testing loadbalancer manager."""

import mock
import unittest

import pyrax

from checkmate import exceptions
from checkmate.providers.rackspace.database import manager


class TestManager(unittest.TestCase):

    def test_client_exception_over_limit(self):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.OverLimit("Limit exceeded")
        api.create = mock.MagicMock(side_effect=mock_exception)
        with self.assertRaises(exceptions.CheckmateException) as exc:
            manager.Manager.create_instance("MyDB", 1, 1, {}, {}, api, None)
            self.assertEqual(exc.exception.friendly_message, "Limit exceeded")


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
