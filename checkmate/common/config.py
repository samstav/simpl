'''
Global configuration
'''
import logging

LOG = logging.getLogger(__name__)


class Config(object):
    '''Temporary placeholder until we implement a more sophisticated config
    systems'''
    address = "127.0.0.1:8080"

    logconfig = None
    debug = False
    verbose = False
    quiet = False
    newrelic = False
    trace_calls = False
    statsd = None

    with_ui = False
    with_simulator = False
    with_admin = False
    eventlet = False

    eager = False
    worker = False

    webhook = False
    github_api = None
    organization = None
    ref = 'stable'
    cache_dir = None
    preview_ref = 'master'
    preview_tenants = None
    group_refs = {}

    def __init__(self, values=None):
        if values:
            self.update(values)

    def update(self, values):
        '''Update config with new values'''
        for key, value in values.items():
            LOG.debug("Config change: %s=%s", key, value)
            setattr(self, key, value)


CURRENT_CONFIG = Config()


def current():
    '''Returns global current config object

    Usage:

        from checkmate.common import config
        CONFIG = config.current()

    To update the config:
        CONFIG.update({'setting': "value"})
    '''
    return CURRENT_CONFIG
