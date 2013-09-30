# pylint: disable=R0904

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
"""Test patterns.yaml file and run any tests embedded in it."""
import copy
import os
import re
import unittest

import yaml


class TestPatterns(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(__file__),
                            os.path.pardir,  # tests
                            os.path.pardir,  # checkmate
                            'checkmate',
                            'common',
                            'patterns.yaml')
        self.patterns = yaml.safe_load(open(path, 'r'))

    def test_patterns_file_loads(self):
        self.assertIsNotNone(self.patterns)
        self.assertIn('regex', self.patterns)

    def test_regex_patterns(self):
        """Tests all regex patterns against the tests supplied in the yaml
        file.
        """
        self.loop_patterns(self.patterns['regex'], '', [])

    def loop_patterns(self, item, hierarchy, test_collector):
        """Recursive lookup of patterns.

        :param test_collector: collects tests as we go down the hierarchy since
                               some tests are placed at the root of a group of
                               others
        """
        for name, pattern in item.iteritems():
            if name not in ["tests", "pass", "fail", "description", "message"]:
                if isinstance(pattern, dict):
                    current_tests = copy.copy(test_collector)
                    if 'tests' in item:
                        current_tests += copy.copy(item['tests'])
                    if 'value' in pattern:
                        # It's a pattern!
                        pattern['key'] = 'patterns%s.%s' % (hierarchy, name)
                        self.exercise_pattern(pattern, current_tests)

                    self.loop_patterns(pattern, '%s.%s' % (hierarchy, name),
                                       current_tests)

    def exercise_pattern(self, pattern, tests):
        """Check pattern and run its tests.

        Check that the regex detects the pass/fail tests as expected.
        """
        for pattern_test in tests:
            message = "%s in %s" % (
                pattern_test.get('description', pattern_test),
                pattern['key'])
            if 'pass' in pattern_test:
                self.assertTrue(re.match(pattern['value'],
                                pattern_test['pass']),
                                msg=message)
            elif 'fail' in pattern_test:
                self.assertFalse(re.match(pattern['value'],
                                 pattern_test['fail']),
                                 msg=message)
            else:
                self.assertFalse(True, "Missing pass/fail keys: %s" %
                                 pattern_test)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
