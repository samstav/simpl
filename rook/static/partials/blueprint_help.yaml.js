# description for a blank file
_: |

  id: ...

  name: ...

  blueprint: can be a reference (YAML), but right now, in checkmate, it's a full copy of a blueprint. We'll support references using URI later (git, local references, etc...).
  environment: same as blueprint - right now we make a full copy

  display-outputs: a map of entries of final outputs for a client. TODO: document syntax and implement

  **Action Item**: determine the need for global inputs. Do we really need them? Or at least put them in a "globals" category

  Minimal, canonical deployment (hello world) available [here](https://github.rackspace.com/Blueprints/helloworld/).

  **Action Item**: define how we reference blueprints and environments in deployments without including full copies.  Reference UUID?  URL to file in git or local reference? etc.

  **Action Item**: improve syntax for indicating a generated value, or remove it and let a generated value be the default.  Or create system for code to be included in blueprint to be used to generate, validate values. See artifacts prototype in app.yaml.


  The Checkmate DSL
  -------------

  - YAML and JSON are both first class citizens. We can do all this in JSON, just easier to type and read YAML (for humans, less puntuation). In fact, JSON is a subset of YAML (a YAML parser will understand JSON).
  - A deployment contains a blueprint and an environment. Those can be references or they can be embedded (a copy) in the YAML/JSON.
  - App.yaml contains everything in one file JUST to make it easier to run Checkmate. That's not the typical use case. Typically, users will have existing environments and blueprints and they'll reference those (like in the new deployment screen).
  - Components should come from providers. Component IDs are universal. We'll need a catalog somewhere. Ex. wordpress is wordpress is wordpress....
  - An environment is unique to a user (a.k.a a tenant in our cloud). So each user creates and manages their own environments (they can call them test, dev, QA, prod, etc...)
  - Environment != Region or cloud provider. So I can have test, prod and dev in Rackspace Cloud US, DFW, account 1000. Only Checkmate knows which resource belongs to which environment (i.e. in Next Generation Cloud Control Panel, they're all intermingled). Another example, might be an environment I create which has everything in Rax DFW, except for backups going to AWS S3. Environment is a user-created construct, not necessarily tied to any existing cloud deployment or provider.
  - Blueprints are independent of all the above. They can be shared between tenants. Tenants can create their own (or modify public ones). For example, we might publish a "Best Practice WordPress by Rackspace Blueprint" and anyone can use it.
  - Deployment is a combination of Blueprint, Environment, and a set of parameters (inputs).
  - Provider is a plug-in for Checkmate that understands how to operate a service or system. Ex. the Rackspace Compute Provider knows how to call Rackspace Cloud and create compute resources. The OpsCode Chef Provider knows how to operate chef and apply cookbooks. Not to be confused with cloud providers (lower case).... :-(
  - A blueprint is meant to be created by an "architect". Someone who wants to encode or write down the logic and constraints of a system or app based on their deep knowledge and expertise of all the components of that system. Ex. a WordPress expert would write the Rackspace best Practice Wordpress Blueprint.
  - Simplicity for the user (blueprint architects and deployment end-users) first. It trumps structure, code, DRY, object orientation, etc...
  - It's more acceptable for a deployment to fail than for a blueprint to be complicated to author.


  Current schema version: v0.7


  Schema History
  ==============

  This is the rough history of the Checkmate blueprint schema.

  v0.1 [circa April 2012]:

  - first prototype released
  - providers as a list
  - services as a keys under a blueprint
  - commit 6c74e2ee3f3a91cf3075bbcff7e64c71450b327a

  ```yaml

    deployment:
      blueprint:
          name: Simple Wordpress
          wordpress:
            config: *wordpress  # points to wordpress component
            relations: {db: mysql}
      environment:
            name: rackcloudtech-test
            providers:
            - compute:
              vendor: rackspace
              constraints:
              - region: ORD
            - loadbalancer: &rax-lbaas
            - database: &rax-dbaas
            - common:
              vendor: rackspace
              credentials:
              - rackspace:
                ...
  ```

  v0.2 [May 26 2012]: alpha release

  - providers as keys
  - `provides` and `requires` in components
  - commit 6fdda01fda53f47f7cb11104aa8bd57a0a5a746d

  ```yaml

    deployment:
      environment:
        providers:
          nova:
            provides:
            - compute
            vendor: rackspace
  ```

  v0.3 [July 2012]: beta/v0.1 release

  - services syntax updated at some point
  - canonicalization of names
  - '=generate_...'
  - postbacks

  v0.4 [Fall 2012]: v0.2 released

  - canonicalization of settings (memory instead of flavor)
  - use of catalogs
  - support static resources


  v0.5 []: v0.3 release

  - `attribute` in relations
  - used relations for data routing
  - chef-local

  v0.6 [Jan 2013]: v0.4 release (chef-solo + maps)

  - keyed `provides` and `requires`
  - relation `attribute` deprecated (but suppported)
  - url type

  v0.7: []: Upcoming release (v0.8 of engine)

  - new options syntax
  - blueprint meta-data and schema versioning

  ```yaml

  blueprint:
    id: 0255a076c7cf4fd38c69b6727f0b37ea
    name: Managed Cloud WordPress w/ MySQL on VMs
    meta-data:
      schema-version: 0.7
    services:
      lb:
        component:
          interface: http
          type: load-balancer
          constraints:
          - algorithm: ROUND_ROBIN
        relations:
          web: http
          master: http
      ...
    options:
      url:
        label: Site Address
        description: 'The domain you wish to host your blog on. (ex: example.com)'
        type: url
        required: true
        default: http://example.com/
        display-hints:
          group: application
          order: 1
          encrypted-protocols: [https]
          sample: http://example.com/
        constraints:
        - protocols: [http, https]
        - regex: '^([a-zA-Z]{2,}?\:\/\/[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,6}(?:\/?|(?:\/[\w\-]+)*)(?:\/?|\/\w+\.[a-zA-Z]{2,4}(?:\?[\w]+\=[\w\-]+)?)?(?:\&[\w]+\=[\w\-]+)*)$'
          message: must be a valid web address
        constrains:
        - setting: allow_insecure
          service: lb
          resource_type: load-balancer
          value: true  # turn on HTTP if protocol is HTTPS (provider handles it)
    resources:
      sync-keys:
        type: key-pair
        constrains:
        - setting: private_sync_key
          resource_type: application
          service: master
          attribute: private_key
  ```


# Blueprint Schema Definition
blueprint:
  _: |
    # Blueprint

    A blueprint describes a design that provides an application with certain 'ilities (scalability, availability, etc...). It defines the components, their relationships to each other, and the various constraints on the components and relationships that must be met in order for the application to work as specified.

    For services in a blueprint:
    - one or more services (all under one 'services' entry)
    - arbitrary name for service ID (each one has its own ID)
    - one component per service with the expectation that we'll be able to pull in blueprints as components in the future.
    - relations between services

    Concept: An application is a collection of components that provide a useful capability. An application is distinct from infrastructure.

  id:
    _: unique identifier.
  version:
    _: |

      version: any string determined by the author.

      Note that YAML will auto-detect integer types, so if you want version `1.0` to be a string, enclose it in single or double quotes `'1.0'`

  services:
    _: "Like tiers, but not restricted to the concept of tiers. Currently, there is one component defined per service."
    any:
      _: |
        An arbitrary name used to identify this service.
        Determined by blueprint author.

        Example:
          "my/_wordpress/_thang":"

      display-name:
        _: "This is the display name"

      component:
        _: |
          This is the component that will be used to deliver this service.

          Supply either an id or key/value pairs to help Checkmate find a suitable component when planning a deployment.

          Example of ID short form: wordpress

          component: wordpress

          Example of key/value pair:

          component:
              type: application
              interface: http

          Details
          ==========

          ```yaml

          id: a unique identifier (not necessarily a UUID, but a string) within the provider that provides that component.
              Temporary assertion: the id for wordpress is wordpress always (in puppet, chef, etc....). And we will maintain
              a list of those ids. Precedents for this are OpsCode cookbooks and Juju charms
              (http://jujucharms.com/charms/precise).
              **Action item/future consideration**: create our own catalog (or use Charms/cookbooks)

          name: user friendliness (*mssql vs Microsoft SQL Server)

          role: Allows you to specify the role of this component.
            EX:
            component:
              name: wordpress
                    role: master

          version: for versioning...!

          description: comes from Juju, a short description. (we could have named it description, but decided not to diverge
                       from something already out there...)
                       **Action item**: switch to description from summary, more universally used.

          is: describes the type of resource based on a list of primitives (compute, database, load-balancer, application, ...)
              coming from OpenStack.
              **Unseconded proposal** to change to type.

          requires: what this resource needs. The needs can be specific or general. General would be anything with a mysql
                    interface (for WordPress). Specific would be I need a host compute resource that is an Ubuntu 12.04 or
                    later machine.
          Syntax (two options, long an short form):
              type: interface. Example: database: mysql - short syntax is resource_type:interface. By design.
              name: hash (key/value pairs) for more specific stuff. Name is arbitrary.
              Name key/value example:
                  server: (this is the arbitrary key - the label of this requirement)
                      type: compute
                      interface: debian (this says I expect to be able to do apt-get, vs yum)
                      relation: host (this says I am hosted on this resource. I cannot exist without it. I am down when it is
                                down). "host" is a keyword.
                      constraint:
                      - 'os': ['debian', 'redhat']
          The name+key/value syntax allows for requiring more than one of the same resource (ex. log and data mysql databases)
          as well as adding additional constraints, etc....

          provides: array of resource_type:interface entries (array can be represented in YAML with entries preceded with
          dashes). For example, let's say we get a CLoud Sites API that provides a "site" resource. Site could provide:
          - database: mysql
          - application: php

          options: what settings I can set on this component
          username:
              default: root
              required: optional | required | auto-generated (default: optional)
              type: string (currently we support string, int, boolean) (default: string)
                  * Action Items: How can we tie this to a "list" from the provider
              label: User Name (used for display friendliness)
              description: ...
              source_field_name: the name as it is known by the underlying provider. Ex. wordpress/database/db_user for OpsCode
                                 Chef. We need this currently since we dynamically generate component definitions and we need
                                 to be able to map things back after they've flowed through checkmate.
                  * Should be able to get rid of this in the future with clean, reversible mapping logic in providers.
              type: string
              regex: for validation
              sample: for display, to show what this looks like.
              help: help text.
          password:
          ```

          Note:

              GET /providers
              GET /:tenant_id/environments/:id/providers/:id/catalog/
              - you'll get a list of components grouped by resource type. (You'll also get some additional info called lists).











        interface:
          _: "A primary interface supplied by this service. Allowed interfaces are http, https, ssh, tcp, smtp, etc..."

        resource-type:
          _: "A primary fresource type to use for this service. Examples: application, compute, database, ..."

        type:
          _: "A shortcut for resource-type"

        constraints:
          _type: array
          _: |
            An array of mappings (key/value pairs) in the standard Checkmate constraints syntax. Supported constraints are:

            * _greater-than_: self-explanatory (for strings or integers)
            * _less-than_: self-explanatory (for strings or integers)
            * _greater-than-or-equal-to_: self-explanatory (for strings or integers)
            * _less-than-or-equal-to_: self-explanatory (for strings or integers)
            * _min-length_: for strings or text
            * _max-length_: for strings or text (including URLs)
            * _allowed-chars_: for strings and text types. Ex. "ABCDEFGabcdefg01234565789!&@"
            * _required-chars_: for strings and text types. Ex. "ABCDEFG"
            * _in_: a list of acceptable values (these could also be used by clients to display drop-downs)
            * _protocols_: unique to URL types. This lists allowed protocols in the URL. See also display-hints for `encrypted-protocols`
            * _regex_: do not use look-forward/behind. Keep these simple so they are supported in javascript (client) and python (server). While many of the above can also be written as regex rules, both are available to blueprint authors to use the one that suits them best.

            Example:

              constraints:
              - count: 2

      relations:
        _: |
          Effectively, connections to other services. Examples:
          - wordpress app to mysql database
          - load balancer to webhead

          Two syntaxes for relations; short and long.

          Short syntax: service_name:interface. Example:

              ```my/_db/_thang:mysql```

          Long syntax: arbitrary name, key values. Example:

              ```
              db:
                interface: mysql
                service: my/_db/_thang
              ```

  name:
    _: "This is the name of the blueprint"

  description:
    _: "This is the description of the blueprint"

  display-outputs:
    _: |

      display-outputs: how a blueprint author determines what information to provide to the end user to be able to use the deployment (credentials, urls, etc).

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

      2 - in a blueprint option by setting `display-output` to the boolean value `true`
      ```yaml
      options:
          "AdminUser":
             display-output: true
      ```

      3 - as a map _under the blueprint_

      ```yaml

      blueprint:
        display-outputs: # used to return outputs that the client (Rook, Pawn, Reach) will display to the end-user
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

      ### Syntax

      display-outputs.**source**: use this to specify where the data will come from. Use cases identified so far are under options and resources. I'm proposing using the same URL syntax we are using in the Chefmap with additional enhancements as per discussions on the networking pull request.

      The syntax would be:

          {root}://{path}

          root = "options" | "resources" | "services"
          path = [/keys]/result (ends with value to return)

      Examples:

          # Get the value of the 'url' option
          source: options://url

          # Get the private_key of the 'url' option
          source: options://url/private_key

          # Get the private_key of the deployment keys
          source: "resources://deployment-keys/instance/private_key"

          # Get the database password
          source: "services://db/interfaces/mysql/datebase_password"


      - display-outputs.**extra-sources**: for some types, like URLs, we need to provide additional information like the IP address so that the UI can display things like scripts to set up /etc/hosts. This is a map of key/value where value follows the same syntax as source.

      - display-outputs.**type**: string, integer, url, boolean (same as options)
      - display-outputs.**label**: used by clients and overrides the key the display outputs is created under
      - display-outputs.**order**: for display ordering
      - display-outputs.**group**: for display option grouping
      - display-outputs.**is-secret**: boolean to mark this as a protected piece of data


      When the deployment runs, new map _on the deployemnt_ where the actual display-outputs will be stored is created. These will be used by the client (Rook, Pawn, Reach) to display to the end-user.


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

      - We identify and separate sensitive data (passwords, private keys) from non-sensitive data so a client can choose to handle them differently.
      - There is an API to destroy sensitive data so future clients can be prevented from accessing the data.
      - Destruction of sensitive data does not block Checkmate from accessing the resources itself for future operations. Ther only way to completely remove sensitive data from checkmate is to delete the deployment.
      - Given we are looking to having blueprints become components that can be included in other blueprints, the keyword `outputs` will probably be used for generating the outputs in that case. So the key for this is called `display-outputs` and is optional.

  options:
    _: |

      options: KEY piece (don't forget it!). This lists the options (levers or dials) that the blueprint author is exposing to me. Similar in syntax to component options, but the main difference is in the constraints. See dedicated section on Blueprint Options below.

      ```yaml
      options:
        "database_bigness":
          description: the size of the database
          default: 2GB
          constrains:
          - service: my_database_thang
            setting: memory
          - service: my_database_log_thang
            setting: memory
          display-hints:
            choice:
            - value: 1024
              name: 1gig
            - value: 2048
             name: 2GB
      ```

      Details
      =================
      ## Fields

      Note: this is the schema that is being supported in v0.7 of the engine. The schema had not been formalized, firmed up, or sufficiently validated prior to this. Validation will start to be more aggressive as we proceed towards a v1.0 release of the Checkmate API.

      **label**: the short label to use when displaying the option to the user.
      **description**: A full description of this option (what it is)
      **help**: Detailed help on this option (how to use it)
      **sample**: an example of what the data will look like. This could be shown as the background of a text control.

      **display-hints**: a mapping (key, value pairs) of hints for how to order and display this option in relation to other options
      **....group**: a random group name used to group options together. Note that Reach would use this and would expect one of the following (to be finalized with Reach):
      * _deployment_: this is a deployment option and shows right under the deployment name
      * _application_: this is an application option and shows on the first screen of options
      * _servers_: this is an option that should be shown under the server options section
      * _load-balancer_: this is an option that should be shown under the load balancer options section
      * _database_: this is an option that should be shown under the database options section
      * _dns_: this is an option that should be shown under the dns options section

      **....order**: relative order of this option within its group (as an integer)
      **....list-type**: what is the type of the entries in the list. This is used to identify if it should be a specific resource type and list or attribute. The format is resource-type.list where resource-type is a known Checkmate resource type (compute, database, etc...) and the list is one of the lists from the provider [TODO: define these `lists` more precisely in the DSL or schema. Right now, they exist only in the provider catalogs]. Examples (and what we will initially support):
      * _compute.memory_: list of available compute image sizes
      * _compute.os_: list of available compute operating systems
      * _load-balancer.algorithm_: list of available load balancer algorithms

      **....encrypted-protocols**: The subset of protocols that are encrypted so that we know when to show ssl cert controls. Ex. [https, pop3s]
      **....always-accept-certificates**: if a blueprint always accepts and handles the certificates (especially if the url is entered in free-form supporting any protocol)
      **....default-protocol**: The default protocol to display to the user. If not supplied, clients should default to an unencrypted protocol since it is the simpler option for the user and does not present certificate options which could deter a user from launching the blueprint.

      **default**: The default value to use. YAML will assume numbers are ints, so enclose strings in "quotation marks" as a best practice. Special values for this are `=generate_password()` which will generate a random password on the server. Several parameters can be passed to `generate_password()`:

        - `min_length=<integer>`: a number representing the minimum number of characters in the password. If `max_length` is not specified the password will be `min_length` characters.
        - `max_length=<integer>`: a number representing the maximum number of characters in the password. If `min_length` is not also specified the password will be `max_length` characters. If both `min_length` and `max_length` are specified the password length will be chosen at random from the specified range.  The maximum length allowed is 255 characters.
        - `required_chars=["<string1>", "<string2>", ..."<stringN>"]`: the generated password will contain one character from each string in the set. A string can be duplicated to require more than one character from the same set.
        - `starts_with="<string>"`: for use when the first password character should be restricted to a set of characters. Defaults to all alphanumeric characters. Pass `starts_with=None` to override this behavior.
        - `valid_chars`: the set of characters that should be used for all but `starts_with` and `required_chars` chars. `valid_chars` can contain duplicates of the characters specified in both `starts_with` and `required_chars`. Defaults to all alphanumeric characters.

      Here is an example of the password section of a blueprint:

      ```yaml

          password:
            label: Admin Password
            type: password
            description: Password to use to administer your deployment.
            default: '=generate_password(min_length=8, required_chars=["0123456789", "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"])'
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

      **type**: the data type of this option. Valid types are: string, integer, boolean, password, url, region, and text (multi-line string). See later for a description of the `url` type which has some special attributes.
      **choice**: a list of items to select from (used to display a drop-down). The entries are either plain strings or a mapping with `value` and `name` entries where `value` is what is passed to Checkmate and `name` is what is displayed to the user. Note: does not apply validation. If you want validation, use an `in` constraint. This is used for display only.
      Example:

      ```
      choice:
      - name: Ubuntu 12.04
        value: q340958723409587230459872345
      - name: Ubuntu 12.10
        value: 2384729387w0tw9879t87ywt3y42
      ```
      **constrains**: a list of mappings that are used as a way to set or limit aspects of the blueprint with the value (or parts of) the option.
      **required**: true/false. Set to true if this option must be supplied by the user.


      **....message**: you can add a message key/value pair to any of these constraints. Always add a message to regex constraints so it is easy to understand what they do when read and so clients (rook, etc) and the server can generate useful error messages and people reading the blueprint don't have to decipher the regexs. Ex. "must have 8-16 characters"

      Browser clients will parse constraints and apply validation rules. A good practice it to have multiple, simple regex constraints to allow browser clients to provide clear and useful feedback to the user for each rule they may break. For example, list lowercase, uppercase, and numeric requirements for a password as three constraints with a message unique to each.

      See example below.

      ```yaml
      blueprint:
        options:
          database_name:
            label:  Database Name
            sample: db1
            display-hints:
              order: 1
              group: database
           default: wp_db
           description: "This is the name of the database that will be created to host your application's data"
           type: string
           constraints:
           - regex: ^(?=.*).{2,15}$
             message: must be between 2 and 15 characters long
           - regex: ^[A-Za-z0-9]*$
             message: can only contain alphanumeric characters
          database_password:
            label:  Database Password
            display-hints:
              order: 2
              group: database
           description: "This is the password to use to access the database that will host your application's data"
           type: password
           constraints:
           - regex: ^(?=.*).{8,15}$
             message: must be between 8 and 15 characters long
           - regex: ^(?=.*\d)
             message: must contain a digit
           - regex: ^(?=.*[a-z])
             message: must contain a lower case letter
           - regex: ^(?=.*[A-Z])
             message: must contain an upper case letter
      ```


      ## The URL Type

      Options of type url provide some advanced handling of common url use cases. The option can be used simply as a string that accepts a url. In this case, the only benefit of setting the type to url is that a client application can perform certain validation to make sure the provided value is a valid URL (according to [RFC 3986](http://tools.ietf.org/html/rfc3986)). Example:

      ```
      option:
        my_web_site:
          type: url
      ```

      It is useful, however, to be able to handle different parts of a URL (i.e the scheme or protocol, domain, path, port, username, password, etc...) separately. They may be validated independently (e.g. make sure the protocol is http or https only). The parts may be wired up to different parts of the blueprint using constraints (e.g. use the domain part for a dns setting). The way that is supported is that the url type has attributes that can be accessed in the blueprint or other parts of Checkmate. These attributes are:

      * scheme: this is the first part of the URL
      * protocol: this is the first part of the URL as well (an alias to scheme)
      * netloc: the dns name or address part
      * port: this is the port if specified (e.g. the port in http://localhost:8080 is 8080)
      * path: the path of the resource or file
      * private_key: the private_key of a certificate to use if the protocol is an encrypted one
      * certificate: the public_key of a certificate to use if the protocol is an encrypted one
      * intermediate_key: the intermediate key chain of a certificate to use if the protocol is an encrypted one

      These attributes can be specified in constraints:

      ```yaml:
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

      ```yaml:
      options:
        my_url:
          label: Site Address
          type: url
          constraints:
          - protocols: [http, https]
      ```

      And there are special display-hints used to aid a client in rendering and validating the url. These are `encrypted-protocols` and `always-accept-certificates` which are documented in constraints.

      When supplying the value for a url as an input, it can be supplied as a string or as a mapping with attributes.

      As a string it would be `my_site_address: https://mydomain.com/blog`.

      As a mapping, it would look be:

      ```yaml:
      inputs:
        my_url:
          url: https://domain.com/path  # 'url' is a special shortcut - see note below
          private_key: |
            -----  BEGIN ...
          intermediate_key: |
            -----  BEGIN ...
          certificate: |
            -----  BEGIN ...
      ```

      Note:  A common use case is to supply the url and keys. A shortcut is available that accepts a key called `url` that can be used to supply the url without having to provide all the components of the url.




  any:
    _: ""

    constrains: &constrains
      _type: array
      _: |
        constrains: (v. not noun) what values within components that this option constrains. Key value to select the options, and then the option name. Example:

        Example:
        ```yaml
        constrains: *constrains
        - service: my_database_thang
          setting: key
          attribute: private_key # this will take the private_key value from the generated keys and apply it as the value for 'key' in the my_database_thang component.
        ```

  resources:
    _: static resources to be created at planning time and shared across the blueprint. For example, users and keys.
    any:
      _: any key to identify this resource and reference it from elsewhere in the blueprint. Ex. "my_key"

      type:
        _: "ex. key-pair: private/public key pair will be created before deploying the workflow"

      constrains: *constrains

  documentation:
    _: a map of documentation text or URLs
    abstract:
      _: one paragraph description in markdown.
    instructions:
      _: one page description of how to use the deployment in markdown.
    guide:
      _: a URL to an extrnal web resource containg the full. multi-page guide.


# Blueprint User Inputs
inputs:
  _: |
    inputs: the user's inputs for a deployment

    These are basically where I'm setting my levers and dials... there are different scopes: global, blueprint, service, and provider scopes. So, I can set the memory size at the provider level (i.e. all servers should be 1GB). Or, all servers in service X should be 1GB and all servers in service Y should be 2GB.
      option_foo: bar
      blueprint:
        blueprint_input_foo: bar
      services:
        my_db_thang:
          service_input_foo: baz
          compute: - filter by resource type!
            service_resource_input_foo: boo
      providers:
        'nova':
          compute:
            os: ubuntu
    ```

    Note: more specific inputs override more general ones (see get_setting code in deployment)



# Blueprint Environment
environment:
  _: |

    Environments provide a 'context' and optional constraints as well as a list of providers. For example, if I have an environment with a Cloud Databases provider 'constrained' to LON where Cloud Databases don't have 4GB instances, then the catalog won't have 4GB instances.

    ```yaml

    id: unique identifier provided by client (or user).
    name: user friendliness

    providers: the keys are predefined names form the providers. Checkmate identifies the provider based on the key and vendor field.
      nova:
        vendor: rackspace  - results in Checkmate dynamically loading  checkmate.providers.rackspace.nova (last two are vendor.key)
      chef-solo:
        vendor: opscode
      database:
        vendor: rackspace
        constraints: - optional constraints applied at the provider level (ex. region=DFW)
            The syntax can follow the normal constraint syntax, but can also be a key:value shorthand
            For the normal syntax, a 'value' defines what the constraint evaluates to
        catalog: - a way to inject a catalog into the provider (two uses for this are #1 testing, #2 only want to show 1GB instances). So if a catalog is provided, the provider will use that. Otherwise, it could log on and query the underlying service (list images, list flavors, get cookbooks, etc...). You'll see this in app.yaml.
    ```

    Environment will define what this looks like based on environment providers and constraints. So there is a likelihood that a blueprint will be incompatible with an environment (the environment cannot provide the required resources OR meet the necesary constraints).





