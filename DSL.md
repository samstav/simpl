Checkmate DSL
-------------

- YAML and JSON are both first class citizens. We can do all this in JSON, just easier to type and read YAML (for humans, less puntuation). In fact, JSON is a subset of YAML (a YAML parser will understand JSON).
- A deployment contains a blueprint and an environment. Those can be references or they can be embedded (a copy) in the YAML/JSON.
- App.yaml contains everything in one file JUST to make it easier to run Checkmate. That's not the typical use case. Typically, users will have existing environments and blueprints and they'll reference those (like in the new deployment screen).
- Components should come from providers. Component IDs are universal. We'll need a catalog somewhere. Ex. wordpress is wordpress is wordpress....
- An environment is unique to a user (a.k.a a tenant in our cloud). So each user create and manage their own environments (they can call them test, dev, QA, prod, etc...)
- Environment != Region or cloud provider. So I can have test, prod and dev in Rackspace Cloud US, DFW, account 1000. Only Checkmate knows which resource belongs to which environment (i.e. in Next Generation Cloud Control Panel, they're all intermingled). Another example, might be an environment I create which has everything in Rax DFW, except for backups going to AWS S3). Environment is a user-created construct, not necessarily tied to any existing cloud deployment or provider.
- Blueprints are independent of all the above. They can be shared between tenants. Tenants can create their own (or modify public ones). For example, we might publish a "Best Practice WordPress by Rackspace Blueprint" and anyone can use it.
- Deployment is a combination of Blueprint, Environment, and a set of parameters (inputs).
- Provider is a plug-in for Checkmate that understands how to operate a service or system. Ex. the Rackspace Compute Provider knows how to call Rackspace Cloud and create compute resources. The OpsCode Chef Provider knows how to operate chef and apply cookbooks. Not to be confused with cloud providers (lower case).... :-(
- A blueprint is meant to be created by an "architect". Someone who wants to encode or write down the logic and constraints of a system or app based on their deep knowledge and expertise of all the components of that system. Ex. a WordPress expert would write the Rackspace best Practice Wordpress Blueprint.
- Simplicity for the user (blueprint architects and deployment end-users) first. It trumps structure, code, DRY, object orientation, etc...
- It's more acceptable for a deployment to fail than for a blueprint to be complicated to author.

Components
==========
id: a unique identifier (not necessarily a UUID, but a string) within the provider that provides that component.
    Temporary assertion: the id for wordpress is wordpress always (in puppet, chef, etc....). And we will maintain a list of those ids. Precedents for this are OpsCode cookbooks and Juju charms (http://jujucharms.com/charms/precise).
    **Action item/future consideration**: create our own catalog (or use Charms/cookbooks)

name: user friendliness (*mssql vs Microsoft SQL Server)

role: Allows you to specify the role of this component. 
	EX:
	component:
	  name: wordpress
          role: master

version: for versioning...!

description: comes from Juju, a short description. (we could have named it description, but decided not to diverge from something already out there...)
    **Action item**: switch to description from summary, more universally used.

is: describes the type of resource based on a list of primitives (compute, database, load-balancer, application, ...) - coming from OpenStack.
    **Unseconded proposal** to change to type.

requires: what this resource needs. The needs can be specific or general. General would be anything with a mysql interface (for WordPress). Specific would be I need a host compute resource that is an Ubuntu 12.04 or later machine.
Syntax (two options, long an short form):
    type: interface. Example: database: mysql - short syntax is resource_type:interface. By design.
    name: hash (key/value pairs) for more specific stuff. Name is arbitrary.
    Name key/value example:
        server: (this is the arbitrary key - the label of this requirement)
            type: compute
            interface: debian (this says I expect to be able to do apt-get, vs yum)
            relation: host (this says I am hosted on this resource. I cannot exist without it. I am down when it is down). "host" is a keyword.
            constraint:
            - 'os': ['debian', 'redhat']
The name+key/value syntax allows for requiring more than one of the same resource (ex. log and data mysql databases) as well as adding additional constraints, etc....

provides: array of resource_type:interface entries (array can be represented in YAML with entries preceded with dashes). For example, let's say we get a CLoud Sites API that provides a "site" resource. Site could provide:
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
    source_field_name: the name as it is known by the underlying provider. Ex. wordpress/database/db_user for OpsCode Chef. We need this currently since we dynamically generate component definitions and we need to be able to map things back after they've flowed through checkmate.
        * Should be able to get rid of this in the future with clean, reversible mapping logic in providers.
    type: string
    regex: for validation
    sample: for display, to show what this looks like.
    help: help text.
password:
    
Note:

    GET /providers
    GET /:tenant_id/environments/:id/providers/:id/catalog/
    - you'll get a list of components grouped by resource type. (You'll also get some additional info called lists).


Environments
============

Environments provide a 'context' and optional constraints as well as a list of providers. For example, if I have an environment with a Cloud Databases provider 'constrained' to LON where Cloud Databases don't have 4GB instances, then the catalog won't have 4GB instances.

id: unique identifier provided by client (or user).
name: user friendliness

providers: the keys are predefined names form the providers. Checkmate identifies the provider based on the key and vendor field.
  nova:
    vendor: rackspace  - results in Checkmate dynaminally loading checkmate.providers.rackspace.nova (last two are vendor.key)
  chef-local:
    vendor: opscode
  database:
    vendor: rackspace
    constraints: - optional constraints applied at the provider level (ex. region=DFW)
        The syntax can follow the normal constraint syntax, but can also be a key:value shorthand
        For the normal syntax, a 'value' defines what the constraint evaluates to
    catalog: - a way to inject a catalog into the provider (two uses for this are #1 testing, #2 only want to show 1GB instances). So if a catalog is provided, the provider will use that. Otherwise, it could log on and query the underlying service (list images, list flavors, get cookbooks, etc...). You'll see this in app.yaml.

Environment will define what this looks like based on environment providers and constraints. So there is a likelihood that a blueprint will be incompatible with an environment (the environment cannot provide the required resources OR meet the necesary constraints).

Blueprints
==========
Concept: An application is a collection of components that provide a useful capability. An application is distinct from infrastructure.

A blueprint describes a design that provides an application with certain 'ilities (scalability, availability, etc...). It defines the components, their relationships to each other, and the various constraints on the components and relationships that must be met in order for the application to work as specified.

For services in a blueprint:
- one or more services (all under one 'services' entry)
- arbitrary name for service ID (each one has its own ID)
- one component per service with the expectation that we'll be able to pull in blueprints as components in the future.
- relations between services

id: unique identifier provided by client (or user).
name: user friendliness
description: ...
services: like tiers, but not restricted to the concept of tiers. Currently, there is one component defined per service.
  name -  arbitrary, determined by blueprint author. Exmplae:
  "my_wordpress_thang":
    either id or key/value pairs to help find a suitable component.
    Example of ID short form: wordpress
    component: wordpress
    Example of key/value pair:
    component:
        type: application
        interface: http
        constraints:
        - count: 2  (currently, there's no defined schema to be able to say somthing like "greater than one")
    relations: effectively connections to other services. Examples:
    - wordpress app to mysql database
    - load balancer to webhead
    Two syntaxes for relations; short and long.
    Short syntax: service_name:interface. Example:
        my_db_thang:mysql
    Long syntax: arbitrary name, key values. Example:
        db:
          interface: mysql
          service: my_db_thang
options: KEY piece (don't forget it!). This lists the options (levers or dials) that the blueprint author is exposing to me. SImilar in syntax to component options, but the main difference is in the constraints
  "database_bigness":
    description: the size of the database
    default: 2GB
    # we need to define the syntax for more complex logic, like greater than, less than, etc....
    constrains:  # what values swithin components that this option constrains. Key value to select the options, and then the optoin name. Example:
    - service: my_database_thang
      setting: memory
    - service: my_database_log_thang
      setting: memory
    choice:
    - value: 1024
      name: 1gig
    - value: 2048
     name: 2GB
resources: static resources to be created at planning time and shared across the blueprint. For example, users and keys.
  "my_key":
    type: key-pair # private/public key pair will be created before deploying the workflow
    constrains:
    - service: my_database_thang
      setting: key
      attribute: private_key # this will take the private_key value from the generated keys and apply it as the value for 'key' in the my_database_thang component.

Deployments
===========

id: ...
name: ...
blueprint: can be a reference (YAML), but right now, in checkmate, it's a full copy of a blueprint. We'll support references using URI later (git, local references, etc...).
environment: same as blueprint - right now we make a full copy
inputs: - these are basically where I'm setting my levers and dials... there are different scopes: global, blueprint, service, and provider scopes. So, I can set the memory size at the provider level (i.e. all servers should be 1GB). Or, all servers in service X should be 1GB and all srvers in service Y should be 2GB.
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
Note: more specific inputs override more general ones (see get_setting code in deployment)

**Action Item**: determine the need for global inputs. Do we really need them? Or at least put them in a "globals" category

Minimal, canonical deployment (hello world) available [here](https://github.rackspace.com/Blueprints/helloworld/).
 
**Action Item**: define how we reference blueprints and environments in deployments without including full copies.  Reference UUID?  URL to file in git or local reference? etc.

**Action Item**: improve syntax for indicating a generated value, or remove it and let a generated value be the default.  Or create system for code to be included in blueprint to be used to generate, validate values. See artifacts prototype in app.yaml.



