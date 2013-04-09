
# Installing Checkmate
![Checkmate](https://github.rackspace.com/checkmate/checkmate/raw/master/checkmate/static/img/checkmate.png)

This document explains how to install Checkmate

## Automated Install Using Vagrant

You can install a Checkmate environment automatically using [vagrant](https://github.rackspace.com/checkmate/checkmate/blob/master/vagrant/README.md).


## Manual Installation

### Dependencies

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

### Requirements for Mac OSX

You need:

- python 2.7.1 or greater with easy_install (available by default on OSX)
- [git](http://git-scm.com/download) for source control
- access to Rackspace internal github, so you must be on the Rackspace network
  or on VPN.
- a c-compiler (on Mac, install X-Code from the App Store and then install the
  `Command Line tools` from XCode preferences/downloads). There is a separate
  download also available here
  https://developer.apple.com/downloads/index.action.

### Optional - Using Python Virtual Environment

A recommended way to keep Python from installing libraries is to use
virtualenv. virtualenv will create a copy of your Python binary and setup your
environment so that pip installs are placed in a local directory. This prevents
developers from needing to escalate to root to run installs.

    $ sudo easy_install virtualenv
    $ virtualenv ~/venv-checkmate
    $ source ~/venv-checkmate/bin/activate
    (venv-checkmate)$

Notice the prompt has changed to signify that the virtual environment is active.
To drop out of the virtual environment use the deactivate command:

    (venv-checkmate)$ deactivate
    $

For the rest of these instructions it is recommended that you stay inside the
virtual environment so that the setup.py files do not require root permissions
and place them in your local directory.

If you do not wish to use a virtual environment and want to develop using your
system python, you can set up all requirements using the following commands:

    # Install forks and other non-standard dependencies
    sudo pip install -r pip-requirements.txt

    # Install dependencies for running tests
    sudo pip install -r tools/test-requirements.txt

    # Point your system's python to your source code for checkmate libraries
    sudo python setup.py develop


### Install Checkmate from source

    git clone git://github.rackspace.com/checkmate/checkmate.git
    cd checkmate
    pip install -r pip-requirements.txt
    python setup.py install
    cd ..

### Install Chef

We'll document two configs. The latest, bleeding edge config for hacking and the
last known good (LKG) config.

Bleeding Edge: To install the latest Chef client, knife-solo, and
knife-solo_data_bag:

    curl chef.rackspacecloud.com/install-alt.sh | bash -s
    # Note: on a Mac, use sudo to start bash:
    # curl chef.rackspacecloud.com/install-alt.sh | sudo bash -s

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
    gem install knife-solo
    gem install knife-solo_data_bag
    gem install librarian

LKG: To install the last known good and tested config of Chef for the Checkmate
server:

    # Install RVM
    apt-get --purge remove ruby-rvm
    rm -rf /usr/share/ruby-rvm /etc/rvmrc /etc/profile.d/rvm.sh
    echo insecure > ~/.curlrc
    curl -L get.rvm.io | bash -s stable --auto
    source /etc/profile.d/rvm.sh

    # Install Ruby 1.9.3 locally
    rvm install 1.9.3-p125
    rvm use ruby-1.9.3-p125

    # Exit and delete any existing gemset (makes this idempotent)
    rvm gemset use global
    rvm --force gemset delete checkmate
    # Create a checkmate gemset
    rvm gemset create checkmate
    # Switch to it
    rvm gemset use checkmate
    # Install know good versions
    gem install bundler --no-rdoc --no-ri
    gem install chef --version 10.12.0 --no-rdoc --no-ri
    gem install knife-solo --version 0.0.13 --no-rdoc --no-ri
    gem install knife-solo_data_bag --version 0.2.1 --no-rdoc --no-ri
    gem install librarian --version 0.0.24 --no-rdoc --no-ri

    # Install the same gems in global, because root from cron needs them
    rvm gemset use global
    gem install bundler --no-rdoc --no-ri
    gem install chef --version 10.12.0 --no-rdoc --no-ri
    gem install knife-solo --version 0.0.13 --no-rdoc --no-ri
    gem install librarian --version 0.0.24 --no-rdoc --no-ri
    # Verify
    knife -v  # should show '10.12.0'
    gem list knife  # should show solo at 0.0.13 and data_bag at 0.2.1

### MongoDB Installation

Installing and starting MongoDB 2.0.6 on OSX:

    curl http://downloads.mongodb.org/osx/mongodb-osx-x86_64-2.0.6.tgz > mongo.tgz
    tar -zxvf mongo.tgz
    sudo mv mongodb-osx-x86_64-2.0.6 /opt/local/mongodb
    sudo mkdir /var/log/mongodb
    sudo chown -R root /opt/local/mongodb
    sudo sh -c 'echo "export PATH=\$PATH:/opt/local/mongodb/bin"' >> ~/.bash_profile
    source ~/.bash_profile

    # Create a data directory and start the server
    # In the checkmate directory:
    sudo mkdir data
    sudo chown -R `id -u` data
    mongod --dbpath data

### Rabbitmq Installation

Install, configure, and start rabbitmq.

    sudo apt-get -y install rabbitmq-server python-dev python-setuptools
    sudo rabbitmqctl delete_user guest
    sudo rabbitmqctl add_vhost checkmate
    sudo rabbitmqctl add_user checkmate <some_password_here>
    sudo rabbitmqctl set_permissions -p checkmate checkmate ".*" ".*" ".*"

Set the environment variable for your checkmate deployment environments and
create the directory. If you want your variable settings to look stock, set
the optional CHECKMATE_PREFIX to something like /home/myuser/checkmate.

    export CHECKMATE_PREFIX=""
    export CHECKMATE_CHEF_LOCAL_PATH="${CHECKMATE_PREFIX}/var/checkmate/deployments"
    mkdir -p $CHECKMATE_CHEF_LOCAL_PATH

### Starting the Checkmate services

Before you start one of the Checkmate services, the shell environment needs to
be prepped:

    # If you're using RabbitMQ + sqlite
    export CHECKMATE_BROKER_USERNAME="checkmate"
    export CHECKMATE_BROKER_PASSWORD="password"
    export CHECKMATE_BROKER_PORT="5672"
    export CHECKMATE_BROKER_HOST="localhost"
    export CHECKMATE_CONNECTION_STRING="sqlite:///${CHECKMATE_PREFIX}/var/checkmate/data/db.sqlite"

    # If you're using MongoDB
    # in username and passwords reserved characters like :, /, + and @ must be escaped following RFC 2396.
    export CHECKMATE_BROKER_URL="mongodb://checkmate:secret@localhost:27017/checkmate"
    export CHECKMATE_RESULT_BACKEND="mongodb"
    export CHECKMATE_MONGODB_BACKEND_SETTINGS='{"host": "localhost", "port": 27017, "user": "checkmate", "password": "secret", "database": "checkmate", "taskmeta_collection": "celery_task_meta"}'
    export CHECKMATE_CONNECTION_STRING="mongodb://checkmate:secret@localhost:27017/checkmate"

    export CHECKMATE_CHEF_LOCAL_PATH="/var/local/checkmate/deployments"

    # Always
    export CELERY_CONFIG_MODULE=checkmate.celeryconfig
    export CHECKMATE_PUBLIC_KEY=`cat ~/.ssh/id_rsa.pub`

Start the queue service (see `--eager` in checkmate-server parameter for
development without a queue):

    bin/checkmate-queue START

Start the Checkmate API and UI service:

    bin/checkmate-server START --with-ui --with-simulator
    # Or, to specify an alternate IP:Port
    bin/checkmate-server START --with-ui --with-simulator 0.0.0.0:8000


Note: A shortcut for creating the environment and running a checkmate server
using only an in-memory database and broker is:

    python tools/install_venv.py
    tools/with_venv.sh bin/checkmate-server START --with-ui --with-simulator
