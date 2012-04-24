# CheckMate
![CheckMate](https://github.com/ziadsawalha/checkmate/raw/master/checkmate/checkmate.png)

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

You should also have Stockton running (see Stockton docs for setting Stockton
up), but when starting up Stockton, make sure to add the checkmate
orchestrator::

    $ celeryd -l info --config=celeryconfig -I Stockton,checkmate.orchestrator

This will add additional calls to celery.


### Sample Call

You'll need three terminal windows and Rackspace cloud credentials (username &
API key). In the first terminal window, start Stockton::

    export BROKER_USERNAME="Stockton"
    export BROKER_PASSWORD="Stockton"
    export BROKER_PORT="5672"
    export BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=celeryconfig

    export CHECKMATE_CONNECTION_CONNECTION=sqlite:///~/checkmate.sqlite

    export STOCKTON_CHEF_PATH=/var/chef
    export STOCKTON_APIKEY="abcedf...."
    export STOCKTON_REGION="chicago"
    export STOCKTON_USERNAME="me"
    export STOCKTON_PUBLIC_KEY=~/.ssh/id_rsa.pub  # on a mac
    export STOCKTON_PRIVATE_KEY=~/.ssh/id_rsa     # on a mac
    export STOCKTON_TEST_DOMAIN=validInRaxDNS.local

    celeryd -l info --config=celeryconfig -I Stockton,checkmate.orchestrator

In the second window, start checkmate::

    export BROKER_USERNAME="Stockton"
    export BROKER_PASSWORD="Stockton"
    export BROKER_PORT="5672"
    export BROKER_HOST="localhost"
    export CELERY_CONFIG_MODULE=celeryconfig

    export CHECKMATE_CONNECTION_CONNECTION=sqlite:///~/checkmate.sqlite

    export STOCKTON_CHEF_PATH=/var/chef
    export STOCKTON_APIKEY="abcedf...."
    export STOCKTON_REGION="chicago"
    export STOCKTON_USERNAME="me"
    export STOCKTON_PUBLIC_KEY=~/.ssh/id_rsa.pub  # on a mac
    export STOCKTON_PRIVATE_KEY=~/.ssh/id_rsa     # on a mac
    export STOCKTON_TEST_DOMAIN=validInRaxDNS.local

    python checkmate/server.py

In the third window, run these scripts::

    $ curl --data-binary @checkmate/examples/app.yaml -H 'content-type: application/x-yaml' http://localhost:8080/deployments -v

    # this starts a deployment. Get the ID or Location header from the response, and watch the status here:
    
    $ curl http://localhost:8080/deployments/enter-your-deployment-id-here/status



### Dependencies

Some of checkmate more significant dependencies are::

- python-stockton: for managing Rackspace cloud services
- celeryd: used by Stockton and integrates with a message queue (ex. RabbitMQ)
- rabbitmq: or another backend for celery, but rabbit is what we tested on
- SpiffWorkflow: a python workflow engine
- chef: OpsCode's chef... and a chef server for now...

