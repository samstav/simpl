# pylint: disable=E1101,W0603,W0613

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

"""Tests for common tasks."""
import logging
import mock
import unittest

from checkmate.common import tasks
from checkmate.db import mongodb

try:
    import mongobox as mbox

    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    mbox.MongoBox = object

LOG = logging.getLogger(__name__)


class TestCommonTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance."""
        try:
            cls.box = mbox.MongoBox()
            cls.box.start()
            cls._connection_string = ("mongodb://localhost:%s/test" %
                                      cls.box.port)
        except StandardError as exc:
            LOG.exception(exc)
            if hasattr(cls, 'box'):
                del cls.box
            global SKIP
            global REASON
            SKIP = True
            REASON = str(exc)

    @classmethod
    def tearDownClass(cls):
        """Stop the sanboxed mongodb instance."""
        if hasattr(cls, 'box') and isinstance(cls.box, mbox.MongoBox):
            if cls.box.running() is True:
                cls.box.stop()
                cls.box = None

    def setUp(self):
        self.driver = mongodb.Driver(self._connection_string)

    @mock.patch.object(tasks.operations, 'update_operation')
    def test_update_operation(self, mock_update):
        tasks.operations.update_operation.return_value = True

        tasks.update_operation.lock_db = self.driver
        tasks.update_operation('DEP1', "WID", driver=self, x=1)
        tasks.operations.update_operation.assert_called_once_with(
            'DEP1', 'WID', driver=self, deployment_status=None, x=1
        )

    @mock.patch.object(tasks.operations, 'update_operation')
    def test_update_deployment_status(self, mock_update):
        tasks.operations.update_operation.return_value = True

        tasks.update_operation.lock_db = self.driver
        tasks.update_operation('DEP1', "WID", driver=self,
                               deployment_status="UP",
                               x=1)
        tasks.operations.update_operation.assert_called_once_with(
            'DEP1', 'WID', driver=self, deployment_status='UP', x=1
        )


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
