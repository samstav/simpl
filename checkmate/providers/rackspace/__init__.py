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
    nova:
      provides:
      - compute
      vendor: rackspace

"""


def register_providers():
    import checkmate.providers.rackspace.compute
    import checkmate.providers.rackspace.loadbalancer
    import checkmate.providers.rackspace.database
    import checkmate.providers.rackspace.dns


register_providers()
