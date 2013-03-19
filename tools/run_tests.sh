### Run tests ###

### Configure rvm use for chef tests.
. ~/.rvm/environments/ruby-1.9.3-p125@checkmate

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