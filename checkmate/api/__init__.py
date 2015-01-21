# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
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

"""REST API for Checkmate server."""

import logging
import os

import bottle  # noqa

import checkmate  # noqa
from checkmate.common import config
from checkmate import environments  # noqa
from checkmate import utils
from checkmate import workflows  # noqa

CONFIG = config.current()
LOG = logging.getLogger(__name__)


#
# Status and System Information
#
@bottle.get('/version')
def get_api_version():
    """Return api version information."""
    accept = bottle.request.get_header('Accept', ['application/json'])
    if 'application/vnd.sun.wadl+xml' in accept:
        return bottle.static_file('application.wadl',
                                  root=os.path.dirname(__file__),
                                  mimetype='application/vnd.sun.wadl+xml')

    LOG.debug('GET /version called and reported version %s',
              checkmate.__version__)
    results = {
        "version": checkmate.__version__,
        "environment": CONFIG.app_environment,
        "git-commit": checkmate.__commit__,
        "wadl": "./version.wadl",
    }
    if not results['git-commit']:
        hashfile = os.path.abspath(os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            os.pardir, 'commit.txt'))
        if os.path.isfile(hashfile):
            with open(hashfile) as head:
                results['git-commit'] = head.read().strip()
    if not results['git-commit']:
        # dont be a heartbreaker
        results.pop('git-commit')

    return utils.write_body(results, bottle.request, bottle.response)
