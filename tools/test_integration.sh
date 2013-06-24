#!/bin/bash

# Runs from tox.ini
# test_integration.sh


# just units for now
nosetests tests/unit --with-xcoverage --cover-package=checkmate --cover-tests --xcoverage-file=coverage.xml

# Skipping errors on lint for now
flake8 checkmate tests bin | tee flake8.out || exit 0
pylint -f parseable checkmate tests bin | tee pylint.out || exit 0
pip install -r {toxinidir}/CloudCAFE-requirements.txt
/bin/rm -rf ./CloudCAFE
/usr/bin/git clone https://github.rackspace.com/checkmate/CloudCAFE-Python {envdir}/CloudCAFE
# testing one for now
./CloudCAFE/bin/runner.py checkmate dev.config -m blueprint_validation -M test_wordpress_clouddb_simulation
