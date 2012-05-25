"""Aliases for imports are used as keys in the environment definition

Defines:
nova         - openstack, next-gen compute provider
legacy       - legacy, slice compute provider
database     - Cloud Databases database provider
loadbalancer - Clud LoadBalancers load-balancer provider

Explanation:

environment:
  providers:
    nova:
      provides:
      - compute
      vendor: rackspace

From vendor and provider key (nova) above, the class
'checkmate.providers.rackspace.nova' will be loaded
"""
from checkmate.providers.rackspace.compute import NovaProvider as nova
from checkmate.providers.rackspace.compute import LegacyProvider as legacy
from checkmate.providers.rackspace.database import Provider as database
from checkmate.providers.rackspace.loadbalancer import Provider as\
        loadbalancer
