# Checkmate
![Checkmate](docs/img/checkmate.png)

## Overview
Checkmate stores and controls your cloud configurations. Use it to deploy and manage complete application stacks.

It exposes a REST API for manipulating configurations. It uses celery for task queuing and SpiffWorkflow to orchestrate deploying them. It support JSON and YAML interchangeably. It has optional built-in browser support with a UI.

Checkmatefile examples are available on [Rackspace github](https://github.rackspace.com/Blueprints).

## Logic: the pieces
In a nutshell:

1. An expert writes a `blueprint` for how an app can be deployed.
2. The blueprint contains `components`, relationships between these components,
   and options and constraints on how the app works.
3. An end-user defines `environments` where they want to deploy apps (ex. a
   laptop, an OpenStack Cloud, a Rackspace US Cloud account)
4. The end-user picks a blueprint (ex. a Scalable Wordpress blueprint) and
   deploys it to an environment of their choice. That's a `deployment` and
   results in a fully built and running, multi-component app.
5. Checkmate knows how to add/remove servers (**scaling**) and can verify the
   app is running and perform troubleshooting (**configuration management**)

## Checkmatefile (deployment templates) development

See [Checkmatefile docs](docs/Checkmatefile.md)

## The API

See [API docs](docs/API.md)

### Environment Variables / Settings

See [Environment docs](docs/Environment.md)

## Checkmate Installation & Setup

See the [INSTALL.md](docs/INSTALL.md) file for installing Checkmate as a
production service or for development.

### Dependencies

Checkmate has code that is python 2.7.1 specific. It won't work on earlier versions.

Some of checkmate's more significant dependencies are::

- celery: integrates with a message queue (ex. RabbitMQ)<sup>*</sup>
- eventlet: coroutine-based concurrency library<sup>*</sup>
- a message broker (rabbitmq or mongodb): any another backend for celery should
  work (celery even has emulators that can use a database), but rabbit and mongo
  are what we tested on
- SpiffWorkflow: a python workflow engine
- chef: OpsCode's chef... you don't need a server, but use with a server is
  supported.
- cloud service client libraries: python-novaclient, python-clouddb, etc...
- rook: a UI middleware that enables checkmate to respond to browser calls in
  HTML.

When hacking on checkmate, please be careful not to `eventlet.monkey_patch()`
modules containing any celery tasks; this can cause unexpected behavior with
celery workers. If you need to import a patched dependency, use
`eventlet.import_patched()` for specific libraries

#### SpiffWorkflow
Necessary additions to SpiffWorkflow are not yet in the source repo, so install
the development branch from this fork:

    $ git clone -b master https://github.rackspace.com/checkmate/SpiffWorkflow
    $ cd SpiffWorkflow
    $ sudo python setup.py install

#### python-novacalient
Necessary patches to python-novacalient are not yet in the source repo, so
install the development branch from this fork:

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

#### Mox

This is a library used for testing. The source code includes some highly useful
updates which have not yet made it into the published binaries. While the public
library will work fine, I recommend doing the following:

    # Get the latest source code
    svn checkout http://pymox.googlecode.com/svn/trunk/ pymox-read-only
    # Install it
    cd pymox-read-only
    sudo python setup.py install

Note: we plan to move to mock.

## Testing

To quickly test one file (--verbose optional, extra -- needed for tox)

    tox tests/test_schema.py -- --verbose
    python tests/test_schema.py --verbose

To run a full suite (with coverage and code inspection)
    tox -e full

Any of these will work

    tox

    nosetests

    python setup.py test

Requirements lists:

- production: requirements.txt
- development: test-requirements.txt

### Cloud Cafe & Checkmate

#### Installing Cloud Cafe
In order to run the QE tests for Checkmate, you will need to start with the
[install of Cloud Cafe](https://github.rackspace.com/Cloud-QE/CloudCAFE-Python)

#### Running the QE Tests
In your Cloud Cafe install (git cloned) directory
(i.e. \<workspace\>/CloudCafe-Python/) you should now be able to run:

    bin/runner.py

With no options, it will give the help menu.

To run the checkmate smoke tests, run:

    bin/runner.py checkmate $CONFIG -m smoketest

where `$CONFIG` is the `.config` file to run the tests against
(i.e. localhost/dev/qa/staging/prod)

#### Where to find the QE checkmate configurations

    $WORKSPACE/CloudCafe-Python/config/checkmate

#### Where to find the QE checkmate test cases

    $WORKSPACE/CloudCafe-Python/lib/testrepo/checkmate

#### SPECIAL: Offline Blueprint development testing

Set the `blueprint_test_path` variable in your localhost.config file

To run tests against blueprints that you (the blueprint developer) are actively
developing, please run:

    cd $WORKSPACE/CloudCafe-Python
    bin/runner.py checkmate localhost.config -m offline_blueprint_validation

## Hacking & Contributing:

We're using github and its fork & pull. There are great instructions on that on
[GitHub](https://help.github.com/).

You can run tests using the `run_tests.sh` script or just the plain
`nosetests` command. `./run_tests.sh` has more friendly output.

We use GitHub for tracking our backlog and tasks.

See the [HACKING](HACKING.rst) file for our chosen style conventions.
