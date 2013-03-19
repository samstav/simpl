#!/usr/bin/python
from test_functions import *

TESTED_PULL_REQUEST_PATH = "tools/tested_pull_requests"

if len(setup_pull_request_branches(TESTED_PULL_REQUEST_PATH)) > 0:
    bash("wget -O - http://cimaster-n01.cloudplatform.rackspace.net:8080/job/checkmate-test-pull-request/build")

teardown_pull_request_branches()