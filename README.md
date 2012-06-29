# CheckMate
![CheckMate](https://github.com/ziadsawalha/checkmate/raw/master/checkmate/static/checkmate.png)

CheckMate stores and controls your cloud configurations. It exposes a REST API
for manipulating configurations. It uses celery for task queuing and SpiffWorkflow to orchestrate deploying them. It support JSON and YAML configurations.

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

This is the equivalent of Chef recipes or Juju charms. They are the building
blocks of a deployment. These can be supplied as part of a deployment or referenced from a provider.

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

An environment is a place where you can launch and manage deployments. It could be your development laptop, a cloud provider, or a combination of cloud providers that you have grouped together to use as your environment.
Multiple environments can exist in one tenant or account. Example: dev, test, staging, and production.

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
resources needed and how to connect and scale them.

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

A deployment defines and points to a running application stack. It consists of a
blueprint, an environment to deploy the resources to, and any additional inputs specific to this deployment.


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

Once deployed, the live resources running the application are also listed. The intent is for CheckMate to be able to manage the deployment. An example of a management operation would be resixzing the servers:
1 - bring down the load-balancer connection for srv1 (knowing srv2 is up)
2 - resize srv1
3 - bring the load balancer connection back up
4 - perform the same on srv1

Such an operation cannot be performed by the underlying services since they have no knowledge of the full stack like checkmate does.


Note:: for additional description of each fields see examples/app.yaml


## Usage

CheckMate is a REST server. To run it::

    $ python checkmate/server.py

Options::

    --with-ui: enable support for browsers and HTML templates
    --debug: log full request/response
    --newrelic: enable newrelic monitoring

You also need to have celery running with the checkmate tasks loaded::

    $ celeryd -l info --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode

### Celery Installation

[celeryd](http://www.celeryproject.org/) does the heavy lifting for
distributing tasks and retrying those that fail.

Install, configure, and start rabbitmq.

    $ sudo apt-get -y install rabbitmq-server python-dev python-setuptools
    $ sudo rabbitmqctl delete_user guest
    $ sudo rabbitmqctl add_vhost checkmate
    $ sudo rabbitmqctl add_user checkmate <some_password_here>
    $ sudo rabbitmqctl set_permissions -p checkmate checkmate ".*" ".*" ".*"
    $ sudo rabbitmq-server -detached


### Trying a test call

You'll need three terminal windows and Rackspace cloud credentials (username &
API key). In the first terminal window, start Stockton::

    export CHECKMATE_BROKER_USERNAME="Stockton"
    export CHECKMATE_BROKER_PASSWORD="Stockton"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:///~/checkmate.sqlite

    export CHECKMATE_CHEF_LOCAL_PATH=/var/chef

    celeryd -l info --config=celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode


In the second window, start checkmate::

    export CHECKMATE_BROKER_USERNAME="Stockton"
    export CHECKMATE_BROKER_PASSWORD="Stockton"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=checkmate.celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:///~/checkmate.sqlite

    export CHECKMATE_PUBLIC_KEY=~/.ssh/id_rsa.pub  # on a mac
    export CHECKMATE_PRIVATE_KEY=~/.ssh/id_rsa     # on a mac

    python checkmate/server.py --with-ui

In the third window, run these scripts::

    export CHECKMATE_CLIENT_APIKEY="*your_rax_API_key*"
    export CHECKMATE_CLIENT_REGION="chicago"
    export CHECKMATE_CLIENT_USERNAME="*your_rax_user*"
    export CHECKMATE_CLIENT_DOMAIN=*aworkingRAXdomain.com*
    export CHECKMATE_CLIENT_PUBLIC_KEY=~/.ssh/id_rsa.pub

    # Yes, sorry, this is long. It's mostly auth and template replacement stuff
    CHECKMATE_CLIENT_TENANT=$(curl -H "X-Auth-User: ${CHECKMATE_CLIENT_USERNAME}" -H "X-Auth-Key: ${CHECKMATE_CLIENT_APIKEY}" -I https://identity.api.rackspacecloud.com/v1.0 -v 2> /dev/null | grep "X-Server-Management-Url" | grep -P -o $'(?!.*/).+$'| tr -d '\r') && CHECKMATE_CLIENT_TOKEN=$(curl -H "X-Auth-User: ${CHECKMATE_CLIENT_USERNAME}" -H "X-Auth-Key: ${CHECKMATE_CLIENT_APIKEY}" -I https://identity.api.rackspacecloud.com/v1.0 -v 2> /dev/null | grep "X-Auth-Token:" | awk '/^X-Auth-Token:/ { print $2 }') && awk '{while(match($0,"[$][\\{][^\\}]*\\}")) {var=substr($0,RSTART+2,RLENGTH -3);gsub("[$][{]"var"[}]",ENVIRON[var])}}1' < examples/app.yaml | curl -H "X-Auth-Token: ${CHECKMATE_CLIENT_TOKEN}" -H 'content-type: application/x-yaml' http://localhost:8080/${CHECKMATE_CLIENT_TENANT}/deployments/simulate -v --data-binary @-

    # this starts a deployment by picking up app.yaml as a template and replacing in a bunch
    # of environment variables. Browse to http://localhost:8080/${CHECKMATE_CLIENT_TENANT}/workflows/simulate to see how the build is progressing

    Note:: for a real deployment that creates servers, remove the /simulate part of the URL in the call above

## Tools

### Monitoring

celery has a tool called celeryev that can monitor ruinning tasks and events. To
use it, you need to turn `events` on when running celeryd using -E or --events:

    celeryd -l debug --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --events

And then use celeryev from the python-stockton directory to watch events and tasks::

    celeryev --config=celeryconfig

### Tuning

The following has been tested to run up to 10 simultaneous workflows using amqp::

    celeryd --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --autoscale=10,2

On Unix/Linux Systems (including Mac), the following
setting resolves issues with workers hanging::

    export CELERYD_FORCE_EXECV=1


### Dependencies

Some of checkmate's more significant dependencies are::

- python-stockton: for managing Rackspace cloud services
- celeryd: also used by Stockton and integrates with a message queue (ex. RabbitMQ)
- rabbitmq: or another backend for celery (celery even has emulators that can use a database), but rabbit is what we tested on
- SpiffWorkflow: a python workflow engine
- chef: OpsCode's chef... you don't need a server.

#### Chef

The chef-local provider uses the following environment variables::

    CHECKMATE_CHEF_REPO: used to store a master copy of all cookbooks used
    CHECKMATE_CHEF_LOCAL_PATH: used to store all environments
