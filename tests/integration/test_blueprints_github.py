# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import json
import unittest2 as unittest

from bottle import default_app
from eventlet.green import socket
import mox
from mox import IgnoreArg
from webtest import TestApp

from checkmate.blueprints import github
from checkmate.common.config import Config


@unittest.skip("Not migrated from CrossCheck fully")
class TestGitHubManager(unittest.TestCase):
    ''' Tests GitHubManager '''

    # pylint: disable=C0103
    def setUp(self):
        self.config = Config({
            'github_api': 'https://github.rackspace.com/api/v3',
            'organization': "Blueprints",
            'ref': 'v0.5',
        })
        self._gm = github.GitHubManager({}, self.config)

    def test_get_blueprints(self):
        """ test get_blueprints method """

        blueprints = self._gm.get_blueprints("v0.5")
        self.assertIsNotNone(blueprints)
        self.assertTrue(len(blueprints.keys()) > 0)

    def test_get_blueprint_and_verify_documentation_section(self):
        """ test get_blueprints method """

        blueprints = self._gm.get_blueprints("v0.5")
        self.assertIsNotNone(blueprints)
        self.assertTrue(len(blueprints) > 1)
        key, _ = blueprints.iteritems().next()
        blueprint = self._gm.get_blueprint(key)
        # verify that documentation section exists in the given blueprint
        self.assertIsNotNone(blueprint['blueprint']['documentation'])

    def test_get_blueprint(self):
        """ test get_blueprint method """

        blueprints = self._gm.get_blueprints("v0.5")
        self.assertIsNotNone(blueprints)
        self.assertTrue(len(blueprints) > 1)
        key, val = blueprints.iteritems().next()
        blueprint = self._gm.get_blueprint(key)
        self.assertEqual(val['name'], blueprint['blueprint']['name'])
        self.assertEqual(val['description'],
                         blueprint['blueprint']['description'])


@unittest.skip("Not migrated from CrossCheck fully")
class TestWebhookRouter(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        self._manager = None
        self.request = None
        self.response = None
        self.handler = None

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_do_post(self):
        ''' test do_post method '''
        new_2 = {
            "deployment": {
                "name": "Modified deployment",
                "description": "testing"
            },
            "environment": {
                "name": "Unit Test Environment"
            }
        }

        # pylint: disable=W0613
        def mock_refresh(repo):
            ''' Simulate update from our repo '''
            self._manager._templates["2"] = new_2

        self.request._headers = {"mock": "Header"}
        self.request.get_header('X-Forwarded-Host').AndReturn(
            self._manager.api_host)
        self.mox.StubOutWithMock(socket, "gethostbyaddr")
        socket.gethostbyaddr("github.rackspace.com").AndReturn(
            ('github.rackspace.com', [], ['10.11.12.13']))
        mock_stream = self.mox.CreateMockAnything()
        mock_stream.read().AndReturn('{"repository":{"name":"foo","owner":'
                                     '{"name":"crosscheck"}}}')
        self.request.stream = mock_stream
        self.mox.StubOutWithMock(self._manager, "refresh")
        self._manager.refresh("foo").WithSideEffects(mock_refresh)
        self.mox.ReplayAll()
        self.handler.on_post(self.request, self.response)
        self.assertEqual(200, self.response.status)
        template_res = Blueprint(self._manager)
        template_res.on_get(self.request, self.response, "T1000", "2")
        self.assertEqual(200, self.response.status)
        self.assertDictEqual(new_2, json.loads(self.response.body))

    def test_not_allowed(self):
        """ Tests that calls from illegal hosts are rejected """
        self.request._headers = {"mock": "Header"}
        self.request.get_header("X-Forwarded-Host").AndReturn(None)
        self.request.get_header("X-Remote-Host").AndReturn("github.com")
        self.request.__str__().AndReturn("I am a mock request!")
        self.mox.ReplayAll()
        try:
            self.handler.on_post(self.request, self.response)
        except HTTPError as htpe:
            self.assertEqual(403, htpe.status)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
