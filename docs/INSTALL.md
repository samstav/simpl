# Installing Checkmate

Development: [Docker](#using-checkmate-in-docker) or
             [Vagrant](#running-checkmate-in-vagrant)

Production: [Installation](#manual-installation)

## Using Checkmate in Docker

### Set up the environment file

Using the `.checkmate_env` file in this repository, you will need to fill in the
following values:

```
# Github.com Auth (public github)
CHECKMATE_GITHUB_ENDPOINT=https://api.github.com
CHECKMATE_GITHUB_CLIENT_ID='CLIENT_ID'
CHECKMATE_GITHUB_CLIENT_SECRET='SECRET'

# SSH Configs
# Change values to use a Rackspace bastion
CHECKMATE_BASTION_ADDRESS='BASTION.ADDRESS'
CHECKMATE_BASTION_USERNAME='SSO.NAME'
CHECKMATE_BASTION_PKEY_FILE='/FULL/PATH/TO/BASTION/KEY_RSA'
```

The GitHub environment variables are optional and can be commented out if you
don't want to use them in your deployment.

### Running Checkmate in Docker containers

Assuming you are using OS X, you will need to install
[VirtualBox](https://www.virtualbox.org/wiki/Downloads) and
[boot2docker](https://docs.docker.com/installation/mac/).

If you are using Linux, you should be able to run
[Docker natively](https://docs.docker.com/installation/).

First, start docker containers for Redis and MongoDB:

```
$ docker run --name checkredis -d -p 6379:6379 dockerfile/redis
$ docker run --name checkmongo -d -p 27017:27017 dockerfile/mongodb
```

Next, build the Checkmate docker container:

`$ docker build -t checkmate .`

Next, run two containers: one for the API and one for the worker. We will also
pass in the environment file you set up in the previous step. Your bastion SSH
key also needs to be mounted to the container:

```
$ docker run -d --name checkmate-api \
--env-file=.checkmate_env \
--link checkredis:checkredis \
--link checkmongo:checkmongo \
-v /PATH/TO/MY/BASTION/SSHKEY:/root/.ssh/lnx-key.lnx:ro
-p 8080:8080 \
checkmate '/app/bin/checkmate-server START --with-ui --with-simulator 0.0.0.0:8080'
```

```
$ docker run -d --name checkmate-worker \
--env-file=.checkmate_env \
--link checkredis:checkredis \
--link checkmongo:checkmongo \
-v /PATH/TO/MY/BASTION/SSHKEY:/root/.ssh/lnx-key.lnx:ro
checkmate '/app/bin/checkmate-queue START -P eventlet'
```

You can now reach Checkmate by going to your boot2docker IP address on port
`8080`. For exaple: `http://192.168.59.103:8080`. You can find this IP with the
boot2docker command:

`$ boot2docker ip`

Log in with a US/UK cloud account. You can now experiment with Checkmatefile
deployments.

### Stop Checkmate Docker containers

```
$ docker kill checkredis checkmongo checkmate-api checkmate-worker
$ docker rm checkredis checkmongo checkmate-api checkmate-worker
```

## Running Checkmate in Vagrant

### Create a developer application in Github

1. Go to your [GitHub profile settings](https://github.com/settings/profile).
2. Click `Applications`.
3. Under the `Developer applications` heading, click `Register new application`.
4. For `Application name`, enter "Checkmate".
5. For `Homepage URL`, enter `http://127.0.0.1:8080`.
6. Click `Register application`.

### vagrant up

1. Install [VirtualBox](https://www.virtualbox.org/wiki/Downloads)
2. Install [Vagrant](https://www.vagrantup.com/downloads)
3. Clone this source repo.
4. Change into the `contrib` directory: `cd contrib`
5. Copy `.checkmate_env.example` to `.checkmate_env` and fill in the `<BLANK>`
   information.
6. Start the vagrant box: `vagrant up`
7. Login to the vagrant box: `vagrant ssh`
8. Activate the Checkmate virtual environment: `workon checkmate`
9. Change into the `/workspace` directory: `cd /workspace`
10. Start the Checkmate server:
    `bin/checkmate-server START --with-admin --worker --eventlet --with-ui --with-simulator 0.0.0.0:8080`

The Checkmate homepage should now be accessible in your browser at
http://127.0.0.1:8080.

The root of this source repo will be synchronized with the vagrant box, so you
can make code changes in the git clone in your host environment and the changes
will be reflected inside the vagrant box. Note: You will restart
`checkmate-server` for changes to take effect.

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
    sudo pip install -r requirements.txt

    # Install dependencies for running tests
    sudo pip install -r tools/test-requirements.txt

    # Point your system's python to your source code for checkmate libraries
    sudo python setup.py develop


### Install Checkmate from source

    git clone git://github.rackspace.com/checkmate/checkmate.git
    cd checkmate
    pip install -r requirements.txt
    python setup.py install
    cd ..

### Install Chef

We'll document two configs. The latest, bleeding edge config for hacking and
the last known good (LKG) config.

Bleeding Edge: To install the latest Chef client, knife-solo, and
knife-solo_data_bag:

    curl chef.rackspacecloud.com/install-alt.sh | bash -s
    # Note: on a Mac, use sudo to start bash:
    # curl chef.rackspacecloud.com/install-alt.sh | sudo bash -s

    # Install RVM
    echo insecure >> ~/.curlrc
    curl -k -L get.rvm.io | bash -s stable
    source ~/.rvm/scripts/rvm

    # Install Ruby 2.1.3 locally
    rvm install 2.1.3
    rvm use ruby-2.1.3
    rvm gemset create checkmate
    rvm gemset use checkmate
    bundle install

LKG: To install the last known good and tested config of Chef for the Checkmate
server:

    # Install RVM
    apt-get --purge remove ruby-rvm
    rm -rf /usr/share/ruby-rvm /etc/rvmrc /etc/profile.d/rvm.sh
    echo insecure > ~/.curlrc
    curl -L get.rvm.io | bash -s stable --auto-dotfiles --autolibs=enabled
    source /etc/profile.d/rvm.sh

    # Install Ruby 1.9.3 locally
    rvm install 2.1.3
    rvm use ruby-2.1.3

    # Exit and delete any existing gemset (makes this idempotent)
    rvm gemset use global
    rvm --force gemset delete checkmate
    # Create a checkmate gemset
    rvm gemset create checkmate
    # Switch to it
    rvm gemset use checkmate
    # Install know good versions
    gem install bundler --no-rdoc --no-ri
    bundle install

    # Verify
    knife -v  # should show 'Chef: 12.3.x'
    gem list knife  # should show solo at 0.3.0 and data_bag at 0.4.0

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

```
sudo apt-get -y install rabbitmq-server python-dev python-setuptools
sudo rabbitmqctl delete_user guest
sudo rabbitmqctl add_vhost checkmate
sudo rabbitmqctl add_user checkmate <some_password_here>
sudo rabbitmqctl set_permissions -p checkmate checkmate ".*" ".*" ".*"
```

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
    # in username and passwords reserved characters like :, /, + and @ must be
    # escaped following RFC 2396.
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
