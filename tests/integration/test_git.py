# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import os
import shutil
import subprocess
import sys
import unittest
import uuid

import git
from webtest import TestApp

from checkmate.git import middleware
from checkmate.git import manager


class MockWsgiApp(object):

    def __init__(self):
        pass

    def __call__(self, env, start_response):
        assert False, "No calls should get to backend"


def _start_response():
    pass


TEST_PATH = '/tmp/checkmate/test'


class TestCloneSimple(unittest.TestCase):
    def setUp(self):
        self.repo_id = uuid.uuid4().hex
        self.repo_path = os.path.join(TEST_PATH, self.repo_id)
        os.makedirs(self.repo_path)
        manager.init_deployment_repo(self.repo_path)

        self.root_app = MockWsgiApp()
        self.middleware = middleware.GitMiddleware(self.root_app, TEST_PATH)
        self.app = TestApp(self.middleware)

    def tearDown(self):
        shutil.rmtree(self.repo_path)

    def test_bad_path(self):
        res = self.app.get(
            '/T1/deployments/DEP01.git/info/refs?service=git-upload-pack',
            expect_errors=True
        )
        self.assertEqual(res.status, '404 Not Found')

    def test_backend_clone_first_call(self):
        '''Test:
        GIT_CURL_VERBOSE=1 git clone http://localhost:8080/557366/deployments/08af2c9e979e4c0c9e2561791a745794.git
        '''
        os.environ['REQUEST_METHOD'] = 'GET'
        os.environ['GIT_PROJECT_ROOT'] = self.repo_path
        os.environ['PATH_INFO'] = '/info/refs'
        os.environ['GIT_HTTP_EXPORT_ALL'] = '1'
        response = subprocess.check_output(['git', 'http-backend'])
        print response

    @unittest.skip('Unable to get this to work with TestApp')
    def test_clone(self):
        res = self.app.get(
            '/T1/deployments/%s.git/info/refs?service=git-upload-pack' %
            self.repo_id,
        )
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'text/plain')
        print res
        self.assertIsNone(res.body)


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
