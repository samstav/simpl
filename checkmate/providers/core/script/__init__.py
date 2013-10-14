# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#
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
"""Script configuration management provider.

Sample:

environment:
  name: Rackspace Open Cloud
  providers:
    script:
      vendor: core
      catalog:
        application:
          openstack:
            provides:
            - application: http
            requires:
            - host: linux
            properties:
              scripts:
                install: |
                  apt-get update || yum update -y
                  apt-get install -qqy git || yum install -y git
                  git clone https://github.com/openstack-dev/devstack.git
                  cd devstack
                  echo 'ADMIN_PASSWORD=simple' > localrc
                  echo 'MYSQL_PASSWORD=simple' >> localrc
                  echo 'RABBIT_PASSWORD=simple' >> localrc
                  echo 'SERVICE_PASSWORD=simple' >> localrc
                  echo 'SERVICE_TOKEN=1111' >> localrc
                  ./stack.sh > stack.out
                verify: "ls /opt/devstack"
                delete:
                    parameters:
                      node_ip: resources://0/instance/ip
                    template:
                      "rm -rf /opt/devstack"


Syntax options for script:
  if a string is supplied, it is executed as a command-line script
  if an array is supplied, it is treated as multiple entries and executed as
      multiple scripts
  if an object is supplied, the following values are allowed/supported:

      parameters: used to replace entries in the script body. URL syntax
          similar to display-outputs can be used to obtain values from a
          deployment. Examples:

              # Get the value of the 'url' option
              source: options://url

              # Get the private_key of the 'url' option
              source: options://url/private_key

              # Get the private_key of the deployment keys
              source: "resources://deployment-keys/instance/private_key"

              # Get the database password
              source: "services://db/interfaces/mysql/datebase_password"

              # Specific resource IP
              resources://instance/ip?resource.service=lb&resource.type=compute

      template: a template to parse (=include() can be used to load a file from
          a path or url

      body: the final parsed/processed body (=include() can also be used).
      file-type:

      powershell, python, bash, bat, etc... to describe file type.
      Ex.
      powershell: |
        # ...


"""

# flake8: noqa
from checkmate.providers.core.script.provider import Provider
from checkmate.providers.core.script.manager import Manager
