# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
import unittest2 as unittest
import bottle
import mox
import checkmate

from celery.app.task import Context
from checkmate.blueprints import get_blueprints


class TestGetBlueprints(unittest.TestCase):
    """Test GET /blueprints endpoint"""

    def test_get_blueprints_returns_empty_set(self):
        '''If there are no blueprints the DB drivers will return None
        A friendlier API implementation will return an empty set
        '''
        bottle.request.bind({})
        bottle.request.context = Context()
        self._mox = mox.Mox()
        self._mox.StubOutWithMock(checkmate.blueprints, "DB")
        checkmate.blueprints.DB.get_blueprints(
            tenant_id='1234',
        ).AndReturn(None)

        self._mox.ReplayAll()
        self.assertEquals('{}', get_blueprints(tenant_id='1234'))
        self._mox.VerifyAll()
        self._mox.UnsetStubs()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
