# Checkmate
![Checkmate](https://github.rackspace.com/checkmate/checkmate/raw/master/checkmate/static/img/checkmate.png)

## Overview
Checkmate stores and controls your cloud configurations. Use it to deploy and manage complete application stacks.

It exposes a REST API for manipulating configurations. It uses celery for task queuing and SpiffWorkflow to orchestrate deploying them. It support JSON and YAML interchangeably. It has optional built-in browser support with a UI.


## Logic: the pieces
In a nutshell:

1. An expert writes a `blueprint` for how an app can be deployed.
2. The blueprint contains `components`, relationships between these components, and options and constraints on how the app works.
3. An end-user defines `environments` where they want to deploy apps (ex. a laptop, an OpenStack Cloud, a Rackspace US Cloud account)
4. The end-user picks a blueprint (ex. a Scalable Wordpress blueprint) and deploys it to an environment of their choice. That's a `deployment` and results in a fully built and running, multi-component app.
5. Checkmate knows how to add/remove servers (**scaling**) and can verify the app is running and perform troubleshooting (**configuration management**)

### Components

These are the equivalent of Chef recipes or Juju charms. They are the primitive building blocks of an application deployment. These can be supplied as part of a deployment or looked up from the server.

    # Definitions of components used (similar to Juju charm syntax)
    components:
    - &wordpress_reference_id
      id: wordpress
      revision: 3
      summary: "A pretty popular blog engine"
      provides:
        url:
          interface: http
      requires:
        db:
         interface: mysql
        server:
          relation: host
          interface: linux
      options:
        url:
          type: String
          default: wp.test.local
          description: the url to use to host your blog on

    - &mysql.1
      id: mysql
      revision: 1
      summary: "A pretty popular database. Note, this is a cloud database and therefore does not need a host"
      provides:
        db: mysql

Components are defined by 'providers' and come with predefined options supported by the provider.

### Environments

An environment is a place where you can launch and manage application deployments. It could be your development laptop, a cloud provider, or a combination of cloud providers that you have grouped together to use together as a single environment.
Multiple environments can exist in one tenant or account. For example, you could have dev, test, staging, and production environments defined on one Rackspace Cloud account. Checkmate will manage which resources belong in which environment under a tenant using its own database, naming conventions, and tags.

    # Environment
    environment: &environment_1000_stag
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
        chef-local:
          vendor: opscode
          provides:
          - application: http  # see catalog for list of apps like wordpress, drupal, etc...
          - database: mysql  # this is mysql installed on a host


### Blueprints

These define the architecture for an application. The blueprint describes the resources needed to make an application run, how to connect, and how scale them.
Blueprints can have options that determine the final deployment topology and the values that go into the individual component options. The blueprint author determines what options to expose and with what constraints to aplpy on the options available to the end user.

    # An wordpress architecture template
    blueprint: &wp
      id: "6fcc7f31-08f8-4664-90e3-58fffc71f773"
      name: Multi-server Wordpress
      services:
        lb:
          component: *loadbalancer
          relations:
            web: http
          exposed: true
          open-ports: [80/tcp]
        web:
          component: *wordpress_reference_id  # wordpress component above
          relations: {backend: mysql}
        backend:
          components: *mysql
      options:
        instance_count:
          type: number
          label: Number of Instances
          description: The number of instances for the specified task.
          default: 2
          constrains:
          - {service: web, resource_type: compute, setting: count}
          constraints:
          - greater-than: 1 # this is an HA config


### Deployments

A deployment defines and points to a running application and the infrastructure it is running on. It basically says "I took blueprint X and deployed it to environment Y using the following options". It combines a blueprint, an environment to deploy the resources to, and any additional inputs specific to this deployment.


    # Actual running app and the parameters supplied when deploying it
    deployment:
      blueprint: *wp
      environment: *environment_1000_stag
      inputs:
        instance_count: 4
      resources:
        '0':
          type: server
          provider: nova
          status: up
          flavor: 1
          image: 119
          instance:
            id: 2098383
            private_ip: 10.10.1.1
            public_ip: 2.2.2.18
          dns-name: srv1.stabletransit.com
          relations:
            web-backend:
              state: up
        '1':
          type: server
          status: up
          provider: nova
          flavor: 1
          image: 119
          instance:
            id: 2098387
            private_ip: 10.10.1.8
            public_ip: 2.2.2.22
          dns-name: srv2.stabletransit.com
          relations:
            web-backend:
              state: up
        '2':
          type: load-balancer
          dns-name: CMDEP32ea304-lb1.rackcloudtech.com
          instance:
            id: 8668444
          relations:
            lb-web:
              state: up
        '3':
          type: database
          provider: databases
          dns-name: CMDEP32ea304-db1.rackcloudtech.com
          flavor: 1
          disk: 2
          instance:
            id: 99958744

Once deployed, the live resources running the application are also listed. The intent is for Checkmate to be able to manage the deployment. An example of a management operation would be resizing the servers:

1. bring down the load-balancer connection for srv1 (knowing srv2 is up)
2. resize srv1
3. bring the load balancer connection back up
4. perform the same on srv1

Such an operation cannot be performed by the underlying services alone since they have no knowledge of the full stack like checkmate does.


Note: for additional descriptions of each field see the examples/app.yaml file.

### Options and Inputs

Options can be exposed by blueprints and components. An *option* is the _definition_ of a user-selectable value that can supplied for that blueprint or a component.

When launching a deployment, the values selected for options are stored as an *input* to the deployment under the 'inputs' key. Inputs can be applied at multiple levels in the deployment hierarchy as follows:

- Global inputs (apply to everything):

  inputs:
    domain: mydomain.com

- Blueprint inputs (apply to a setting on the blueprint):

  inputs:
    blueprint:
      domain: mydomain.com

- Service inputs (apply to a particular service in the blueprint):

  inputs:
    services:
      "backend":
        use_encryption: true

- Provider inputs (apply to a provider and any resourcers that provider provides):

  inputs:
    providers:
      'legacy':
        region: dallas

- Resource type inputs. These can be applied under services or providers as follows:

  inputs:
    services:
      "backend":
        'database':
          'memory': 512 Mb
    providers:
      'nova':
        'compute':
          'operating-system': Ubuntu 12.04 LTS


Options can be associated with one or more options using *constraints*. Example:

  blueprint:
    options:
      "my_setting":
        default: 1
        constrains: [{service: web, resource_type: compute, setting: foo}]

The above setting would apply to (constrains) any setting called 'foo' under a 'compute' resource in the 'web' service of the blueprint. See app.yaml for more examples of how inputs and options are used.

More precisely scoped options will override broader options. For example, a service or provider option will override a global option.

TODO: fix terminology. 'setting', 'option' and/or 'input'. And update code, schema, and docsa accordingly


## Semantic: The API
The API is a **REST HTTP API**. It supports POST, PUT, GET, DELETE on:

- /components[/:id]
- /blueprints[/:id]
- /environments[/:id]
- /deployments[/:id]
- /workflows[/:id]
- /providers[/:id]

*Note: not all verbs on all paths. DELETE not yet ready*

### POST & PUT
Sometimes a religious debate, but here are the semantics checkmate uses now. Simply:

- **PUT** updates without taking any action.
- **POST** can trigger actions or have side-effects (like actual server deployments) and can accept partial objects.

The **symantics** are:

**POST /objects** (without ID):
- creates a new object. ID is generated by checkmate and returned in the Location header.
- use it to create objects without fear of ID conflicts

**POST /objects/:id**
- Update an existing object. Partial updates are supported (i.e. I can POST only the name to rename the object). Could trigger side effects, like running a workflow.
- Use it to modify parts of an object.

**PUT /objects/:id**
- Overwrites the object completely. Does not trigger side effects, but will validate data (especially id and tenant_id fields).
- Use it to store something in checkmate (ex. a deployment exported from another instance of checkmate)

**GET** will sometimes add the object ID and tenant ID if the underlying store does not provide them. This is so that the object can be identified when parsed later.

###JSON, YAML, and XML
Objects are returned as JSON by default, but YAML is also supported (content-type: application/x-yaml)
HTML output is also supported if the server is started with a `--with-ui` parameter.

XML is not yet supported.

###Special cases and considerations

All objects should have a root key with the name of the class. Ex. `{"blueprint": {"id": 1}}`. However, checkmate will permit objects without the root if they are provided. Example:

	PUT /blueprints/2 {"id": 2}

Checkmate will fill in the id, status, tenant_id, and creation date of posted objects. For puts, these value must be supplied and must be correct (i.e. matching the tenant and id in the URL).

YAML supports references within a document. If a deployment is in YAML format and is using references, the references can be provided under a key called 'includes'. This can be used, for example, to create a new deployment passing in all the necessary components, blueprints, environments, etc... (or
    references to them).

Some commands can be issued with a '+command' URL. Example:

      /workflows/wf1000/+execute

All calls are supported flat off of the root or under a tenant ID. Calls off of the root require administrative privileges and will return all objects from all tenants (ex. /environments vs /T1000/environments)


### List of all calls
*:tid* is the tenant ID and is optional.

    GET/POST [/:tid]/environments
    PUT/GET/POST [/:tid]/environments/:id

    GET [/:tid]/environments/:id/providers
    GET [/:tid]/environments/:id/providers/:pid
    GET [/:tid]/environments/:id/providers/:pid/catalog
    GET [/:tid]/environments/:id/providers/:pid/catalog/:cid

    GET/POST [/:tid]/blueprints
    PUT/GET/POST [/:tid]/blueprints/:id

    GET/POST [/:tid]/deployments
    PUT/GET/POST [/:tid]/deployments/:id
    POST [/:tid]/deployments/+parse
    POST [/:tid]/deployments/+preview

    GET [/:tid]/deployments/:id/status

    GET/POST [/:tid]/workflows
    PUT/GET/POST [/:tid]/workflows/:id

    GET [/:tid]/workflows/:id/status

    POST [/:tid]/workflows/:id/+execute

    GET/POST [/:tid]/workflows/:id/tasks/:task_id

    POST [/:tid]/workflows/:id/tasks/:task_id/+execute
    POST [/:tid]/workflows/:id/tasks/:task_id/+resubmit

    GET [/:tid]/providers
    GET [/:tid]/providers/:pid
    GET [/:tid]/providers/:pid/catalog
    GET [/:tid]/providers/:pid/catalog/:cid

    GET /status/celery
    GET /status/libraries


## Usage

To start the checkmate REST API server:

    $ bin/checkmate-server START [options] [address[:port]]

Options:

        --with-ui:         enable support for browsers and HTML templates
        --with-simulator:  enable support for the workflow simulator
        --newrelic:        enable newrelic monitoring (place newrelic.ini in
                           your directory)
        --eventlet:        use the eventlet server (recommended in production)
        --quiet:           turn down logging to WARN (default is INFO)
        --verbose:         turn up logging to DEBUG (default is INFO)
        --debug:           turn on additional debugging inspection and output
                           including full HTTP requests and responses. Log
                           output includes source file path and line numbers.
        --trace-calls, -t: display call hierarchy and errors to stdout
        --eager:           all celery (queue) tasks will be executed in-process
                           Use this for debugging only. There is no need to
                           start a queue instance when running eager.

Once up, you can issue curl commands (or point your browser at it if you started the server --with-ui) to use checkmate.

To execute deployments, checkmate uses a message queue. You need to have celery running with the checkmate tasks loaded:

    $ bin/checkmate-queue START

    or, directly using celery:

    $ celeryd -l info --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode

### Settings

The following environment variables can be set to configure checkmate:

**CHECKMATE_CONNECTION_STRING**: a sql-alchemy or mongodb connection string pointing to the database store for checkmate. Examples:

    sqlite:////var/checkmate/data/db.sqlite

    mongodb://localhost/checkmate

Note: to connect to mongodb, also install the pymongo client library:

    $ pip install pymongo  # you probably need to sudo this

**CHECKMATE_DOMAIN**: a default DNS domain to use for resources created.

**CHECKMATE_PUBLIC_KEY**: a public key string to push to all created servers to allow ssh access to them. If you set this to the contents of your ~/.ssh/id_rsa.pub file you will be able to log on to all checkmate-created servers without having to suply a password.

**CHECKMATE_CHEF_LOCAL_PATH**: checkmate uses chef to configure applications on
    servers. Checkmate supports using chef with and without a chef server. When
    using it without a chef server, checkmate has a provider called chef-local
    that stores all deployments in a multi-tenant capable and scalable file
    structure. This setting points to the directory where this structure should
    be hosted.  If not specified, Checkmate will try to default to
    /var/local/checkmate/deployments.

**CHECKMATE_CHEF_REPO**: This setting points to a directory that contains a chef
    repository (a directory with cookbooks, roles, environments, site-cookbooks
    subdirecotries, etc...). You can clone the opscode repo (https://github.com/opscode-cookbooks/)
    or use your own. This repo is never modified by checkmate. Files from it are
    copied to the individual deployments. If not specified, Checkmate will try
    to default to /var/local/checkmate/chef-stockton.

**CHECKMATE_CHEF_USE_DATA_BAGS**: when using the chef-local provider, some capabilities of a chef server can be emulated using data bags. Setting this value to True tells checkmate to use data bags instead of normal node, role, and environment overrides to store data for deployments. (default=True).

**CHECKMATE_CHEF_PATH**: when using checkmate with a server, checkmate needs to know the path for the chef client deployment. This points to that path. The kniofe.rb file should be in there.

**CHECKMATE_BROKER_USERNAME**: the username to use to connect to the message queue

**CHECKMATE_BROKER_PASSWORD**: the password to use to connect to the message queue.

Note: set this value if you are using the CHECKMATE_BROKER_URL override with a password. Checkmate will use this to replace your password with ***** in logs.

**CHECKMATE_BROKER_HOST**: the IP address or resolveable name of the message queue server

**CHECKMATE_BROKER_PORT**: the port to use to connect to the message queue server

**CHECKMATE_BROKER_URL**: Alternatively, a full url with username and password can be supplied. This *overrides* the previous four settings. Checkmate server and queue listener will report out what settings they are using when they start up.

To use mongodb as a broker instead of rabbitmq, set this value to your mongodb endpoint (see `Setup for mongodb broker` at end of this document):

    mongodb://localhost/checkmate

Note: all CHECKMATE_BROKER_* values are picked by code in the checkmate.celeryconfig module. If you use an alternate config file, these variable may be ignored. See **CELERY_CONFIG_MODULE**.

**CHECKMATE_RESULT_BACKEND**: default is 'database'. Checkmate needs to query task results and status. [tested with 'database' only]. This value is picked up from checkmate.celeryconfig. If you use an alternate config file, this variable may be ignored. See **CELERY_CONFIG_MODULE**.

In preliminary testing is the "mongodb" setting:

    CELERY_RESULT_BACKEND = "mongodb"
    CELERY_MONGODB_BACKEND_SETTINGS = {"host": "localhost", "port": 27017, "database": "checkmate", "taskmeta_collection": "celery_task_meta"}

**CHECKMATE_RESULT_DBURI**: defaults to 'sqlite://../data/celerydb.sqlite' under the checkmate directory. Use this to set an alternate location for the celery result store. This value is picked up from checkmate.celeryconfig. If you use an alternate config file, this variable may be ignored. See **CELERY_CONFIG_MODULE**.

**CELERY_CONFIG_MODULE**: use checkmate.celeryconfig by default. See celery instructions for more detail. THis module also picks up the values from some of the other environment variables. If you use a different config module, the other checkmate variables may get ignored.

**CELERY_ALWAYS_EAGER**: forces celery to run synchronously, in-process instead of using the message queue. May be useful for debugging, development, and troubleshooting.

Deprecated: not used anymore

CELERYD_FORCE_EXECV (as of celery 3.x)

CHECKMATE_DATA_PATH

CHECKMATE_PRIVATE_KEY


## Checkmate Installation

See the INSTALL.md file for installing Checkmate as a production service or
for development.


## Authentication


Checkmate supports multiple authentication protocols and endpoints simultaneously. If it is started with a web UI (using the --with-ui) option, it will also support basic auth for browser friendliness.

### Authenticating through a Browser

By default, three authentication domains are enabled. In a browser, if you are prompted for credentials, enter the following:

- To log in as an administrator: username and password from the machine running Checkmate (uses PAM).

- To log in to a Rackspace US Cloud Account: use US\username and password.

- To log in to a Rackspace UK Cloud Account: use UK\username and password.

### Authenticating using REST HTTP calls

Checkmate supports standard Rackspace\OpenStack authentication with a token. Get a token from your auth endpoint (US or UK!) and provide it in the X-Auth-Header:

    curl -H "X-Auth-Token: ccdcd4f9-d72d-5677-8b1a-f329389cc539" http://localhost:8080/4500 -v

Checkmate will try the US and then UK endpoints.

To avoid hitting the US for each UK call, and to be a good citizen, tell Checkmate which endpoint your token came from using the X-Auth-Source header:

    curl -H "X-Auth-Source: https://lon.identity.api.rackspacecloud.com/v2.0/tokens" -H "X-Auth-Token: ccdcd4f9-d72d-5677-8b1a-f329389cc539" http://localhost:8080/1000002 -v

Note: This is a Checkmate extension to the auth mechanism. This won't work on any other services in OpenStack.

## Tools

### Monitoring

celery has a tool called celeryev that can monitor running tasks and events. To use it, you need to turn `events` on when running celeryd using -E or --events:

    celeryd -l debug --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --events

And then use celeryev from the checkmate directory to watch events and tasks::

    celeryev --config=checkmate.celeryconfig

### Tuning

The following has been tested to run up to 10 simultaneous workflows using amqp::

    celeryd --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --autoscale=10,2

On Unix/Linux Systems (including Mac), the following
setting resolves issues with workers hanging::

    export CELERYD_FORCE_EXECV=1


### Dependencies

Checkmate has code that is python 2.7.1 specific. It won't work on earlier versions.

Some of checkmate's more significant dependencies are::

- celeryd: integrates with a message queue (ex. RabbitMQ)
- a message broker (rabbitmq or mognodb): any another backend for celery should work (celery even has emulators that can use a database), but rabbit and mongo are what we tested on
- SpiffWorkflow: a python workflow engine
- chef: OpsCode's chef... you don't need a server, but use with a server is supported.
- cloud service client libraries: python-novaclient, python-clouddb, etc...

#### SpiffWorkflow
Necessary additions to SpiffWorkflow are not yet in the source repo, so install
the development branch from this fork:

    $ git clone -b master https://github.rackspace.com/checkmate/SpiffWorkflow
    $ cd SpiffWorkflow
    $ sudo python setup.py install

#### python-novacalient
Necessary patches to python-novacalient are not yet in the source repo, so install
the development branch from this fork:

    $ git clone -b master https://github.rackspace.com/checkmate/python-novacalient
    $ cd python-novacalient
    $ sudo python setup.py install

#### python-clouddb
Necessary patches to python-clouddb are not yet in the source repo, so install
the development branch from this fork:

    $ git clone -b master https://github.rackspace.com/checkmate/python-clouddb
    $ cd python-clouddb
    $ sudo python setup.py install

#### Celery

[celeryd](http://www.celeryproject.org/) does the heavy lifting for
distributing tasks and retrying those that fail.


#### AngularJS

[AngularJS](http://www.angularjs.org/) is a UI framework that we use in
Checkmate. It provides a Javascript framework that can run from the browser.

[This](http://yearofmoo.com/2012/08/use-angularjs-to-power-your-web-application/) is
a good intro to AngularJS. It seems to be constantly updated and remains relevant.


#### Mox

This is a library used for testing. The source code includes some highly useful
updates which have not yet made it into the published binaries. While the public
library will work fine, I recommend doing the following:

    # Get the latest source code
    svn checkout http://pymox.googlecode.com/svn/trunk/ pymox-read-only
    # Install it
    cd pymox-read-only
    sudo python setup.py install


## Why the name checkmate?

My intention for this product is be a deployment _verification_ and management service,
and not just a deployment automation service. So it will be used to CHECK configurations
and autoMATE, not only the deployment, but the repair of live deployments as well. It
also conveniently abbreviates to 'cm' which could also stand for configuration management,
aludes to this being a killer app, appeals to my inner strategist, it has a 'k' sound in
it which I am told by branding experts makes it sticky, and, above all, it sounds cool.


## Setup for mongodb broker

### Celery
Install celery with all of its mongo-related dependencies. This command will
install the latest stable version of celery if it has not yet been installed or
upgraded.

    sudo pip install -U celery-with-mongodb

### Mongo
Specific instructions for installing MongoDB on your OS can be found
[here](http://docs.mongodb.org/manual/installation/).

Once you have MongoDB installed, you need to start the **mongod** process.
Instructions on how to do this can be found at the end of the MongoDB
installation documentation for each OS. To run mongo from the checkmate
directory and have it store its database in the data directory:

    mongod --dbpath data

Now that Mongo is installed and running, we need to configure security settings
and then set up a db to act as our broker.

With **mongod** running, open a new window. Run the following code to open the
special admin DB that mongo provides.

    mongo localhost/admin

Now that we're logged into the admin DB we need to create a user that is the
admin for the entire db server process. **Note**: these are NOT the credentials
we are going to use to connect to the checkmate broker.

    db.addUser("SOME_USERNAME","SOME_PASSWORD")
    db.auth("SOME_USERNAME","SOME_PASSWORD")

Lastly, we need to create a checkmate DB to act as our broker, and create a
user that will have read/write access to that DB.

    use checkmate #creates'checkmate' DB
    db.addUser("checkmate","password") #Gives read/write access to user 'checkmate'


### Checkmate

All the following settings require the checkmate celery config module to be
used by celery:

    export CELERY_CONFIG_MODULE=checkmate.celeryconfig

#### Using mongo as the broker (instead of rabbitmq)

Checkmate's `celeryconfig` file defaults to an amqp broker, so instead of
exporting each variable (i.e. `CHECKMATE_BROKER_USERNAME`,
`CHECKMATE_BROKER_PASSWORD`,etc) we need to export one `CHECKMATE_BROKER_URL`
in the form of `mongodb://username:password@host:port/db_name` that tells
celery to use mongo.

    export CHECKMATE_BROKER_URL="mongodb://checkmate:password@localhost:27017/checkmate"

#### Using mongo as the result store

To have celery store the task results in mongo, we also need to set the
backend URI to mongo:

    export CHECKMATE_RESULT_BACKEND="mongodb"
    export CHECKMATE_MONGODB_BACKEND_SETTINGS='{"host": "localhost", "database": "checkmate", "taskmeta_collection": "celery_task_meta"}'

#### Using mongo as the database for Checkmate:

    export CHECKMATE_CONNECTION_STRING="mongodb://checkmate:password@localhost:27017/checkmate"


#### Putting all together:

Start the task queue:

    export CELERY_CONFIG_MODULE=checkmate.celeryconfig
    export CHECKMATE_BROKER_URL="mongodb://checkmate:password@localhost:27017/checkmate"
    export CHECKMATE_RESULT_BACKEND="mongodb"
    export CHECKMATE_MONGODB_BACKEND_SETTINGS='{"host": "localhost", "port": 27017, "user": "checkmate", "password": "password", "database": "checkmate", "taskmeta_collection": "celery_task_meta"}'
    export CHECKMATE_CONNECTION_STRING="mongodb://checkmate:password@localhost:27017/checkmate"
    export CHECKMATE_CHEF_REPO=/var/checkmate/chef/repo/chef-stockton
    export CHECKMATE_CHEF_LOCAL_PATH=/var/chef
    bin/checkmate-queue START


And then start the checkmate server:

    export CELERY_CONFIG_MODULE=checkmate.celeryconfig
    export CHECKMATE_BROKER_URL="mongodb://checkmate:password@localhost:27017/checkmate"
    export CHECKMATE_RESULT_BACKEND="mongodb"
    export CHECKMATE_MONGODB_BACKEND_SETTINGS='{"host": "localhost", "port": 27017, "user": "checkmate", "password": "password", "database": "checkmate", "taskmeta_collection": "celery_task_meta"}'
    export CHECKMATE_CONNECTION_STRING="mongodb://checkmate:password@localhost:27017/checkmate"
    export CHECKMATE_CHEF_REPO=/var/checkmate/chef/repo/chef-stockton
    export CHECKMATE_CHEF_LOCAL_PATH=/var/chef
    export CHECKMATE_PUBLIC_KEY=`cat ~/.ssh/id_rsa.pub`  # on a mac
    bin/checkmate-server START --with-ui --with-simulator
