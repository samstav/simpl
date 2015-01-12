## Checkmatefile Design

A Checkmatefile is a file, typically written in YAML, that defines an
application and how it is deployed.

Full Checkmatefile examples are available on
[Rackspace github](https://github.rackspace.com/Blueprints). The current schema
version is v0.7

### Table of Contents

In a Checkmatefile there are several sections:

* [blueprint](#the-blueprint-section)
  * [services](#services)
  * [components](#components)
  * [options](#options)
  * [resources](#resources)
  * [meta](#meta)
  * [display-outputs](#display-outputs)
* [inputs](#the-inputs-section)
* [environment](#the-environment-section)

##### The `blueprint` section

Imagine the blueprint section as a whiteboard that you are using to draw your
generalized application architecture:

![whiteboard](img/whiteboard.jpg)

The blueprint section is made up of several subsections:

###### Services
Services are the boxes on your virtual whiteboard and how they relate to each
other. A catalog of all available services (and their default options) is
available
[here](https://github.com/checkmate/checkmate/blob/master/ui/rook/static/scripts/common/services/catalog.yml).

###### Components

* What is inside the boxes (web, database, application, cache)
* These components have sane defaults set
* Custom components are possible

An example component, under the `appserver` service:

* type: Describes the component based on a list of primitives (compute,
  application, database, load-balancer)  
* name: Arbitrary name for the the component.
* role: Role of the component
* relations: How this component connects to others in the blueprint.
* constraints: Optional constraints applied at the provider level (ex.
  region=DFW).

```yaml
appserver:
  component:
    type: application
    name: django
    role: app_srvr
    relations:
      backend: mysql
    constraints:
      - omnibus-version: "11.8.2"
```

###### Options

Choices presented to the user launching the deployment. The options will most
likely be the bulk of the Checkmatefile.

* OS, memory, flavor, disk, domain, etc.

An example options section, with several types (choice, constrains,
constraints):

```yaml
options:
  region:
    label: Region
    type: string
    required: true
    default: DFW
    display-hints:
      group: deployment
      list-type: region
      choice:
        - DFW
        - ORD
        - LON
        - SYD
        - IAD
        constrains:
          - setting: region
  server_count:
    label: Server Count
    type: integer
    required: true
    default: 2
    display-hints:
      group: server
      order: 1
      constraints:
        - greater-than-or-equal-to: 1
        message: must build at least one server
        - less-than-or-equal-to: 25
        message: maximum of 25 allowed
        constrains:
          - setting: count
          service: appserver
          resource_type: application
  os:
    label: Operating System
    type: string
    default: Ubuntu 12.04
    display-hints:
      group: server
      order: 2
      list-type: compute.os
      choice:
      - name: Ubuntu 12.04 LTS (Precise Pangolin)
      value: Ubuntu 12.04
      - name: CentOS 6.5
      value: CentOS 6.5
      constraints:
      - in: ["Ubuntu 12.04", "CentOS 6.5"]
    constrains:
    - setting: os
    resource_type: compute
    service: appserver
```

When creating an option for a password, several values are available:

**default**: The default value to use. YAML will assume numbers are ints, so
enclose strings in "quotation marks" as a best practice. Special values for this
are `=generate_password()` which will generate a random password on the server.
Several parameters can be passed to `generate_password()`:

- `min_length=<integer>`: a number representing the minimum number of characters
  in the password. If `max_length` is not specified the password will be
  `min_length` characters.
- `max_length=<integer>`: a number representing the maximum number of characters
  in the password. If `min_length` is not also specified the password will be
  `max_length` characters. If both `min_length` and `max_length` are specified
  the password length will be chosen at random from the specified range.  The
  maximum length allowed is 255 characters.
- `required_chars=["<string1>", "<string2>", ..."<stringN>"]`: the generated
  password will contain one character from each string in the set. A string can
  be duplicated to require more than one character from the same set.
- `starts_with="<string>"`: for use when the first password character should be
  restricted to a set of characters. Defaults to all alphanumeric characters.
  Pass `starts_with=None` to override this behavior.
- `valid_chars`: the set of characters that should be used for all but
  `starts_with` and `required_chars` chars. `valid_chars` can contain duplicates
  of the characters specified in both `starts_with` and `required_chars`.
  Defaults to all alphanumeric characters.

Here is an example password option:

```yaml
options:
  password:
    label: Admin Password
    type: password
    description: Password to use to administer your deployment.
    default: '=generate_password(min_length=6, required_chars=["0123456789", "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"])'
    constraints:
    - regex: '^(?=.*).{6,15}$'
      message: must be between 6 and 15 characters long
    - regex: '^(?=.*\d)'
      message: must contain a digit
    - regex: '^(?=.*[a-z])'
      message: must contain a lower case letter
    - regex: '^(?=.*[A-Z])'
      message: must contain an upper case letter
```

Options of type url provide some advanced handling of common url use cases. The
option can be used simply as a string that accepts a url. In this case, the only
benefit of setting the type to url is that a client application can perform
certain validation to make sure the provided value is a valid URL (according to
[RFC 3986](http://tools.ietf.org/html/rfc3986)). Example:

```yaml
option:
  my_web_site:
    type: url
```

It is useful, however, to be able to handle different parts of a URL (i.e the
scheme or protocol, domain, path, port, username, password, etc...) separately.
They may be validated independently (e.g. make sure the protocol is http or
https only). The parts may be wired up to different parts of the blueprint using
constraints (e.g. use the domain part for a dns setting). The way that is
supported is that the url type has attributes that can be accessed in the
Checkmatefile or other parts of Checkmate. These attributes are:

* scheme: this is the first part of the URL
* protocol: this is the first part of the URL as well (an alias to scheme)
* netloc: the dns name or address part
* port: this is the port if specified (e.g. the port in http://localhost:8080 is
  8080)
* path: the path of the resource or file
* private_key: the private_key of a certificate to use if the protocol is an
  encrypted one
* certificate: the public_key of a certificate to use if the protocol is an
  encrypted one
* intermediate_key: the intermediate key chain of a certificate to use if the
  protocol is an encrypted one

These attributes can be specified in constraints:

```yaml
options:
  my_url:
    label: Site Address
    type: url
    constraints:
    - protocols: [http, https]
    constrains:
    - type: load-balancer
      service: lb
      attribute: protocol  # This picks out the 'http' or 'https' part of the URL
      setting: protocol
    - type: compute
      service: web
      attribute: "private_key"  # This picks out the cert
      setting: ssl_certificate
    - type: compute
      service: web
      attribute: "intermediate_key"  # This picks up the intermediate cert
      setting: ssl_intermediate_certificate
```

You can constrain a list of protocols using the `protocols` constraint.

```yaml
options:
  my_url:
    label: Site Address
    type: url
    constraints:
    - protocols: [http, https]
```

Supported constraints are:

* `greater-than`: self-explanatory (for strings or integers)
* `less-than`: self-explanatory (for strings or integers)
* `greater-than-or-equal-to`: self-explanatory (for strings or integers)
* `less-than-or-equal-to`: self-explanatory (for strings or integers)
* `min-length`: for strings or text
* `max-length`: for strings or text (including URLs)
* `allowed-chars`: for strings and text types. Ex. "ABCDEFGabcdefg012345657!&@"
* `required-chars`: for strings and text types. Ex. "ABCDEFG"
* `in`: a list of acceptable values (these could also be used by clients to
  display drop-downs)
* `protocols`: unique to URL types. This lists allowed protocols in the URL.
  See also display-hints for `encrypted-protocols`
* `regex`: do not use look-forward/behind. Keep these simple so they are
  supported in javascript (client) and python (server). While many of the above
  can also be written as regex rules, both are available to blueprint authors
  to use the one that suits them best.
* `check`: evaluates a constraint using constructs like "if", "if-not",
  "and", etc...

And there are special display-hints used to aid a client in rendering and
validating the url. These are `encrypted-protocols` and
`always-accept-certificates` which are documented in constraints.

When supplying the value for a url as an input, it can be supplied as a string
or as a mapping with attributes.

As a string it would be `my_site_address: https://mydomain.com/blog`.

As a mapping:

```yaml
inputs:
  my_url:
    url: https://domain.com/path
    private_key: |
      -----BEGIN...
    intermediate_key: |
      -----BEGIN...
    certificate: |
      -----BEGIN...
```

Note:  A common use case is to supply the url and keys. A shortcut is available
that accepts a key called `url` that can be used to supply the url without having
to provide all the components of the url.

###### Resources

Static resources to be created and shared across the Checkmatefile. For
example: users, passwords, or SSH keys:

```yaml
resources:
  django_admin:
    type: user
    constrains:
      - setting: django_admin_user
      service: appserver
      resource_type: application
      attribute: name
      - setting: django_admin_pass
      service: appserver
      resource_type: application
      attribute: password
```

###### Meta

* id (random UUID)
* version (semver number for your use)
* meta-data (documentation for the deployment.)

###### Display Outputs

Display outputs is how a Checkmatefile author determines what information to
provide to the end user to be able to use the deployment (credentials, urls,
etc).

Display outputs can be specified in three ways:

1 - under a component in blueprint services

```yaml
service:
    database:
    component:
      display-outputs:
        "Password":
          label:"blah"
          order: 1
          source: mysql://passwd
```

2 - in a blueprint option by setting `display-output` to the boolean value
`true`.

```yaml
options:
    "AdminUser":
       display-output: true
```

3 - as a map under blueprint

```yaml

blueprint:
  display-outputs:
    "Site Address":
      type: url
      source: options://url
      extra-sources:
        ipv4: "resources://instance/vip?resource.service=lb&type=resource.load-balancer"
      order: 1
      group: application
    "Admin Username":
      type: string
      source: options://username
      order: 2
      group: application
    "Admin Password":
      type: password
      source: options://password
      order: 3
      group: application
    "Private Key":
      type: private-key
      source: "resources://instance/private_key?resource.index=deployment-keys"
      order: 4
      group: application
    "Database Username":
      source: options://db_username
      order: 5
      group: database
    "Database Password":
      type: password
      source: options://db_password
      order: 6
      group: database
    "Database Host":
      source: "resources://instance/interfaces/mysql/host?resource.service=db&resource.type=compute"
      order: 7
      group: database
```

***Syntax for Display Outputs***

The syntax is:

```
{root}://{path}

root = "options" | "resources" | "services"
path = [/keys]/result (ends with value to return)
```

Examples:

```
# Get the value of the 'url' option
source: options://url

# Get the private_key of the 'url' option
source: options://url/private_key

# Get the private_key of the deployment keys
source: "resources://deployment-keys/instance/private_key"

# Get the database password
source: "services://db/interfaces/mysql/datebase_password"
```

```yaml
# under deployment
display-outputs:
  Site Address:
    type: url
    uri: http://example.com/
    extra-info:
      ipv4: 4.4.4.204
    order: 1
    group: application
  Admin Username:
    type: string
    value: john
    order: 2
    group: application
  Admin Password:
    type: password
    value: w34ot8how87h34t
    order: 3
    group: application
  Private Key:
    type: private-key
    value: |
      -----BEGIN RSA PRIVATE KEY-----
      MIIEpAIBAAKCAQEAu1R+vwvUR3o5rQa6ny79OlhLT2qWYY0xKVg5bxW0DGKhn/6e
      gI8yWSf9kUmbEWdO1xuQiEiMnAA2wY0w+TXHCNkCX305shCGL/ejt4XrPLloK7c6
      anCS2MTdcDUjppeHhhNi7TdotN9E5wxY8x1IBtioCldNVIkJVwZMhiMORteGpOZ2
      DV+OZ2GquZKrrrRN9tJtIwMMbqjVno1k3Lz3iJfvRZn4D5xZFSd/lgTp+H0bpc4o
      9kS9Z4k44l9chMvZItGjAgwQ07ORny5cPnKCAPewO+F20ng+WT19KerGWQq/58T3
      -----END RSA PRIVATE KEY-----
    order: 4
    group: application
```

Additional Information:

- We identify and separate sensitive data (passwords, private keys) from
  non-sensitive data so a client can choose to handle them differently.
- There is an API to destroy sensitive data so future clients can be prevented
  from accessing the data.
- Destruction of sensitive data does not block Checkmate from accessing the
  resources itself for future operations. Ther only way to completely remove
  sensitive data from checkmate is to delete the deployment.
- Given we are looking to having blueprints become components that can be
  included in other blueprints, the keyword `outputs` will probably be used for
  generating the outputs in that case. So the key for this is called
  `display-outputs` and is optional.

Sample Checkmatefiles (with complete blueprint sections) are available
[here](https://github.rackspace.com/Blueprints).

###### The `inputs` section

When launching a deployment, the values selected for options are stored as an
*input* to the deployment under the 'inputs' key. Inputs can be applied at
multiple levels in the deployment hierarchy as follows:

**Global inputs (apply to everything):**

```yaml
inputs:
  domain: mydomain.com
```

**Blueprint inputs (apply to a setting on the blueprint):**

```yaml
inputs:
  blueprint:
    domain: mydomain.com
```

**Service inputs (apply to a particular service in the blueprint):**

```yaml
inputs:
  services:
    "backend":
      use_encryption: true
```

**Provider inputs (apply to a provider and any resourcers that
  provider provides):**

```yaml
inputs:
  providers:
    'legacy':
      region: dallas
```

**Resource type inputs. These can be applied under services or
providers as follows:**

```yaml
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

```yaml
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

#### The `environment` section

The environment section defines WHERE you want to launch your deployment. It
could be your development laptop, a cloud provider, or a combination of cloud
providers that you have grouped together to use together as a single
environment.

Multiple environments can exist in one tenant or account. For example, you
could have dev, test, staging, and production environments defined on one
Rackspace Cloud account. Checkmate will manage which resources belong in which
environment under a tenant using its own database, naming conventions, and tags.

```yaml
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
          - application: http
          - database: mysql
```
