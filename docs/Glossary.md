# Glossary

#### `blueprint`

A blueprint describes an application topology, including all of the services
and how they connect.

A "Checkmatefile" (currently `checkmate.yaml` by convention) is also often
referred to as a blueprint, but a blueprint is actually just the data defined
under the top-level `blueprint` key in a Checkmatefile. See
[the blueprint section](Checkmatefile.md#the-blueprint-section) for more details.

#### `environment`

An environment describes a group of providers which determine where a deployment's
resources are hosted.

An environment is also part of a Checkmatefile, and is defined under the
top-level key `environment`.

#### `deployment`

A deployment is a launched instance of a [blueprint](#blueprint) in a given
[environment](#environment). In other words, a deployment is an actual
instance of a running application.

A deployment will often also use the information under [inputs](#inputs) in the
Checkmatefile, which supplies input values for blueprint [options](#options)
(e.g., region, flavor, server count, etc.).

#### `resource`

A resource is a generic primitive component for building application
deployments. Some examples of resources include:

* application
* database
* load-balancer
* compute (a server of some type)
* user (for example: an LDAP record for a user or database username/password)
* keypair

Different providers may provide slightly different but equivalent variations
of a given type of resource. For example for a "compute" node, a Cloud Server
hosted by Rackspace and an EC2 instance hosted by Amazon are equivalent in this
context.

#### `provider`

A provider wraps a single vendor's API and provides a generic interface to
manage [resources](#resource).

A provider has a catalog that lists the types of resources that it can provide.

#### `workflow`

A workflow consists of a collection of actions being applied to a deployment or
its resources. Workflows are generated to create, delete, or modify deployments.
Only one workflow may run per deployment at a given time.

Typical workflows are:

* deploy
* scale up
* scale down
* bring node online
* take node offline
* delete (deployment)

Workflow is often used synonymously with "operation".

#### `options`

Options are choices which the blueprint wants to present to the user launching a
deployment. The blueprint author determines where the value of that option is
applied in the blueprint.

Options are like variables which can be defined once and used many times in the
blueprint. For example: A URL can be used both to define an Apache vhost as well
as to determine the protocol of a load balancer.

Options can be defined as  can have a default value which is used if no
corresponding [input](#inputs) is provided. If a "required" option has no
default value and no corresponding input, the deployment cannot be launched.

Options are defined in the `options` section of a blueprint.

#### `inputs`

Inputs provide arguments for blueprint [options](#options). They can also
override any part of the deployment configuration. (For example, it is possible
to supply a provider override to create resources only in a specific region.)

Inputs are defined in the top-level `inputs` key of a Checkmatefile.
