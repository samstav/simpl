#!/usr/bin/python
import os, re, subprocess

def bash(cmd, verbose=True):
    result = subprocess.check_output("#!/bin/bash\nset -e\n" + cmd, shell=True, stderr=subprocess.STDOUT)
    if verbose: print result
    return result

def getPullRequests(pull_requests):
    return re.findall(r'\s*\*.*origin/pr/(\d+)', pull_requests)

def getTestedPullRequests(pull_request_file):
    return open(pull_request_file, 'r').read().split('\n')

def notifyTestFailure(branch):
    print "Pull Request %s failed!" % branch

#todo: use the managed script plugin or something... this is ugly
#remove WORKSPACE local stuff
def test():
	return bash('''
        PYENV_HOME=$WORKSPACE/../.checkmate_pyenv/
        . $PYENV_HOME/bin/activate

        if [ "$CLEAN_DEPS" != "false" ]
        then
        pip install -U --force-reinstall -r $WORKSPACE/pip-requirements.txt $WORKSPACE/
        else
        pip install -r $WORKSPACE/pip-requirements.txt $WORKSPACE/
        fi

        find ./checkmate -type d -name chef-stockton -exec rm -rf {} \; || exit 0

        . ~/.rvm/environments/ruby-1.9.3-p125@checkmate
        if [ -d /tmp/checkmate/test ]; then
        rm -rf /tmp/checkmate/test
        fi
        . $PYENV_HOME/bin/activate
        export CHECKMATE_CHEF_REPO=$WORKSPACE/chef-stockton

        if [ -e $CHECKMATE_CHEF_REPO ]
        then
        cd $CHECKMATE_CHEF_REPO
        git pull origin master
        cd -
        else
        git clone -b master git://github.rackspace.com/checkmate/chef-stockton.git $CHECKMATE_CHEF_REPO
        fi

        nosetests --with-coverage --cover-package=checkmate --with-xunit -w tests/
        coverage xml --include="checkmate/**"
        . $PYENV_HOME/bin/activate
        pylint -f parseable checkmate/ | tee pylint.out
        ''')

tested_pull_request_path = "../tested_pull_requests"
success = True
tests_passed = []
tests_failed = []

bash('''
    cp .git/config .git/config.bak
    git config --add remote.origin.fetch '+refs/pull/*/head:refs/remotes/origin/pr/*'
    ''')

remote_pull_requests = getPullRequests(bash("git fetch origin"))
print "remote_pull_requests " + " ,".join(remote_pull_requests)

tested_pull_requests = getTestedPullRequests(tested_pull_request_path)
print "tested_pull_requests %s" % " ,".join(tested_pull_requests)

test_pull_requests = [pr for pr in remote_pull_requests if pr not in tested_pull_requests]
for branch in test_pull_requests:
    pr_branch = "pr/%s" % branch
    bash("git checkout %s" % pr_branch)

    try:
        test()
        tests_passed.append(branch)
    except subprocess.CalledProcessError as cpe:
        print cpe.output
        notifyTestFailure(branch) 
        success=False
        tests_failed.append(branch)

    bash("git checkout master")
    bash("git branch -d %s" % pr_branch)

print "Pull Requests PASSED:" + ", ".join(tests_passed)
print "Pull Requests FAILED:" + ", ".join(tests_failed)

with open(tested_pull_request_path, 'a') as tested_pull_request_file:
    tested_pull_request_file.write("\n".join(test_pull_requests))

bash("mv .git/config.bak .git/config")
if not success: raise RuntimeError("There was a failure running tests!")
