## Checkmatefile Design

A Checkmatefile is a file, typically written in YAML, that defines an
application and how it is deployed.

A catalog of all available components (and their default options) is available
[here](https://github.com/checkmate/checkmate/blob/master/ui/rook/static/scripts/common/services/catalog.yml).

Full Checkmatefile examples are available on
[Rackspace github](https://github.rackspace.com/Blueprints).

In a Checkmatefile there are several sections:

##### The `blueprint` section

Imagine the blueprint section as a whiteboard that you are using to draw your
generalized application architecture:

![whiteboard](img/whiteboard.jpg)

The blueprint section is made up of several subsections:

* Services
  * The boxes on your virtual whiteboard and how they relate to each other.
* Components
  * what is inside the boxes (web, database, application, cache)
  * these components have sane defaults set
* Options
  * choices presented to the user launching the deployment
  * OS, memory, flavor, disk, domain, etc.
* id (random UUID)
* version (semver number for your use)
* meta-data (documentation for the deployment.)

An example blueprint section:

```
blueprint:
  id: 12345
  name: "magentostack-cloud"
  description: "Magento Community Edition installed using Cloud Datastores"
  version: 1.0.0
  services:
    lb:
      component:
        interface: http
        type: load-balancer
        constraints:
        - algorithm: ROUND_ROBIN
      relations:
      - magento: http
      display-name: Load Balancer
  'magento':
    component:
      name: magento
      resource_type: application
      role: master
    constraints:
    - setting: count  # used for manual scaling
      greater-than-or-equal-to: 1
      less-than: 9
    relations:
    - data: mysql
    - session-cache: redis#sessions
    - object-cache: redis#objects
  'data':
    component:
      resource_type: database
      interface: mysql
      id: mysql_database
  'session-cache':
    component:
      resource_type: cache
      interface: redis
      id: redis_cache
  'object-cache':
    component:
      resource_type: cache
      interface: redis
      id: redis_cache
```

##### The `environment` section

The environment section defines WHERE you want to launch your deployment. It
could be your development laptop, a cloud provider, or a combination of cloud
providers that you have grouped together to use together as a single
environment.

Multiple environments can exist in one tenant or account. For example, you
could have dev, test, staging, and production environments defined on one
Rackspace Cloud account. Checkmate will manage which resources belong in which
environment under a tenant using its own database, naming conventions, and tags.

    environment: &cloud_staging
      name: Rackspace Cloud US - staging
      providers:
        nova:
          vendor: rackspace
          provides:
          - compute: linux
          - compute: windows
          constraints:
          - region: ORD
        load-balancer:
          vendor: rackspace
          provides:
          - loadbalancer: http
        database:
          vendor: rackspace
          provides:
          - database: mysql
        chef-solo:
          vendor: opscode
          provides:
          - application: http  # see catalog for list of apps like wordpress, drupal, etc...
          - database: mysql  # this is mysql installed on a host

##### The `inputs` section

When launching a deployment, the values selected for options are stored as an
*input* to the deployment under the 'inputs' key. Inputs can be applied at
multiple levels in the deployment hierarchy as follows:

**Global inputs (apply to everything):**

```
inputs:
  domain: mydomain.com
```

**Blueprint inputs (apply to a setting on the blueprint):**

```
inputs:
  blueprint:
    domain: mydomain.com
```

**Service inputs (apply to a particular service in the blueprint):**

```
inputs:
  services:
    "backend":
      use_encryption: true
```

**Provider inputs (apply to a provider and any resourcers that
  provider provides):**

```
inputs:
  providers:
    'legacy':
      region: dallas
```

**Resource type inputs. These can be applied under services or
providers as follows:**

```
inputs:
  services:
  "backend":
    'database':
      'memory': 512 Mb
  providers:
    'nova':
      'compute':
        'operating-system': Ubuntu 12.04 LTS
```

**Custom Resources inputs. These can be applied under
`custom_resources` to describe an array of existing resources (e.g.
  when importing existing servers into Checkmate):**

```
inputs:
  custom_resources:
  - example_resource1:
    type: server
    provider: nova
    status: ACTIVE
    instance:
      id: 2098383
      private_ip: 10.10.1.1
      public_ip: 2.2.2.18
      flavor: 1
      image: 119
      dns-name: srv1.stabletransit.com
  - example_resource2:
    type: database
```
