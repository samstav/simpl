#!/bin/bash

# Runs from tox.ini or jenkins:
# test_integration.sh {envdir} {inidir} pr# {simulation target} creds.file jenkins://url
#
# Example:
# /bin/bash tools/test_integration.sh /code/checkmate/.tox/pr /code/checkmate 909 qa ../gitcreds.txt http://jenkins......com
#
#
envpath=$1
codepath=$2
pr=$3
target=$4
creds=$5
url=$6

echo "--------------------------"
echo "Running $0:"
echo "environment:      $envpath"
echo "code path:        $codepath"
echo "pull request:     $pr"
echo "github creds:     $creds"
echo "jenkins job url:  $url"
echo "simulation env:   $target"

function cleanup
{
    trap
    echo "Cleaning up $pr"
    if [ -d /tmp/$pr/CloudCAFE ]
    then
        rm -rf /tmp/$pr/CloudCAFE
    fi
}

function onexit {
    local exit_status=${1:-$?}
    echo Posting failure message to github
    python $codepath/tools/github_comment.py FAILED $pr $creds $url
    echo Exiting $0 with $exit_status
    cleanup || true
    exit $exit_status
}

function run_tests
{
    trap onexit ERR SIGHUP SIGINT SIGTERM
    echo "Running nosetests with coverage"
    # just units for now
    nosetests tests/unit --with-xcoverage --cover-package=checkmate --cover-tests --xcoverage-file=coverage.xml

    # Skipping errors on lint for now (take out checkmate tests)
    echo "Running flake8 > flake8.out"
    flake8 checkmate > flake8.out || true

    echo "Running pylint > pylint.out"
    pylint -f parseable checkmate > pylint.out || true

    echo "Downloading Cafe to /tmp/$pr"
    mkdir -p /tmp/$pr
    /usr/bin/git clone https://github.rackspace.com/checkmate/CloudCAFE-Python /tmp/$pr/CloudCAFE
    cd /tmp/$pr/CloudCAFE
    export PYTHONPATH=$PYTHONPATH:`pwd`/lib

    # testing one for now
    echo "Running 4 simulations against $target"
    bin/runner.py checkmate $target.config -m blueprint_validation -M test_wordpress_simulation
    bin/runner.py checkmate $target.config -m blueprint_validation -M test_wordpress_clouddb_simulation
    bin/runner.py checkmate $target.config -m blueprint_validation -M test_drupal_simulation
    bin/runner.py checkmate $target.config -m blueprint_validation -M test_php_app_db_simulation
    cd $codepath
    cleanup || true
}

run_tests
# If we got here, we've succeeded
echo Posting success message to github
python $codepath/tools/github_comment.py SUCCESS $pr $creds $url
