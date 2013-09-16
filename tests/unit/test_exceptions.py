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
    def test_checkmate_retriable_exception(self):
        exc = cmexc.CheckmateException("Techincal Message",
                                       friendly_message="Friendly Message",
                                       options=cmexc.CAN_RETRY)
        self.assertTrue(exc.retriable)
        self.assertFalse(exc.resumable)
        self.assertFalse(exc.resetable)

    def test_checkmate_resumable_exception(self):
        exc = cmexc.CheckmateException("Techincal Message",
                                       friendly_message="Friendly Message",
                                       options=cmexc.CAN_RESUME)
        self.assertTrue(exc.resumable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resetable)

    def test_checkmate_resetable_exception(self):
        exc = cmexc.CheckmateException("Techincal Message",
                                       friendly_message="Friendly Message",
                                       options=cmexc.CAN_RESET)
        self.assertTrue(exc.resetable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resumable)

    def test_checkmate_exception(self):
        exc = cmexc.CheckmateException("Techincal Message",
                                       "Friendly Message")
        self.assertFalse(exc.resetable)
        self.assertFalse(exc.retriable)
        self.assertFalse(exc.resumable)
