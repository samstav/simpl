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

"""Rackspace Providers

Defined:
nova          - openstack, next-gen compute provider
legacy        - legacy, slice compute provider
databases     - Cloud Databases database provider
loadbalancer  - Cloud LoadBalancers load-balancer provider
dns           - Cloud DNS

Sample use:

environment:
  providers:
    legacy:
      provides:
      - compute: linux
      - compute: windows
      vendor: rackspace
"""

from checkmate.providers.rackspace.database import tasks
from checkmate.providers.rackspace.block import tasks


def register():
    """Register Provider classes."""
    from checkmate.providers import base
    from checkmate.providers.rackspace.compute import (
        Provider as nova)
    from checkmate.providers.rackspace.compute_legacy import (
        Provider as legacy)
    from checkmate.providers.rackspace.database.provider import Provider as db
    from checkmate.providers.rackspace.dns.provider import Provider as dns
    from checkmate.providers.rackspace.files import Provider as files
    from checkmate.providers.rackspace.loadbalancer import (
        Provider as loadbalancer)
    from checkmate.providers.rackspace.mailgun import Provider as mg
    from checkmate.providers.rackspace.block.provider import Provider as block

    base.register_providers(
        [block, legacy, nova, loadbalancer, db, dns, files, mg])
