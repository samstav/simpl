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

from checkmate.providers import register_providers as rps

# for celery
import checkmate.providers.os_auth.identity

def register():
    from checkmate.providers.rackspace.compute_legacy import (
        Provider as legacy)
    from checkmate.providers.rackspace.compute import (
        Provider as nova)
    from checkmate.providers.rackspace.loadbalancer import (
        Provider as loadbalancer)
    from checkmate.providers.rackspace.database import Provider as database
    from checkmate.providers.rackspace.dns import Provider as dns
    from checkmate.providers.rackspace.files import Provider as files
    from checkmate.providers.os_auth.identity import os_authenticate as auth
    rps([legacy, nova, loadbalancer, database, dns, files, auth])
