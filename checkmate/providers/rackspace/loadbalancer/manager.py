# pylint: disable=E1103
# Copyright (c) 2011-2013 Rackspace Hosting
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

"""
Rackspace Loadbalancer provider manager.
"""
import logging
import pyrax

from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains loadbalancer provider model and logic for interaction."""

    @staticmethod
    def enable_content_caching(lbid, api, simulate=False):
        """Enables content caching on specified loadbalancer."""
        if simulate:
            clb = utils.Simulation(status='ACTIVE')
            clb.content_caching = True
        else:
            try:
                clb = api.get(lbid)
                clb.content_caching = True
            except pyrax.exceptions.ClientException as exc:
                raise exceptions.CheckmateException('ClientException occurred '
                                                    'enabling content caching '
                                                    'on lb %s: %s' % (lbid,
                                                                      exc))
        results = {
            'id': lbid,
            'status': clb.status,
            'caching': clb.content_caching
        }
        return results
