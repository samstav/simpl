#!/bin/bash
### Set up virtual environment ###
PYENV_HOME=$WORKSPACE/../.checkmate_pyenv/

# Create virtualenv and install necessary packages
. $PYENV_HOME/bin/activate

if [ "$CLEAN_DEPS" != "false" ]
then
        pip install -U --force-reinstall -r $WORKSPACE/pip-requirements.txt $WORKSPACE/
else
        pip install -r $WORKSPACE/pip-requirements.txt $WORKSPACE/
fi

# make sure we pull the latest chef recipies
find ./checkmate -type d -name chef-stockton -exec rm -rf {} \; || exit 0


### Run tests ###
### Configure rvm use for chef tests.
. ~/.rvm/environments/ruby-1.9.3-p125@checkmate

env
which knife        

### Clean up tmp directory
if [ -d /tmp/checkmate/test ]; then
        rm -rf /tmp/checkmate/test
fi

### Set up virtual environment ###
PYENV_HOME=$WORKSPACE/../.checkmate_pyenv/
### Activate virtual environment ###
. $PYENV_HOME/bin/activate

### Set chef-stockton location for chef provider tests.
export CHECKMATE_CHEF_REPO=$WORKSPACE/chef-stockton

### Clone the chef-stockton repo
git clone -b master git://github.rackspace.com/checkmate/chef-stockton.git $CHECKMATE_CHEF_REPO

# return success so the build does not fail on test failures/errors by appending || exit 0 below
# the JUnit Report publisher should take care of marking build status appropriately
nosetests --with-coverage --cover-package=checkmate --with-xunit -w tests/

# Create coverage.xml for Cobertura
coverage xml --include="checkmate/**"


### Run Pylint ###

PYENV_HOME=$WORKSPACE/../.checkmate_pyenv/
. $PYENV_HOME/bin/activate
pylint -f parseable checkmate/ | tee pylint.out