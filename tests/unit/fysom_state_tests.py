# coding=utf-8
#
# fysom - pYthOn Finite State Machine - this is a port of Jake
#         Gordon's javascript-state-machine to python
#         https://github.com/jakesgordon/javascript-state-machine
#
# Copyright (C) 2011 Mansour Behabadi <mansour@oxplot.com>, Jake Gordon
#                                        and other contributors
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import unittest

from checkmate.common.fysom import Fysom, FysomError


class FysomStateTests(unittest.TestCase):
    def setUp(self):
        self.fsm = Fysom({
            'initial': 'green',
            'events': [
                {'name': 'warn', 'src': 'green', 'dst': 'yellow'},
                {'name': 'panic', 'src': 'yellow', 'dst': 'red'},
                {'name': 'calm', 'src': 'red', 'dst': 'yellow'},
                {'name': 'clear', 'src': 'yellow', 'dst': 'green'}
            ]
        })

    def test_is_state_should_succeed_for_initial_state(self):
        self.assertTrue(self.fsm.isstate('green'))

    def test_identity_transition_should_not_be_allowed_by_default(self):
        self.assertFalse(self.fsm.can('clear'))
        self.assertTrue(self.fsm.cannot('clear'))

    def test_configured_transition_should_work(self):
        self.assertTrue(self.fsm.can('warn'))

    def test_transition_should_change_state(self):
        self.fsm.warn()
        self.assertTrue(self.fsm.isstate('yellow'))

    def test_should_raise_exception_when_state_transition_is_not_allowed(self):
        self.assertRaises(FysomError, self.fsm.panic)
        self.assertRaises(FysomError, self.fsm.calm)
        self.assertRaises(FysomError, self.fsm.clear)
