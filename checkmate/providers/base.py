import logging

from checkmate import utils

LOG = logging.getLogger(__name__)


class ProviderBase():
    def __init__(self, provider):
        self.dict = provider

    def provides(self):
        return self.dict.get('provides', [])

    def generate_template(self, deployment, service_name, service, name=None):
        raise NotImplementedError()


def get_provider_class(vendor, key):
    name = "%s.%s" % (vendor, key)
    class_name = "checkmate.providers.%s" % name.replace('-', '_')
    LOG.debug("Instantiating provider class: %s" % class_name)
    return utils.import_class(class_name)
