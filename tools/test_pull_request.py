#!/usr/bin/python
import re, subprocess
from test_functions import *

TESTED_PULL_REQUEST_PATH = "tools/tested_pull_requests"
SUCCESS = True
TESTS_PASSED = []
TESTS_FAILED = []

PULL_REQUESTS = setup_pull_request_branches(TESTED_PULL_REQUEST_PATH)

for branch in PULL_REQUESTS:
    pr_branch = "pr/%s" % branch
    bash("git checkout %s" % pr_branch)

    try:
        test()
        TESTS_PASSED.append(branch)
    except subprocess.CalledProcessError as cpe:
        print cpe.output
        print "Pull Request %s failed!" % branch
        SUCCESS = False
        TESTS_FAILED.append(branch)

    bash("git checkout master")
    
teardown_pull_request_branches()

if len(TESTS_PASSED) + len(TESTS_FAILED) > 0:
    print "#" * 30
    print "Pull Requests PASSED:" + ", ".join(TESTS_PASSED)
    print "Pull Requests FAILED:" + ", ".join(TESTS_FAILED)
    print "#" * 30

    print "Failed branch commit detail:"
    for branch in TESTS_FAILED:
        print "Branch %s:" % branch
        bash("git log master..pr/" + branch)
        bash("git branch -D pr/%s" % branch, False)

    with open(TESTED_PULL_REQUEST_PATH, 'a') as tested_pull_request_file:
        tested_pull_request_file.write("\n" + "\n".join(PULL_REQUESTS))

    bash('''
        #commit the tested pull request file
        git commit -a -m 'Jenkins tested the pull request(s): %s'
        git push origin master
        ''' % ", ".join(PULL_REQUESTS))

if not SUCCESS: 
    raise RuntimeError("There was a failure running tests!")
