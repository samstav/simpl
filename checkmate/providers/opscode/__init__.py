"""OpsCode Providers

Defined:
chef-local   - chef-solo configuration provider (no chef server needed)
chef-server  - configuration provider using Chef server

Explanation:

environment:
  providers:
    chef-server:
      provides:
      - configuration
      vendor: opscode

"""


def register_providers():
    import checkmate.providers.opscode.configuration_management


register_providers()
