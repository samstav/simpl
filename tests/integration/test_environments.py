# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
import unittest2 as unittest
import bottle
import mox
import checkmate

from celery.app.task import Context
from checkmate.environments import get_environments


class TestGetEnvironments(unittest.TestCase):
    """Test GET /environments endpoint"""

    def test_get_environments_returns_empty_set(self):
        '''If there are no environments the DB drivers will return None
        A friendlier API implementation will return an empty set
        '''
        bottle.request.bind({})
        bottle.request.context = Context()
        self._mox = mox.Mox()
        self._mox.StubOutWithMock(checkmate.environments, "DB")
        checkmate.environments.DB.get_environments(
            tenant_id='1234',
        ).AndReturn(None)

        self._mox.ReplayAll()
        self.assertEquals('{}', get_environments(tenant_id='1234'))
        self._mox.VerifyAll()
        self._mox.UnsetStubs()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
