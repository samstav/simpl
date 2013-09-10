import mock
import unittest

from checkmate import resources


class TestResourcesManager(unittest.TestCase):
    def test_get_resources(self):
        driver = mock.Mock()
        manager = resources.Manager({'default': driver})
        manager.get_resources(tenant_id=123, offset=1, limit=3,
                              resource_type='load-balancer',
                              provider='load-ballooncer')
        driver.get_resources.assert_called_once_with(
            tenant_id=123,
            offset=1,
            limit=3,
            resource_type='load-balancer',
            provider='load-ballooncer'
        )
