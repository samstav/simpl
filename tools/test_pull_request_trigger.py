#!/usr/bin/python

from test_pull_request import bash, setup_pull_request_branches, teardown_pull_request_branches

if len(setup_pull_request_branches()) > 0:
    bash("wget -O - http://cimaster-n01.cloudplatform.rackspace.net:8080/job/checkmate-test-pull-request/build")

teardown_pull_request_branches()