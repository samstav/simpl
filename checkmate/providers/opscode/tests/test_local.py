#!/usr/bin/env python
import __builtin__
import json
import mox
import os
import unittest2 as unittest

from checkmate.providers.opscode import local


class TestChefLocal(unittest.TestCase):
    """ Test CheffLocal Module """

    def setUp(self):
        os.environ['CHECKMATE_CHEF_LOCAL_PATH'] = '/tmp/checkmate/test'
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_cook_missing_role(self):
        results = """Checking cookbook syntax...
[Mon, 21 May 2012 17:25:54 +0000] INFO: *** Chef 0.10.10 ***
[Mon, 21 May 2012 17:25:55 +0000] INFO: Setting the run_list to ["role[build]", "role[wordpress-web]"] from JSON
[Mon, 21 May 2012 17:25:55 +0000] ERROR: Role build is in the runlist but does not exist. Skipping expand.
[Mon, 21 May 2012 17:25:55 +0000] ERROR: Role wordpress-web is in the runlist but does not exist. Skipping expand.
[Mon, 21 May 2012 17:25:55 +0000] FATAL: Stacktrace dumped to /tmp/checkmate/environments/myEnv/chef-stacktrace.out
[Mon, 21 May 2012 17:25:55 +0000] FATAL: Chef::Exceptions::MissingRole: Chef::Exceptions::MissingRole
"""
        params = ['knife', 'cook', 'root@a.b.c.d', '-p', '22']

        #Stub out checks for paths
        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists('/tmp/checkmate/test').AndReturn(True)
        os.path.exists('/tmp/checkmate/test/myEnv/kitchen').AndReturn(True)
        os.path.exists('/tmp/checkmate/test/myEnv/kitchen/nodes/a.b.c.d.json')\
                .AndReturn(True)

        #Stub out file access
        mock_file = self.mox.CreateMockAnything()
        mock_file.__enter__().AndReturn(mock_file)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file reads
        node = json.loads('{ "run_list": [] }')
        self.mox.StubOutWithMock(json, 'load')
        json.load(mock_file).AndReturn(node)

        #Stub out file write
        mock_file.__enter__().AndReturn(mock_file)
        self.mox.StubOutWithMock(json, 'dump')
        json.dump(node, mock_file).AndReturn(None)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file opens
        self.mox.StubOutWithMock(__builtin__, 'file')
        __builtin__.file("/tmp/checkmate/test/myEnv/kitchen/nodes/a.b.c.d."
                "json", 'r').AndReturn(mock_file)
        __builtin__.file("/tmp/checkmate/test/myEnv/kitchen/nodes/a.b.c.d."
                "json", 'w').AndReturn(mock_file)

        #Stub out directory change
        self.mox.StubOutWithMock(os, 'chdir')
        os.chdir('/tmp/checkmate/test/myEnv/kitchen').AndReturn(None)

        #Stub out process call to knife
        self.mox.StubOutWithMock(local, 'check_output')
        local.check_output(params).AndReturn(results)

        self.mox.ReplayAll()
        try:
            local.cook('a.b.c.d',  'myEnv', recipes=None,
                roles=['build', 'wordpress-web'])
        except Exception as exc:
            self.assertIn("Chef/Knife error encountered: MissingRole",
                        exc.__str__())
        self.mox.VerifyAll()


if __name__ == '__main__':
    unittest.main()
