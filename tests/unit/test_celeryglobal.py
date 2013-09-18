# pylint: disable=C0103,R0201,R0904,W0603

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

"""Tests for Celery."""
import logging
import mock
import unittest

from celery import exceptions
from celery import task

from checkmate import celeryglobal as celery  # module to be renamed
from checkmate.db import common
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


class TestAfterSetupLoggerHandler(unittest.TestCase):
    @mock.patch.object(celery, 'LOG')
    @mock.patch.object(celery, 'celconf')
    @mock.patch.object(celery.os.path, 'exists', return_value=False)
    def test_invalid_path(self, mock_os, mock_celconf, mock_logger):
        mock_celconf.CHECKMATE_CELERY_LOGCONFIG = 'something'
        celery.after_setup_logger_handler()
        mock_os.assert_called_once_with(mock.ANY)
        mock_logger.debug.assert_called_once_with(
            "'CHECKMATE_CELERY_LOGCONFIG' env is not configured, or is "
            "configured to a non-existent path."
        )

    @mock.patch.object(celery, 'LOG')
    @mock.patch.object(celery, 'celconf')
    def test_no_env_setting(self, mock_celconf, mock_logger):
        mock_celconf.CHECKMATE_CELERY_LOGCONFIG = None
        celery.after_setup_logger_handler()
        mock_logger.debug.assert_called_once_with(
            "'CHECKMATE_CELERY_LOGCONFIG' env is not configured, or is "
            "configured to a non-existent path."
        )

    @mock.patch.object(celery.logging.config, 'fileConfig')
    @mock.patch.object(celery, 'LOG')
    @mock.patch.object(celery, 'celconf')
    @mock.patch.object(celery.os.path, 'exists', return_value=True)
    def test_logging_configured(self, mock_os, mock_celconf, mock_logger,
                                mock_fconfig):
        mock_celconf.CHECKMATE_CELERY_LOGCONFIG = 'something'
        celery.after_setup_logger_handler()
        mock_os.assert_called_once_with(mock.ANY)
        mock_logger.debug.assert_called_once_with(
            "Logging-Configuration file: %s", 'something')
        mock_fconfig.assert_called_once_with('something',
                                             disable_existing_loggers=False)


class TestSingleTask(unittest.TestCase):
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

    def test_concurrent_tasks(self):
        lock_key = "async_dep_writer:DEP_10"
        self.driver.lock(lock_key, 3600)
        do_nothing.lock_db = self.driver
        self.assertRaises(common.ObjectLockedError, do_nothing, "DEP_10")
        self.driver.unlock(lock_key)
        do_nothing("DEP_10")


class TestRetryTask(unittest.TestCase):
    def test_retry_with_custom_exception(self):
        retry_task = celery.RetryTask()
        retry_task.request_stack = mock.Mock()
        request_mock = retry_task.request_stack.top
        request_mock.retries = 2
        request_mock.called_directly = False
        self.assertRaises(Exception, retry_task.retry, max_retries=1,
                          exc=Exception('test'))

    def test_retry_with_no_custom_exception(self):
        retry_task = celery.RetryTask()
        retry_task.subtask_from_request = mock.Mock()
        retry_task.request_stack = mock.Mock()
        request_mock = retry_task.request_stack.top
        request_mock.retries = 2
        request_mock.called_directly = False
        self.assertRaises(exceptions.MaxRetriesExceededError,
                          retry_task.retry,
                          max_retries=1)

    def test_retry_raises_retry_task_error(self):
        retry_task = celery.RetryTask()
        retry_task.subtask_from_request = mock.Mock()
        retry_task.request_stack = mock.Mock()
        request_mock = retry_task.request_stack.top
        request_mock.retries = 2
        request_mock.called_directly = False
        self.assertRaises(exceptions.RetryTaskError, retry_task.retry,
                          max_retries=3)


@task.task(base=celery.SingleTask, default_retry_delay=1, max_retries=4,
           lock_db=None, lock_key="async_dep_writer:{args[0]}",
           lock_timeout=50)
def do_nothing(key):
    """Placeholder method for the task decorator."""
    return key


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
