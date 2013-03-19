#!/usr/bin/python
import test_functions

TESTED_PULL_REQUEST_PATH = "tools/tested_pull_requests"

if len(test_functions.setup_pull_request_branches(TESTED_PULL_REQUEST_PATH)) > 0:
    test_functions.bash("wget -O - http://cimaster-n01.cloudplatform.rackspace.net:8080/job/checkmate-test-pull-request/build")

teardown_pull_request_branches()
