import mock
import unittest

from checkmate import resources


class TestResourcesManagerGetResources(unittest.TestCase):
    def setUp(self):
        driver = mock.Mock()
        get_driver_patcher = mock.patch.object(resources.manager.db,
                                               'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = driver
        self.addCleanup(get_driver_patcher.stop)

        manager = resources.Manager()
        manager.get_resources(tenant_id=123, offset=1, limit=3,
                              query='fake query')
        _, self.kwargs = driver.get_resources.call_args

    def test_pass_tenant_id_to_driver(self):
        self.assertEqual(self.kwargs['tenant_id'], 123)

    def test_pass_offset_to_driver(self):
        self.assertEqual(self.kwargs['offset'], 1)

    def test_pass_limit_to_driver(self):
        self.assertEqual(self.kwargs['limit'], 3)

    def test_pass_query_to_driver(self):
        self.assertEqual(self.kwargs['query'], 'fake query')
