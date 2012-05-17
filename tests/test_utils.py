#!/usr/bin/env python
import json
import os
import unittest2 as unittest
from checkmate import utils


class TestUtils(unittest.TestCase):
    """ Test Utils code """

    def setUp(self):
        pass

    def test_get_template_name_from_path(self):
        fxn = utils.get_template_name_from_path
        self.assertEqual(fxn(None), 'default')
        self.assertEqual(fxn(''), 'default')
        self.assertEqual(fxn('/'), 'default')

        expected = {'/workflows': 'workflows',
                    '/deployments': 'deployments',
                    '/blueprints': 'blueprints',
                    '/components': 'components',
                    '/environments': 'environments',
                    '/workflows/1': 'workflow',
                    '/workflows/1/tasks': 'workflow.tasks',
                    '/workflows/1/tasks/1': 'workflow.task',
                    '/workflows/1/status': 'workflow.status'
                }
        for path, template in expected.iteritems():
            self.assertEqual(fxn(path), template, '%s should have returned %s'
                    % (path, template))
        # Check with tenant_id
        for path, template in expected.iteritems():
            self.assertEqual(fxn('/T1000/%s' % path), template, '%s should have returned %s'
                    % (path, template))


if __name__ == '__main__':
    unittest.main(verbosity=2)
