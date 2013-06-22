'''
Global configuration

Usage:

    from checkmate.common import config
    CONFIG = config.current()

To update the config:
    CONFIG.update({'setting': "value"})

To load config from sys.args and environment variables:
    CONFIG.initialize()

'''
import argparse
import sys
import logging

LOG = logging.getLogger(__name__)


class Config(object):
    '''Temporary placeholder until we implement a more sophisticated config
    systems
    '''
    address = "127.0.0.1:8080"

    logconfig = None
    debug = False
    verbose = False
    quiet = False
    trace_calls = False

    newrelic = False
    statsd = False
    statsd_port = 8125
    statsd_host = None

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

    def update(self, *args, **kwargs):
        '''Update config with new values.'''
        sources = list(args)
        sources.append(kwargs)
        for source in sources:
            if not hasattr(source, '__iter__'):
                raise ValueError("Config.update requires iterables or kwargs")
            for key, value in source.items():
                LOG.debug("Config change: %s=%s", key, value)
                setattr(self, key, value)

    def initialize(self):
        '''Create a config from sys.args and environment variables'''
        self.update(vars(parse_arguments()))


CURRENT_CONFIG = Config()


def current():
    '''Returns global current config object

    Usage:

        from checkmate.common import config
        CONFIG = config.current()

    To update the config:
        CONFIG.update({'setting': "value"})

    To load config from sys.args and environment variables:
        CONFIG.initialize()
    '''
    return CURRENT_CONFIG


def _comma_separated_strs(value):
    '''Handles comma-separated arguments passed in command-line.'''
    return map(str, value.split(","))


def _comma_separated_key_value_pairs(value):
    '''Handles comma-separated key/values passed in command-line.'''
    pairs = value.split(",")
    results = {}
    for pair in pairs:
        key, pair_value = pair.split('=')
        results[key] = pair_value
    return results


def parse_arguments(args=None):
    '''Parses start-up arguments and returns namespace with config variables.

    :param args: defaults to sys.argv if not supplied
    '''

    parser = argparse.ArgumentParser()

    #
    # Positional arguments
    #
    parser.add_argument("address",
                        help="address and optional port to start server on "
                        "[address[:port]]",
                        nargs='?',
                        default="127.0.0.1:8080"
                        )

    #
    # Verbosity, debugging, and monitoring
    #
    parser.add_argument("--logconfig",
                        help="Optional logging configuration file")
    parser.add_argument("-d", "--debug",
                        action="store_true",
                        help="turn on additional debugging inspection and "
                        "output including full HTTP requests and responses. "
                        "Log output includes source file path and line "
                        "numbers."
                        )
    parser.add_argument("-v", "--verbose",
                        action="store_true",
                        help="turn up logging to DEBUG (default is INFO)"
                        )
    parser.add_argument("-q", "--quiet",
                        action="store_true",
                        help="turn down logging to WARN (default is INFO)"
                        )
    parser.add_argument("--newrelic",
                        action="store_true",
                        default=False,
                        help="enable newrelic monitoring (place newrelic.ini "
                        "in your directory"
                        )
    parser.add_argument("-t", "--trace-calls",
                        action="store_true",
                        default=False,
                        help="display call hierarchy and errors to stdout"
                        )
    parser.add_argument("--statsd",
                        help="enable statsd server with [address[:port]]",
                        )

    #
    # Optional Capabilities
    #
    parser.add_argument("-u", "--with-ui",
                        action="store_true",
                        default=False,
                        help="enable support for browsers and HTML templates"
                        )
    parser.add_argument("-s", "--with-simulator",
                        action="store_true",
                        default=False,
                        help="enable support for the deployment simulator"
                        )
    parser.add_argument("-a", "--with-admin",
                        action="store_true",
                        default=False,
                        help="enable /admin calls (authorized to admin users "
                        "only)"
                        )
    parser.add_argument("-e", "--eventlet",
                        action="store_true",
                        default=False,
                        help="use the eventlet server (recommended in "
                        "production)"
                        )

    #
    # Queue
    #
    parser.add_argument("--eager",
                        action="store_true",
                        default=False,
                        help="all celery (queue) tasks will be executed "
                        "in-process. Use this for debugging only. There is no "
                        "need to start a queue instance when running eager."
                        )
    parser.add_argument("--worker",
                        action="store_true",
                        default=False,
                        help="start the celery worker in-process as well"
                        )

    #
    # Blueprint handling (CrossCheck functionality)
    #
    parser.add_argument("--webhook",
                        action="store_true",
                        default=False,
                        help="Enable blueprints GitHub webhook responder"
                        )
    parser.add_argument("-g", "--github-api",
                        help="Root github API uri for the repository "
                        "containing blueprints. ex: "
                        "https://api.github.com/v3")
    parser.add_argument("-o", "--organization",
                        help="The github organization owning the blueprint "
                        "repositories",
                        default="Blueprints")
    parser.add_argument("-r", "--ref",
                        help="Branch/tag/reference denoting the version of "
                        "blueprints to use.",
                        default="master")
    parser.add_argument("--cache-dir",
                        help="cache directory")
    parser.add_argument("--preview-ref",
                        help="version of deployment templates for preview",
                        default=None)
    parser.add_argument("--preview-tenants",
                        help="preview tenant IDs",
                        type=_comma_separated_strs,
                        default=None)
    parser.add_argument("--group-refs",
                        help="Auth Groups and refs to associate with them as "
                        "a comma-delimited list. Ex. "
                        "--group-refs tester=master,prod=stable",
                        type=_comma_separated_key_value_pairs,
                        default=None)

    if not args:
        if len(sys.argv) > 1 and sys.argv[1] == 'START':
            args = sys.argv[1:]
    parsed = parser.parse_args(args)
    return parsed
