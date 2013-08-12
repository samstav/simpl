"""Openstack Providers

Defined:
identity      - OpenStack-compatible identity

"""

from checkmate.providers import register_providers as rps


def register():
    from checkmate.providers.openstack.compute import Provider as compute
    rps([compute])
