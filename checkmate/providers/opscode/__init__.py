"""OpsCode Providers

Defined:
chef-server  - configuration provider using Chef server

Explanation:

environment:
  providers:
    chef-server:
      provides:
      - application: wordpress
      - application: drupal
      vendor: opscode

"""

from checkmate.providers import register_providers


def register():
    from checkmate.providers.opscode.server import Provider as server
    from checkmate.providers.opscode.solo import Provider as solo
    register_providers([server, solo])
