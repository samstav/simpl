# Copyright (c) 2011-2013 Rackspace Hosting
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

# pylint: disable=C0103,W0603
"""Checkmate Server.

Note: To support running with a wsgiref server with auto reloading and also
full eventlet support, we need to handle eventlet up front. If we are using
eventlet, then we'll monkey_patch ASAP. If not, then we won't monkey_patch at
all as that breaks reloading.
"""
# BEGIN: ignore style guide
# monkey_patch ASAP if we're using eventlet
import sys
try:
    import eventlet
    if '--eventlet' in sys.argv:
        eventlet.monkey_patch(socket=True, thread=True, os=True)
    else:
        # Only patch socket so that httplib, urllib type libs are green
        eventlet.monkey_patch(socket=True)
except ImportError:
    pass  # OK if running setup.py or not using eventlet somehow
# END: ignore style guide

import ConfigParser
import gettext
import os

from checkmate.common import config

# This installs the _(...) function as a built-in so all other modules
# don't need to.
gettext.install('checkmate')

config.CURRENT_CONFIG.initialize()


def _read_version():
    configfile = os.path.join(os.path.dirname(__file__), 'checkmate.cfg')
    parser = ConfigParser.ConfigParser()
    parser.read(configfile)
    return parser.get("checkmate", "version")

__version__ = _read_version()


def version():
    """Return checkmate server version as a string."""
    return __version__
