
![CheckMate](https://github.com/ziadsawalha/checkmate/raw/master/checkmate/checkmate.png)

# CheckMate

CheckMate stores and controls your cloud configurations. It exposes a REST API
for manipulating configurations. It uses python-stockton and SpiffWorkflow to
deploy them. It support JSON and YAML configurations. The configurations try to
be compatible or close to other projects like Juju.

## The API

POST /deployment

    Create a new deployment passsing in all the necessary components (or references to
    them).


GET /environments

    Gets a list of environments in the system. JSON is default, YAML is also supported.


## Usage


### with python-stockton

Command to start the orchestrator with stockton::

    celeryd -l info --config=celeryconfig -I stockton,checkmate.orchestrator

This will add additional calls to celery.

