import logging

from checkmate import utils

LOG = logging.getLogger(__name__)


class ProviderBase():
    def __init__(self, provider):
        self.dict = provider
        LOG.debug(provider)

    def provides(self):
        return self.dict.get('provides', [])

    def generate_template(self, deployment, service_name, service, name=None):
        raise NotImplementedError()


def get_provider_class(name):
    return utils.import_class("checkmate.providers.%s" % name)
