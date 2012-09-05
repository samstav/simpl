# Installing Checkmate By Hand
![Checkmate](https://github.rackspace.com/checkmate/checkmate/raw/master/checkmate/static/img/checkmate.png)


This document explains how to install Checkmate by hand. If you are looking for
a get a development box up quickly, see
[vagrant](https://github.rackspace.com/checkmate/checkmate/blob/master/vagrant/README.md).

## Dependencies

Checkmate is mostly a python service. Therefore, most installations can be
done with python tools like pip or easy_install. There are two main exceptions
to this:

1. Chef: chef is a ruby-based app that is used to handle application
configuration on servers.

2. Forks: of existing projects are sometimes used to support functionality that
is not available for a system like checkmate. For example, checkmate uses
OpenStack auth tokens to call OpenStack services. Many of the libraries for
OpenStack services are rapidly evolving and designed for command-line use.
Another example is the SpiffWorkflow workflow engine. This is a project
developed in an academic setting and needed significant patching to work with
checkmate. For these projects, we maintain our own forks that need to be
deployed with checkmate. All modifications are intended to be proposed upstream.

## Optional - Using Python Virtual Environment

A recommended way to keep Python from installing libraries is to use
virtualenv. virtualenv will create a copy of your Python binary and setup your
environment so that pip installs are placed in a local directory. This prevents
developers from needing to escalate to root to run installs.

    $ sudo apt-get install python-virtualenv
    $ virtualenv ~/venv-checkmate
    $ source ~/venv-checkmate/bin/activate
    (venv-checkmate)$

Notice the promt has changed to signify that the virtual environment is active.
To drop out of the virtual environment use the deactivate command:

    (venv-checkmate)$ deactive
    $

For the rest of these instructions it is recommended that you stay inside the
virtual environment so that the setup.py files do not require root permissions
and place them in your local directory.

## Install Checkmate from source

    $ git clone git://github.rackspace.com/checkmate/checkmate.git
    $ cd checkmate
    $ pip install -r pip-requirements.txt
    $ cd ..

## Install Chef

Install the latest Chef client, knife-solo, and knife-solo_data_bag:

    $ curl chef.rackspacecloud.com/install-alt.sh | bash -s

    # Install RVM
    $ echo insecure >> ~/.curlrc
    $ curl -k -L get.rvm.io | bash -s stable
    $ source ~/.rvm/scripts/rvm

    # Install Ruby 1.9.3 locally
    $ rvm install 1.9.3-p125
    $ rvm use ruby-1.9.3-p125
    $ rvm gemset create chef
    $ rvm gemset use chef
    $ gem install bundler
    $ gem install knife-solo --version 0.0.10
    $ gem install knife-solo_data_bag --version 0.2.1

## Rabbitmq Installation

Install, configure, and start rabbitmq.

    $ sudo apt-get -y install rabbitmq-server python-dev python-setuptools
    $ sudo rabbitmqctl delete_user guest
    $ sudo rabbitmqctl add_vhost checkmate
    $ sudo rabbitmqctl add_user checkmate <some_password_here>
    $ sudo rabbitmqctl set_permissions -p checkmate checkmate ".*" ".*" ".*"

Set the environment variable for your checkmate deployment environments and
create the directory. If you want your variable settings to look stock, set
the optional CHECKMATE_PREFIX to something like /home/myuser/checkmate.

    $ export CHECKMATE_PREFIX=""
    $ export CHECKMATE_CHEF_LOCAL_PATH="${CHECKMATE_PREFIX}/var/checkmate/chef"
    $ mkdir -p $CHECKMATE_CHEF_LOCAL_PATH

Clone the chef repository and point checkmate to it:

    $ export CHECKMATE_CHEF_REPO="${CHECKMATE_PREFIX}/var/checkmate/chef/repo"
    $ mkdir -p $CHECKMATE_CHEF_REPO
    $ cd $CHECKMATE_CHEF_REPO
    $ git clone git://github.rackspace.com/checkmate/chef-stockton.git

## Starting the Checkmate services

Before you start one of the Checkmate services, the shell environment needs to
be prepped:

    $ export CHECKMATE_BROKER_USERNAME="checkmate"
    $ export CHECKMATE_BROKER_PASSWORD="password"
    $ export CHECKMATE_BROKER_PORT="5672"
    $ export CHECKMATE_BROKER_HOST="localhost"
    $ export CELERY_CONFIG_MODULE=checkmate.celeryconfig
    $ export CHECKMATE_CHEF_REPO="${CHECKMATE_PREFIX}/var/checkmate/chef/repo/chef-stockton"
    $ export CHECKMATE_CONNECTION_STRING="sqlite:///${CHECKMATE_PREFIX}/var/checkmate/data/db.sqlite"
    $ export CHECKMATE_CHEF_LOCAL_PATH="${CHECKMATE_PREFIX}/var/checkmate/chef"
    $ export CHECKMATE_PUBLIC_KEY=`cat ~/.ssh/id_rsa.pub`

Start the queue service:

    $ bin/checkmate-queue START

Start the Checkmate API and UI service:

    $ bin/checkmate-server START --with-ui
    $ bin/checkmate-server START --with-ui 0.0.0.0:8000 # Specify alternate IP:Port