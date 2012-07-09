# CheckMate
![CheckMate](https://github.rackspace.com/checkmate/checkmate/raw/master/checkmate/static/checkmate.png)

CheckMate stores and controls your cloud configurations. Use it to deploy complete application stacks.

It exposes a REST API for manipulating configurations. It uses celery for task queuing and SpiffWorkflow to orchestrate deploying them. It support JSON and YAML interchangeably. It has optional built-in browser support & a UI.

## The API

POST, PUT, GET on /components[/:id], /blueprints[/:id], /environments[/:id],
/deployments[/:id], and /workflows[/:id]

PUT updates without taking any action.
POST can trigger actions (like actual server deployments)

Objects are returned as JSON by default, but YAML is also supported (application/x-yaml)
HTML output is also supported if the server is started with a `--with-ui` parameter.

Special cases::

    POST /deployment

        Create a new deployment passing in all the necessary components, blueprints, environments, etc... (or
        references to them).

### Components

These are the equivalent of Chef recipes or Juju charms. They are the building
blocks of an application deployment. These can be supplied as part of a deployment or looked up from the server.

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
        summary: "A pretty popular database"
        provides:
          db: mysql


### Environments

An environment is a place where you can launch and manage application deployments. It could be your development laptop, a cloud provider, or a combination of cloud providers that you have grouped together to use together as a single environment.
Multiple environments can exist in one tenant or account. For example, you could have dev, test, staging, and production environments on one Rackspace Cloud account.

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


### Blueprints

These define the architecture for an application. The blueprint describes the
resources needed and how to connect and scale them when deploying and managing an application.

    # An wordpress architecture template
    blueprint: &wp
      name: Multi-server Wordpress
      services:
        lb:
          components: *loadbalancer
          relations:
            web: http
          exposed: true
          open-ports: [80/tcp]
        web:
          components: *wordpress_reference_id  # wordpress component above
          relations: {backend: mysql}
        backend:
          components: *mysql
      options:
        blueprint:
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

A deployment defines and points to a running application and the infrastructure it is running on. It combines a blueprint, an environment to deploy the resources to, and any additional inputs specific to this deployment.


    # Actual running app and the parameters supplied when deploying it
    deployment:
      blueprint: *wp
      environment: *environment_1000_stag
      inputs:
        instance_count: 4
      resources:
        '0':
          type: server
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
          dns-name: CMDEP32ea304-db1.rackcloudtech.com
          flavor: 1
          instance:
            id: 99958744

Once deployed, the live resources running the application are also listed. The intent is for CheckMate to be able to manage the deployment. An example of a management operation would be resizing the servers:

  1 - bring down the load-balancer connection for srv1 (knowing srv2 is up)

  2 - resize srv1

  3 - bring the load balancer connection back up

  4 - perform the same on srv1

Such an operation cannot be performed by the underlying services alone since they have no knowledge of the full stack like checkmate does.


Note: for additional descriptions of each field see the examples/app.yaml file.


## Usage

CheckMate is a REST server. To run it:

    $ python checkmate/server.py

Options:

        --with-ui:  enable support for browsers and HTML templates
        --newrelic: enable newrelic monitoring (place newrelic.ini in your
                    directory)
        --quiet:    turn down logging to WARN (default is INFO)
        --verbose:  turn up logging to DEBUG (default is INFO)
        --debug:    turn on additional debugging inspection and output
                    including full HTTP requests and responses

You also need to have celery running with the checkmate tasks loaded:

    $ celeryd -l info --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode

### Settings

The following environment variables can be set to configure checkmate:

    CHECKMATE_CONNECTION_STRING

    CHECKMATE_DOMAIN
    CHECKMATE_PUBLIC_KEY
    CHECKMATE_CHEF_REPO
    CHECKMATE_CHEF_LOCAL_PATH - local
    CHECKMATE_CHEF_PATH - server

    CHECKMATE_BROKER_USERNAME
    CHECKMATE_BROKER_PASSWORD
    CHECKMATE_BROKER_HOST
    CHECKMATE_BROKER_PORT
    or
    CHECKMATE_BROKER_URL

    CELERY_CONFIG_MODULE
    CELERYD_FORCE_EXECV


    Deprecated:
    CHECKMATE_DATA_PATH - used with file system data provider
    CHECKMATE_PRIVATE_KEY


## CheckMate Installation

Create and go to the directory you want to install CheckMate in:

Install Chef client and knife-solo:

  # Get latest chef code
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

Install CheckMate:

  git clone http://github.com/ziadsawalha/checkmate.git
  cd checkmate
  git checkout master
  python setup.py install
  cd ..

Install SpiffWorkflow:

  git clone http://github.com/ziadsawalha/SpiffWorkflow.git
  cd SpiffWorkflow
  git checkout celery
  python setup.py install
  cd ..

Install, configure, and start rabbitmq.

    $ sudo apt-get -y install rabbitmq-server python-dev python-setuptools
    $ sudo rabbitmqctl delete_user guest
    $ sudo rabbitmqctl add_vhost checkmate
    $ sudo rabbitmqctl add_user checkmate <some_password_here>
    $ sudo rabbitmqctl set_permissions -p checkmate checkmate ".*" ".*" ".*"
    $ sudo rabbitmq-server -detached

Set the environment variable for your checkmate environments and create the directory:

    $ export CHECKMATE_CHEF_LOCAL_PATH=/var/checkmate/environments
    $ mkdir -p $CHECKMATE_CHEF_LOCAL_PATH


### Authentication


CheckMate supports multiple authentication protocols and endpoints simultaneously. If is is started with a web UI (using the --with-ui) option, it will also support basic auth for browser friendliness.

#### Authenticating through a Browser

By default, three authentication domains are enabled. In a browser, if you are prompted for credentials, enter the following:

- To log in as an administrator: username and password from the machine running CheckMate.

- To log in to a US Cloud Account: use US\username and password.

- To log in to a UK Cloud Account: use UK\username and password.

#### Authenticating using REST

CheckMate supports standard Rackspace\OpenStack authentication with a token. Get a token from your auth endpoint (US or UK!) and provide it in the X-Auth-Header:

    curl -H "X-Auth-Token: ccdcd4f9-d72d-5677-8b1a-f329389cc539" http://localhost:8080/4500 -v

CheckMate will try the US and then UK endpoints.

To avoid hitting the US for each UK call, and to be a good citizen, tell CheckMate which endpoint your token came from using the X-Auth-Source header:

    curl -H "X-Auth-Source: https://lon.identity.api.rackspacecloud.com/v2.0/tokens" -H "X-Auth-Token: ccdcd4f9-d72d-5677-8b1a-f329389cc539" http://localhost:8080/1000002 -v

Note: This is a CheckMate extension to the auth mechanism. This won't work on any other services.


### Trying a test call

You'll need three terminal windows and Rackspace cloud credentials (username &
API key). In the first terminal window, start the task queue:

    export CHECKMATE_BROKER_USERNAME="checkmate"
    export CHECKMATE_BROKER_PASSWORD="password"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=checkmate.celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:////var/checkmate/data/db.sqlite

    export CHECKMATE_CHEF_LOCAL_PATH=/var/chef

    celeryd -l info --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode


In the second window, start the checkmate server & REST API:

    export CHECKMATE_BROKER_USERNAME="checkmate"
    export CHECKMATE_BROKER_PASSWORD="password"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=checkmate.celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:////var/checkmate/data/db.sqlite

    export CHECKMATE_PUBLIC_KEY=~/.ssh/id_rsa.pub  # on a mac

    python checkmate/server.py --with-ui

In the third window, run these commands to simulate a client call:

    export CHECKMATE_CLIENT_APIKEY="*your_rax_API_key*"
    export CHECKMATE_CLIENT_REGION="chicago"
    export CHECKMATE_CLIENT_USERNAME="*your_rax_user*"
    export CHECKMATE_CLIENT_DOMAIN=*aworkingRAXdomain.com*
    export CHECKMATE_CLIENT_PUBLIC_KEY=`cat ~/.ssh/id_rsa.pub`

    # Yes, sorry, this is long. It's mostly auth and template replacement stuff
    CHECKMATE_CLIENT_TENANT=$(curl -H "X-Auth-User: ${CHECKMATE_CLIENT_USERNAME}" -H "X-Auth-Key: ${CHECKMATE_CLIENT_APIKEY}" -I https://identity.api.rackspacecloud.com/v1.0 -v 2> /dev/null | grep "X-Server-Management-Url" | grep -P -o $'(?!.*/).+$'| tr -d '\r') && CHECKMATE_CLIENT_TOKEN=$(curl -H "X-Auth-User: ${CHECKMATE_CLIENT_USERNAME}" -H "X-Auth-Key: ${CHECKMATE_CLIENT_APIKEY}" -I https://identity.api.rackspacecloud.com/v1.0 -v 2> /dev/null | grep "X-Auth-Token:" | awk '/^X-Auth-Token:/ { print $2 }') && awk '{while(match($0,"[$][\\{][^\\}]*\\}")) {var=substr($0,RSTART+2,RLENGTH -3);gsub("[$][{]"var"[}]",ENVIRON[var])}}1' < examples/app.yaml | curl -H "X-Auth-Token: ${CHECKMATE_CLIENT_TOKEN}" -H 'content-type: application/x-yaml' http://localhost:8080/${CHECKMATE_CLIENT_TENANT}/deployments/simulate -v --data-binary @-

    # this starts a deployment simulation by picking up app.yaml as a template and replacing in a bunch
    # of environment variables. Browse to http://localhost:8080/${CHECKMATE_CLIENT_TENANT}/workflows/simulate to see how the build is progressing (each reload of the page moves the workflow forward one step)

    Note: for a real deployment that creates servers, remove the /simulate part of the URL in the call above

## Tools

### Monitoring

celery has a tool called celeryev that can monitor running tasks and events. To
use it, you need to turn `events` on when running celeryd using -E or --events:

    celeryd -l debug --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --events

And then use celeryev from the python-stockton directory to watch events and tasks::

    celeryev --config=checkmate.celeryconfig

### Tuning

The following has been tested to run up to 10 simultaneous workflows using amqp::

    celeryd --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --autoscale=10,2

On Unix/Linux Systems (including Mac), the following
setting resolves issues with workers hanging::

    export CELERYD_FORCE_EXECV=1


### Dependencies

Some of checkmate's more significant dependencies are::

- celeryd: also used by Stockton and integrates with a message queue (ex. RabbitMQ)
- rabbitmq: or another backend for celery (celery even has emulators that can use a database), but rabbit is what we tested on
- SpiffWorkflow: a python workflow engine
- chef: OpsCode's chef... you don't need a server.
- cloud client libraries: python-novaclient, python-clouddb, etc...

#### SpiffWorkflow
Necessary additions to SpiffWorkflow are not yet in the source repo, so install
the development branch from this fork:

    $ git clone -b master https://github.rackspace.com/checkmate/SpiffWorkflow
    $ cd SpiffWorkflow
    $ sudo python setup.py install

#### Chef

The chef-local provider uses the following environment variables::

    CHECKMATE_CHEF_REPO: used to store a master copy of all cookbooks used
    CHECKMATE_CHEF_LOCAL_PATH: used to store all environments

### Celery

[celeryd](http://www.celeryproject.org/) does the heavy lifting for
distributing tasks and retrying those that fail.
