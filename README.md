# CheckMate
![CheckMate](https://github.com/ziadsawalha/checkmate/raw/master/checkmate/static/checkmate.png)

CheckMate stores and controls your cloud configurations. It exposes a REST API
for manipulating configurations. It uses python-stockton and SpiffWorkflow to
deploy them. It support JSON and YAML configurations. The configurations try to
be compatible or close to other projects like Juju.

## The API

POST, PUT, GET on /components[/:id], /blueprints[/:id], /environments[/:id],
and /deployments[/:id]

PUT updates without taking any action.
POST can trigger actions (like actual server deployments)

Objects are returned as JSON by default, but YAML is also supported (application/x-yaml)

Special cases::

    POST /deployment

        Create a new deployment passing in all the necessary components (or
        references to them).

### Components

This is the equivalent of Chef recipes or Juju charms. They are the building
blocks of a deployment.

    # Definitions of components/services used (based on Juju charm syntax)
    components:
      wordpress: &wordpress
        revision: 3
        summary: "A pretty popular blog engine"
        provides:
          url:
            interface: http
        requires:
          db:
           interface: mysql
        options:
          url:
            type: String
            default: wp.test.local
            description: the url to use to host your blog on

      mysql: &mysql
        revision: 1
        summary: "A pretty popular database"
        provides:
          db: mysql

### Environments

This is a where you deploy things. Consider Environments as a group of
resources configured collaboratively to deliver an application (like a
wordpress blog).
Multiple environments can exist in one tenant or account. Example: dev, test, staging, and production.

    # Environment
    environment: &env1
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

### Blueprints

These define the architecture for an application. The blueprint describes the
resources needed and how to connect and scale them.

    # An wordpress architecture template
    blueprint: &wp
      name: Simple Wordpress
      wordpress:
        exposed: true
        open-ports: [80/tcp]
        config: *wordpress  # points to wordpress component
        relations: {db: mysql}
      mysql:
        config: *mysql


### Deployments

A deployment is the definition of a running application. It consists of a
blueprint (which determines a set of components) and an environment to deploy
the resources to. Once deployed and configured, the application should be up
and running.

    # Actual deployment instance and the parameters requested for it
    deployment:
      blueprint: *wp
      environment: *production1
      inputs:
        domain: mydomain.com
        ssl: false
        region: chicago
        high-availability: false
        requests-per-second: 60

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

    export BROKER_USERNAME="Stockton"
    export BROKER_PASSWORD="Stockton"
    export BROKER_PORT="5672"
    export BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:///~/checkmate.sqlite

    export STOCKTON_CHEF_PATH=/var/chef
    export STOCKTON_PUBLIC_KEY=~/.ssh/id_rsa.pub  # on a mac
    export STOCKTON_PRIVATE_KEY=~/.ssh/id_rsa     # on a mac
    export STOCKTON_TEST_DOMAIN=validInRaxDNS.local
    celeryd -l info --config=celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode


In the second window, start checkmate::

    export BROKER_USERNAME="Stockton"
    export BROKER_PASSWORD="Stockton"
    export BROKER_PORT="5672"
    export BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=celeryconfig

    export CHECKMATE_CONNECTION_STRING=sqlite:///~/checkmate.sqlite

    export CHECKMATE_PUBLIC_KEY=~/.ssh/id_rsa.pub  # on a mac
    export CHECKMATE_PRIVATE_KEY=~/.ssh/id_rsa     # on a mac

    python checkmate/server.py

In the third window, run these scripts::

    export CHECKMATE_APIKEY="*your_rax_API_key*"
    export CHECKMATE_REGION="chicago"
    export CHECKMATE_USERNAME="*your_rax_user*"
    export CHECKMATE_DOMAIN=*aworkingRAXdomain.com*
    export CHECKMATE_PUBLIC_KEY=~/.ssh/id_rsa.pub
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

