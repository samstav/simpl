# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Global configuration.

Usage:

    from checkmate.common import config
    CONFIG = config.current()


To load config from sys.args, environment variables, and keyring:
    CONFIG.parse()

"""
import argparse
import logging
import os
import sys

from checkmate.contrib import config
from checkmate import utils

LOG = logging.getLogger(__name__)


OPTIONS = [
    #
    # General Options
    #
    config.Option("--address",
                  help="address and optional port to start server on "
                  "[address[:port]]",
                  nargs='?',
                  default="127.0.0.1:8080",
                  env="CHECKMATE_ADDRESS"
                  ),
    config.Option("--deployments-path",
                  default="/var/local/checkmate/deployments",
                  env="CHECKMATE_CHEF_LOCAL_PATH",
                  ),
    config.Option("--omnibus-version",
                  env="CHECKMATE_CHEF_OMNIBUS_VERSION",
                  ),
    config.Option("-m", "--connection-string",
                  help="URL to the database store (ex: mongodb://localhost)"
                  ),
    config.Option("-c", "--cache-connection-string",
                  help="URL to a cache, ex: redis://localhost",
                  ),
    config.Option("--app-environment",
                  default="dev",
                  help="Application environment, i.e. production, dev",
                  env='CHECKMATE_APP_ENV',
                  ),
    config.Option("--bottle-reloader",
                  mutually_exclusive_group='bottle_reloader',
                  default=True,
                  dest='bottle_reloader',
                  action="store_true",
                  help="Use bottle reloader (default is True)"
                  ),
    config.Option("--no-bottle-reloader",
                  mutually_exclusive_group='bottle_reloader',
                  action="store_false",
                  dest='bottle_reloader',
                  help="Do not use bottle reloader (default is False)"
                  ),
    #
    # Verbosity, debugging, and monitoring
    #
    config.Option("--logconfig",
                  help="Optional logging configuration file"
                  ),
    config.Option("-d", "--debug",
                  default=False,
                  action="store_true",
                  help="turn on additional debugging inspection and "
                  "output including full HTTP requests and responses. "
                  "Log output includes source file path and line "
                  "numbers"
                  ),
    config.Option("-v", "--verbose",
                  default=False,
                  action="store_true",
                  help="turn up logging to DEBUG (default is INFO)"
                  ),
    config.Option("-q", "--quiet",
                  default=False,
                  action="store_true",
                  help="turn down logging to WARN (default is INFO)"
                  ),
    config.Option("--newrelic",
                  action="store_true",
                  default=False,
                  help="enable newrelic monitoring (place newrelic.ini "
                  "in your directory)"
                  ),
    config.Option("-t", "--trace-calls",
                  action="store_true",
                  default=False,
                  help="display call hierarchy and errors to stdout"
                  ),
    config.Option("--statsd",
                  help="enable statsd server with [address[:port]]. "
                       "Overrides '--statsd-host' and '--statsd-port'.",
                  dest="statsd_url",
                  ),
    config.Option("--statsd-host",
                  help="enable statsd server with hostname - use with "
                       "'--statsd-port'. Cannot be used with '--statsd'",
                  env="STATSD_HOST",
                  dest="statsd_host",
                  ),
    config.Option("--statsd-port",
                  help="enable statsd server with port - use with "
                       "'--statsd-host'. Cannot be used with '--statsd'",
                  default=8125,
                  env="STATSD_PORT",
                  dest="statsd_port",
                  ),
    config.Option("--access-log",
                  type=argparse.FileType('a', 0),
                  help="File to store access HTTP logs in"
                  ),
    #
    # Optional Capabilities
    #
    config.Option("--with-git",
                  action="store_true",
                  default=False,
                  help="Enable git protocl support (git clone, push, "
                  "pull to deplpoyments.git URLs"
                  ),
    config.Option("-u", "--with-ui",
                  action="store_true",
                  default=False,
                  help="enable support for browsers and HTML templates"
                  ),
    config.Option("-s", "--with-simulator",
                  action="store_true",
                  default=False,
                  help="enable support for the deployment simulator"
                  ),
    config.Option("--simulator-connection-string",
                  help="Connection string for the deployment simulator."
                  ),
    config.Option("-a", "--with-admin",
                  action="store_true",
                  default=False,
                  help="enable /admin calls (authorized to admin users "
                  "only)"
                  ),
    config.Option("-e", "--eventlet",
                  action="store_true",
                  default=False,
                  help="use the eventlet server (recommended in "
                  "production)"
                  ),
    config.Option("--backdoor-port",
                  default=None,
                  help='port for eventlet backdoor to listen'
                  ),
    #
    # Queue Options
    #
    config.Option("--eager",
                  action='store_true',
                  default=False,
                  help="All celery (queue) tasks will be executed "
                  "in-process. Use this for debugging only. There is no "
                  "need to start a queue instance when running eager.",
                  env="CHECKMATE_CELERY_ALWAYS_EAGER"
                  ),
    config.Option("--worker",
                  action="store_true",
                  default=False,
                  help="Start the celery worker in-process as well"
                  ),

    #
    # Blueprint handling (CrossCheck functionality)
    #
    config.Option("--webhook",
                  action="store_true",
                  default=False,
                  help="Enable blueprints GitHub webhook responder"
                  ),
    config.Option("-g", "--github-api",
                  help="Root github API uri for the repository "
                       "containing blueprints. "
                       "ex: https://api.github.com/v3",
                  env="CHECKMATE_GITHUB_ENDPOINT",
                  ),
    config.Option("-o", "--organization",
                  help="The github organization owning the "
                       "blueprint repositories",
                  default="Blueprints"
                  ),
    config.Option("-r", "--ref",
                  help="Branch/tag/reference denoting the version of "
                  "blueprints to use.",
                  default="master"
                  ),
    config.Option("--cache-dir",
                  help="blueprint cache directory"
                  ),
    config.Option("--blueprint-cache-expiration",
                  env="CHECKMATE_BLUEPRINT_CACHE_EXPIRE",
                  ),
    config.Option("--preview-ref",
                  help="version of deployment templates for preview",
                  default=None
                  ),
    config.Option("--preview-tenants",
                  help="preview tenant IDs",
                  type=config.comma_separated_strings,
                  default=None
                  ),
    config.Option("--group-refs",
                  help="Auth Groups and refs to associate with them as "
                  "a comma-delimited list. Ex. "
                  "--group-refs tester=master,prod=stable",
                  type=config.comma_separated_pairs,
                  default=None
                  ),
    #
    # Networking
    #
    config.Option("--github-token",
                  help="Token for GitHub Auth."
                  ),
    config.Option("--github-client-id",
                  help="Github Client ID for Github Auth"
                  ),
    config.Option("--github-client-secret",
                  help="Github Client Secret for Github Auth"
                  ),
    config.Option("--github-use-https",
                  action="store_true",
                  default=False,
                  help="Communicate with GitHub over https."
                  ),
    config.Option("--bastion-address",
                  help="Bastion address for SSH/NetBIOS commands",
                  default=None
                  ),
    config.Option("--bastion-username",
                  help="Username for bastion access",
                  default=None
                  ),
    config.Option("--bastion-key-filename",
                  help="SSH Key file for bastion access",
                  default=None,
                  env="CHECKMATE_BASTION_PKEY_FILE",
                  ),
    config.Option("--bastion-password",
                  help="SSH password for bastion access",
                  default=None
                  ),
    config.Option("--knife-bastion-suffix",
                  help="A suffix to add to host name to route knife "
                  "calls through a ~/.ssh/config rule",
                  default=None
                  ),

]


class Config(config.Config):

    """Implements config and extends it with logging setup."""

    @property
    def log_level(self):
        """Get debug settings from arguments.

        --debug: turn on additional debug code/inspection (implies
                 logging.DEBUG)
        --verbose: turn up logging output (logging.DEBUG)
        --quiet: turn down logging output (logging.WARNING)
        default is logging.INFO
        """
        if self.debug is True:
            return logging.DEBUG
        elif self.verbose is True:
            return logging.DEBUG
        elif self.quiet is True:
            return logging.WARNING
        else:
            return logging.INFO

    @property
    def bottle_parent(self):
        """Detect if running as a bottle autoreload parent."""
        return (self.eventlet is False and 'BOTTLE_CHILD' not in os.environ
            and self.bottle_reloader)

    def init_logging(self, default_config=None):
        """Configure logging based on log config file.

        Turn on console logging if no logging files found

        :param config: object with configuration namespace (argparse parser)
        """
        if self.logconfig and os.path.isfile(self.logconfig):
            logging.config.fileConfig(self.logconfig,
                                      disable_existing_loggers=False)
        elif default_config and os.path.isfile(default_config):
            logging.config.fileConfig(default_config,
                                      disable_existing_loggers=False)
        else:
            self.init_console_logging()

    def get_debug_formatter(self):
        """Get debug formatter based on configuration.

        :param config: configurtration namespace (ex. argparser)

        --debug: log line numbers and file data also
        --verbose: standard debug
        --quiet: turn down logging output (logging.WARNING)
        default is logging.INFO
        """
        if self.debug is True:
            return DebugFormatter('%(pathname)s:%(lineno)d: %(levelname)-8s '
                                  '%(message)s')
        elif self.verbose is True:
            return logging.Formatter(
                '%(name)-30s: %(levelname)-8s %(message)s')
        elif self.quiet is True:
            return logging.Formatter('%(message)s')
        else:
            return logging.Formatter(logging.BASIC_FORMAT)

    def init_console_logging(self):
        """Log to console."""
        # define a Handler which writes messages to the sys.stderr
        console = find_console_handler(logging.getLogger())
        if not console:
            console = logging.StreamHandler()
        logging_level = self.log_level
        console.setLevel(logging_level)

        # set a format which is simpler for console use
        formatter = self.get_debug_formatter()
        # tell the handler to use this format
        console.setFormatter(formatter)
        # add the handler to the root logger
        logging.getLogger().addHandler(console)
        logging.getLogger().setLevel(logging_level)
        global LOG  # pylint: disable=W0603
        LOG = logging.getLogger(__name__)  # reset

    def display(self):
        """Generate a formatted representation attempting to hide secrets."""
        clean = utils.scrub_data(self._values)
        return "Config:\n\t%s" % '\n\t'.join([
            '%s%s' % (k.ljust(30), v) for k, v in sorted(clean.iteritems())])

    def __repr__(self):
        """Generate a scrubbed representation attempting to hide secrets."""
        clean = utils.scrub_data(self._values)
        return "<Config %s>" % ', '.join([
            '%s=%s' % (k, v) for k, v in clean.iteritems()])


class DebugFormatter(logging.Formatter):

    """Log formatter.

    Outputs any 'data' values passed in the 'extra' parameter if provided.
    """

    def format(self, record):
        """Print out any 'extra' data provided in logs."""
        if hasattr(record, 'data'):
            return "%s. DEBUG DATA=%s" % (
                logging.Formatter.format(self, record),
                record.__dict__['data'])
        return logging.Formatter.format(self, record)


def find_console_handler(logger):
    """Return a stream handler, if it exists."""
    for handler in logger.handlers:
        if (isinstance(handler, logging.StreamHandler) and
                handler.stream == sys.stderr):
            return handler

checkmateini = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, 'checkmate.cfg'))
CURRENT_CONFIG = Config(options=OPTIONS, ini_paths=[checkmateini])


def current():
    """Return global current config object.

    Usage:

        from checkmate.common import config
        CONFIG = config.current()

    To update the config:
        CONFIG.update({'setting': "value"})

    To load config from sys.args and environment variables:
        CONFIG.initialize()
    """
    return CURRENT_CONFIG
