#!/usr/bin/python

from test_functions import *

if len(setup_pull_request_branches()) > 0:
    bash("wget -O - http://cimaster-n01.cloudplatform.rackspace.net:8080/job/checkmate-test-pull-request/build")

teardown_pull_request_branches()