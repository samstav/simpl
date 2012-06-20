"""Aliases for imports are used as keys in the environment definition

Defines:
chef_local   - chef-solo configuration provider (no chef server needed)
chef_server  - configuration provider using Chef server

Explanation:

environment:
  providers:
    chef-server:
      provides:
      - configuration
      vendor: opscode

From vendor and provider key (chef-server) above, the class
'checkmate.providers.opscode.chef_server' will be loaded
"""
from checkmate.providers.opscode.configuration_management \
    import LocalProvider as chef_local, ServerProvider as chef_server
