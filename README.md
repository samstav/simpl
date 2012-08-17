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

    GET [/:tid]/deployments/:id/status

    GET/POST [/:tid]/workflows
    PUT/GET/POST [/:tid]/workflows/:id

    GET [/:tid]/workflows/:id/status

    POST [/:tid]/workflows/:id/+execute

    GET/POST [/:tid]/workflows/:id/tasks/:task_id

    POST [/:tid]/workflows/:id/tasks/:task_id/+execute
    POST [/:tid]/workflows/:id/tasks/:task_id/+resubmit

    GET [/:tid]/providers

    GET /status/celery
    GET /status/libraries


## Usage

To start the checkmate REST API server:

    $ bin/checkmate-server START [options] [address[:port]]

Options:

        --with-ui:  enable support for browsers and HTML templates
        --newrelic: enable newrelic monitoring (place newrelic.ini in your
                    directory)
        --quiet:    turn down logging to WARN (default is INFO)
        --verbose:  turn up logging to DEBUG (default is INFO)
        --debug:    turn on additional debugging inspection and output
                    including full HTTP requests and responses. Log output includes source file path and line numbers.

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

**CHECKMATE_CHEF_LOCAL_PATH**: checkmate uses chef to configure applications on servers. Checkmate supports using chef with and without a chef server. When using it without a chef server, checkmate has a provider called chef-local that stores all deployments in a multi-tenant capable and scalable file structure. This setting points to the directory where this structure should be hosted. An example would be /var/checkmate/deployments.

**CHECKMATE_CHEF_REPO**: This setting points to a directory that contains a chef repository (a directory with cookbooks, roles, environments, site-cookbooks subdirecotries, etc...). You can clone the opscode repo (https://github.com/opscode-cookbooks/) or use your own. This repo is never modified by checkmate. Files from it are copied to the individual deployments.

**CHECKMATE_CHEF_USE_DATA_BAGS**: when using the chef-local provider, some capabilities of a chef server can be emulated using data bags. Setting this value to True tells checkmate to use data bags instead of normal node, role, and environment overrides to store data for deployments. (default=True).

**CHECKMATE_CHEF_PATH**: when using checkmate with a server, checkmate needs to know the path for the chef client deployment. This points to that path. The kniofe.rb file should be in there.

**CHECKMATE_BROKER_USERNAME**: the username to use to connect to the message queue

**CHECKMATE_BROKER_PASSWORD**: the password to use to connect to the message queue.

**CHECKMATE_BROKER_HOST**: the IP address or resolveable name of the message queue server

**CHECKMATE_BROKER_PORT**: the port to use to connect to the message queue server

**CHECKMATE_BROKER_URL**: Alternatively, a full url with username and password can be supplied. This *overrides* the previous four settings. Checkmate server and queue listener will report out what settings they are using when they start up.

Note: all CHECKMATE_BROKER_* values are picked up from checkmate.celeryconfig. If you use an alternate config file, these variable may be ignored. See **CELERY_CONFIG_MODULE**.

**CHECKMATE_RESULT_BACKEND**: default is 'database'. Checkmate needs to query task results and status. [tested with 'database' only]. This value is picked up from checkmate.celeryconfig. If you use an alternate config file, this variable may be ignored. See **CELERY_CONFIG_MODULE**.

**CHECKMATE_RESULT_DBURI**: defaults to 'sqlite://../data/celerydb.sqlite' under the checkmate directory. Use this to set an alternate location for the celery result store. This value is picked up from checkmate.celeryconfig. If you use an alternate config file, this variable may be ignored. See **CELERY_CONFIG_MODULE**.

**CELERY_CONFIG_MODULE**: use checkmate.celeryconfig by default. See celery instructions for more detail. THis module also picks up the values from some of the other environment variables. If you use a different config module, the other checkmate variables may get ignored.

**CELERYD_FORCE_EXECV**: See celery instructions for more detail. This setting can prevent queue listeners hanging on some OSes (seen frequently on developer Macs)

Deprecated: not used anymore

CHECKMATE_DATA_PATH

CHECKMATE_PRIVATE_KEY


## Checkmate Installation

Checkmate is mostly a python service. Therefore, most installations can be done with python tools like pip or easy_install. There are two main exceptions to this:

1. Chef: chef is a ruby-based app.

2. forks: of existing projects are sometimes used to support functionality that is not available for a system like checkmate. For example, checkmate uses OpenStack auth tokens to call OpenStack services. Many of the libraries for OpenStack services are rapidly evolving and designed for command-line use. Another example is the SpiffWorkflow workflow engine. This is a project developed in an academic setting and needed significant patching to work with checkmate. For these projects, we maintain our own forks that need to be deployed with checkmate. All modifications are intended be proposed upstream.

### Installation:

Create and go to the directory you want to install Checkmate in:

Install the latest Chef client, knife-solo, and knife-solo_data_bag:

    # Get latest chef code (or see chef install for version 10.12.0):
    git clone git://github.com/opscode/chef.git  # Get latest chef code
    cd chef

    # Install RVM
    echo insecure >> ~/.curlrc
    curl -k -L get.rvm.io | bash -s stable
    source ~/.rvm/scripts/rvm

    # Install Ruby 1.9.3 locally
    rvm install 1.9.3-p125
    rvm use ruby-1.9.3-p125

    rvm gemset create chef
    rvm gemset use chef
    gem install bundler

    # Build chef
    rake install

Install knife add-ons:

    gem install knife-solo --version 0.0.10

    gem install knife-solo_data_bag --version 0.2.1

Install SpiffWorkflow fork:

    git clone http://github.com/ziadsawalha/SpiffWorkflow.git
    cd SpiffWorkflow
    python setup.py install
    cd ..

Install Checkmate:

    git clone http://github.com/ziadsawalha/checkmate.git
    cd checkmate
    git checkout master
    python setup.py install
    cd ..

Install, configure, and start rabbitmq.

    $ sudo apt-get -y install rabbitmq-server python-dev python-setuptools
    $ sudo rabbitmqctl delete_user guest
    $ sudo rabbitmqctl add_vhost checkmate
    $ sudo rabbitmqctl add_user checkmate <some_password_here>
    $ sudo rabbitmqctl set_permissions -p checkmate checkmate ".*" ".*" ".*"
    $ sudo rabbitmq-server -detached

Set the environment variable for your checkmate deployment environments and create the directory:

    $ export CHECKMATE_CHEF_LOCAL_PATH=/var/checkmate/deployments
    $ mkdir -p $CHECKMATE_CHEF_LOCAL_PATH

Clone the chef repository and point checkmate to it:

    $ mkdir -p /var/checkmate/chef/repo
    $ cd /var/checkmate/chef/repo
    $ git clone git://github.rackspace.com/checkmate/chef-stockton.git


Starting the server processes:

You'll need three terminal windows and Rackspace cloud credentials (username &
API key). In the first terminal window, start the task queue:

    export CHECKMATE_BROKER_USERNAME="checkmate"
    export CHECKMATE_BROKER_PASSWORD="password"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=checkmate.celeryconfig
    export CHECKMATE_CHEF_REPO=/var/checkmate/chef/repo/chef-stockton

    export CHECKMATE_CONNECTION_STRING=sqlite:////var/checkmate/data/db.sqlite

    export CHECKMATE_CHEF_LOCAL_PATH=/var/chef

    bin/checkmate-queue START


In the second window, start the checkmate server & REST API:

    export CHECKMATE_BROKER_USERNAME="checkmate"
    export CHECKMATE_BROKER_PASSWORD="password"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CHECKMATE_CHEF_REPO=/var/checkmate/chef/repo/chef-stockton
    export CELERY_CONFIG_MODULE=checkmate.celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:////var/checkmate/data/db.sqlite

    export CHECKMATE_PUBLIC_KEY=`cat ~/.ssh/id_rsa.pub`  # on a mac

    bin/checkmate-server START --with-ui

There are multiple ways to use checkmate. You could browse to http://localhost:8080/ now, but below is how to make a complete deployment call using a sample deployment in simulations mode.

In the third window, run these commands to simulate a client call:

    # load your cloud credentials in (checkmate by default talks to the Racksapce cloud using the OpenStack Keystone Identity API)
    export CHECKMATE_CLIENT_APIKEY="*your_rax_API_key*"
    export CHECKMATE_CLIENT_REGION="chicago"
    export CHECKMATE_CLIENT_USERNAME="*your_rax_user*"
    export CHECKMATE_CLIENT_DOMAIN=*aworkingRAXdomain.com*
    export CHECKMATE_CLIENT_PUBLIC_KEY=`cat ~/.ssh/id_rsa.pub`

    bin/checkmate-simulate

    # this starts a deployment simulation by picking up app.yaml as a template and replacing in a bunch
    # of environment variables. Browse to http://localhost:8080/${CHECKMATE_CLIENT_TENANT}/workflows/simulate to see how the build is progressing (each reload of the page moves the workflow forward one step)

    Note: for a real deployment that creates servers, remove the /simulate part of the URL in the call above


### Authentication


Checkmate supports multiple authentication protocols and endpoints simultaneously. If it is started with a web UI (using the --with-ui) option, it will also support basic auth for browser friendliness.

#### Authenticating through a Browser

By default, three authentication domains are enabled. In a browser, if you are prompted for credentials, enter the following:

- To log in as an administrator: username and password from the machine running Checkmate (uses PAM).

- To log in to a Rackspace US Cloud Account: use US\username and password.

- To log in to a Rackspace UK Cloud Account: use UK\username and password.

#### Authenticating using REST HTTP calls

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

Checkmate has code that is python 2.7 specific. It won't work on earlier versions.

Some of checkmate's more significant dependencies are::

- celeryd: integrates with a message queue (ex. RabbitMQ)
- rabbitmq: or another backend for celery (celery even has emulators that can use a database), but rabbit is what we tested on
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


## Why the name checkmate?

My intention for this product is be a deployment _verification_ and management service, and not just a deployment automation service. So it will be used to CHECK configurations and autoMATE, not only the deployment, but the repair of live deployments as well. It also conveniently abbreviates to 'cm' which could also stand for configuration management, aludes to this being a killer app, appeals to my inner strategist, it has a 'k' sound in it which I am told by branding experts makes it sticky, and, above all, it sounds cool.

