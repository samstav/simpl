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

"""OpsCode Providers.

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

import urlparse

from checkmate.providers import register_providers


def register():
    from checkmate.providers.opscode.server import Provider as server
    from checkmate.providers.opscode.solo import Provider as solo
    register_providers([server, solo])


def register_scheme(scheme):
    """Use this to register a new scheme with urlparse.

    New schemes will be parsed in the same way as http is parsed
    """
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly
