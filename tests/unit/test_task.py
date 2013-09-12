import unittest

from mock import MagicMock
from checkmate import task as cmtsk
from checkmate.exceptions import CheckmateRetriableException

"""Task module Tests - for Task class helper methods"""


class TestTask(unittest.TestCase):
    """Tests for Tasks helper methods"""
    def test_is_failed_task(self):
        task_with_error = MagicMock(_get_internal_attribute=MagicMock())
        task_without_error = MagicMock(_get_internal_attribute=MagicMock())

        task_with_error._get_internal_attribute.return_value = {
            "info": "Error Information",
            "state": "FAILURE",
            "traceback": "Traceback"}

        task_without_error._get_internal_attribute.return_value = {}

        self.assertTrue(cmtsk.is_failed(task_with_error))
        self.assertFalse(cmtsk.is_failed(task_without_error))

    def test_get_exception_on_task(self):
        task = MagicMock()
        task._get_internal_attribute = MagicMock()
        task._get_internal_attribute.return_value = {
            "info": ("CheckmateRetriableException(u\'\',"
                     " \'CheckmateServerBuildFailed\', "
                     "u\'Server build failed\', \'\')")}
        exception = cmtsk.get_exception(task)
        task._get_internal_attribute.assert_called_once_with("task_state")
        self.assertTrue(isinstance(exception, CheckmateRetriableException))

    def test_set_exception_on_task(self):
        task = MagicMock()
        task._get_internal_attribute = MagicMock()
        task._get_internal_attribute.return_value = {
            "info": ("CheckmateRetriableException(u\'\',"
                     " \'CheckmateServerBuildFailed\', "
                     "u\'Server build failed\', \'\')")}
        new_exception = Exception("This replaces the old exception")
        cmtsk.set_exception(new_exception, task)
        exception = cmtsk.get_exception(task)
        task._get_internal_attribute.assert_called_with("task_state")
        self.assertTrue(isinstance(exception, Exception))
