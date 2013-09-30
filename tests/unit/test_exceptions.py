# pylint: disable=C0103,R0201,R0904

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
"""Tests for checkmate exceptions."""

import unittest

from checkmate import exceptions as cmexc


class TestCheckmateException(unittest.TestCase):

    def test_checkmate_exception(self):
        exc = cmexc.CheckmateException()
        self.assertFalse(exc.resetable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resumable)
        self.assertEqual(str(exc), "Checkmate Error")
        self.assertEqual(repr(exc), "CheckmateException(None, None, 0, None)")

    def test_checkmate_exception_message(self):
        exc = cmexc.CheckmateException("Technical Message")
        self.assertFalse(exc.resetable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resumable)
        self.assertEqual(str(exc), "Technical Message")
        self.assertEqual(
            repr(exc),
            "CheckmateException('Technical Message', None, 0, None)")

    def test_checkmate_exception_friendly(self):
        """Exception uses standard message for __str__ like other exceptions.

        We only want to use friendly messages when we explicetly want them,
        otherwise we want to behave like a normal exception.
        """
        exc = cmexc.CheckmateException("Technical Message",
                                       friendly_message="Friendly Message")
        self.assertFalse(exc.resetable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resumable)
        self.assertEqual(str(exc), "Technical Message")

    def test_checkmate_retriable_exception(self):
        exc = cmexc.CheckmateException("Technical Message",
                                       options=cmexc.CAN_RETRY)
        self.assertTrue(exc.retriable)
        self.assertFalse(exc.resumable)
        self.assertFalse(exc.resetable)

    def test_checkmate_resumable_exception(self):
        exc = cmexc.CheckmateException("Technical Message",
                                       options=cmexc.CAN_RESUME)
        self.assertTrue(exc.resumable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resetable)

    def test_checkmate_resetable_exception(self):
        exc = cmexc.CheckmateException("Technical Message",
                                       options=cmexc.CAN_RESET)
        self.assertTrue(exc.resetable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resumable)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
