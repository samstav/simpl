#!/usr/bin/python
import re, subprocess
import test_functions as tf

def post_pull_request_comment(status, branch):
    oauth_token = "607ba2c45f86d44f0c53653163b3420b5e728cf0"
    git_repo = "test-checkmate"
    git_user = "andr5956"

    status_string = "PASSED" if status else "FAILED"

    return tf.bash('''
    curl -H "Authorization: token %s" -H "Content-Type: application/json" -X POST -d \\
    '{ \\
        "body": "Pull request:%s %s testing: http://cimaster-n01.cloudplatform.rackspace.net:8080/view/Checkmate/job/checkmate-test-pull-request/$BUILD_NUMBER/" \\
    }' https://github.rackspace.com/api/v3/repos/%s/%s/issues/%s/comments
    ''', oauth_token, branch, status_string, git_user, git_repo, branch)


TESTED_PULL_REQUEST_PATH = "tools/tested_pull_requests"
SUCCESS = True
TESTS_PASSED = []
TESTS_FAILED = []

PULL_REQUESTS = tf.setup_pull_request_branches(TESTED_PULL_REQUEST_PATH)

for branch in PULL_REQUESTS:
    pr_branch = "pr/%s" % branch
    tf.bash("git checkout %s" % pr_branch)

    try:
        tf.test()
        TESTS_PASSED.append(branch)
    except subprocess.CalledProcessError as cpe:
        print cpe.output
        print "Pull Request %s failed!" % branch
        SUCCESS = False
        TESTS_FAILED.append(branch)

    tf.bash("git checkout master")
    
tf.teardown_pull_request_branches()

if len(TESTS_PASSED) + len(TESTS_FAILED) > 0:
    print "#" * 30
    print "Pull Requests PASSED:" + ", ".join(TESTS_PASSED)
    print "Pull Requests FAILED:" + ", ".join(TESTS_FAILED)
    print "#" * 30

    print "Failed branch commit detail:"
    for branch in TESTS_FAILED:
        print "Branch %s:" % branch
        tf.bash("git log master..pr/" + branch)
        tf.bash("git branch -D pr/%s" % branch, False)
        post_pull_request_comment(False, branch)

    for branch in TESTS_PASSED:
        post_pull_request_comment(True, branch)

    with open(TESTED_PULL_REQUEST_PATH, 'a') as tested_pull_request_file:
        tested_pull_request_file.write("\n" + "\n".join(PULL_REQUESTS))

    tf.bash('''
        #commit the tested pull request file
        git commit -a -m 'Jenkins tested the pull request(s): %s'
        git push origin master
        ''' % ", ".join(PULL_REQUESTS))

if not SUCCESS: 
    raise RuntimeError("There was a failure running tests!")
