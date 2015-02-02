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

"""Checkmate Server.

Note: To support running with a wsgiref server with auto reloading and also
full eventlet support, we need to handle eventlet up front. If we are using
eventlet, then we'll monkey_patch ASAP. If not, then we won't monkey_patch at
all as that breaks reloading.
"""

from __future__ import print_function

__title__ = 'checkmate'
__version__ = '2.0.0'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright Rackspace US, Inc. (c) 2011-2015'
__url__ = 'https://github.com/checkmate/checkmate'

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

import gettext
import os


# This installs the _(...) function as a built-in so all other modules
# don't need to.
gettext.install('checkmate')


def print_banner(role):
    """Print the start-up banner to stdout."""
    if not os.environ.get('BOTTLE_CHILD'):
        print("\n*** Starting Checkmate %s v%s Commit %s ***\n"
              % (role, __version__, __commit__[:8]))


def _get_commit():
    """Get HEAD commit sha-1 hash from .git/HEAD ."""
    cfd = os.path.dirname(os.path.realpath(__file__))
    dotgitpath = os.path.abspath(os.path.join(cfd, os.pardir, ".git"))
    if not os.path.exists(dotgitpath):
        return ''
    headfile = os.path.join(dotgitpath, 'HEAD')
    if not os.path.isfile(headfile):
        return ''
    with open(headfile) as head:
        headref = head.read().strip()
        if 'ref:' in headref:
            headref = headref.partition('ref:')[-1].strip()
        elif len(headref) == 40:
            return headref
        else:
            raise StandardError(
                "Cannot read %s for HEAD sha-1."
                % os.path.join(dotgitpath, 'HEAD'))
    headreffile = os.path.join(dotgitpath, headref)
    if not os.path.isfile(headreffile):
        return ''
    with open(headreffile) as href:
        return href.read().strip()

__commit__ = _get_commit()
