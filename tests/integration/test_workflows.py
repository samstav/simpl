# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
import unittest2 as unittest
import bottle
import mox
import checkmate

from celery.app.task import Context
from checkmate.workflows import get_workflows


class TestGetWorkflows(unittest.TestCase):
    """Test GET /workflows endpoint"""

    def test_get_workflows_returns_empty_set(self):
        '''If there are no workflows the DB drivers will return None
        A friendlier API implementation will return an empty set
        '''
        bottle.request.bind({})
        bottle.request.context = Context()
        self._mox = mox.Mox()
        self._mox.StubOutWithMock(checkmate.workflows, "DB")
        checkmate.workflows.DB.get_workflows(
            tenant_id='1234',
            limit=None,
            offset=None
        ).AndReturn(None)

        self._mox.ReplayAll()
        self.assertEquals(
            '{}',
            get_workflows(tenant_id='1234', driver=checkmate.workflows.DB)
        )
        self._mox.VerifyAll()
        self._mox.UnsetStubs()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
