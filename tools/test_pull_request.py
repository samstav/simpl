#!/usr/bin/python
import re, subprocess, sys

def bash(cmd, verbose=True):
    """
    Executes the specified cmd using the bash shell, redirects stderr to stdout.

    :param verbose: true if the command's output should be printed to the console
    :param cmd: the command to execute
    raises CalledProcessError - if the run cmd returns a non-zero exit code. 
        Inspect CalledProcessError.output or CalledProcessError.returncode for information.
    """
    try:
        script_heading = "set -e\n"
        if verbose:
            script_heading = script_heading + "set -x\n"

        result = subprocess.check_output(script_heading + cmd, 
            shell=True, 
            stderr=subprocess.STDOUT,
            executable = "/bin/bash")
        if verbose: 
            print result
        return result
    except subprocess.CalledProcessError as proc_error:
        print str(proc_error.returncode) + "\n" + proc_error.output  
        raise proc_error

def test():
    """
    Runs unit tests and linting... this was copied directly from the checkmate jenkins job.
    """
    bash("bash tools/pip_setup.sh", True)
    bash("bash tools/jenkins_tests.sh", True)
    bash("bash tools/run_pylint.sh", True)

def setup_pull_request_branches():
    """
    Adds the remote pull request refspec, backs up the .git/config, and returns the
    difference between the remote pull requests and the pull requests that we have already
    tested.
    """
    bash('''
        cp .git/config .git/config.bak
        git config --add remote.origin.fetch '+refs/pull/*/head:refs/remotes/origin/pr/*'
        git fetch origin
        ''')

def get_github_credentials(filepath):
    with open(filepath, 'r') as cred_file:
        lines = cred_file.read()
        print "lines:" + lines

        oauth_token = re.findall(r'oauth_token\s*=\s*(.*)', lines)
        git_repo = re.findall(r'git_repo\s*=\s*(.*)', lines)
        git_user = re.findall(r'git_user\s*=\s*(.*)', lines)

        return {
            "oauth_token" : oauth_token,
            "git_repo" : git_repo,
            "git_user" : git_user
        }

def post_pull_request_comment(status, branch, github_creds):
    """
    Posts a comment on the pull request specified by the branch, indicating if testing passed or failed.

    :param status: True if PASSED False if FAILED
    :param branch: the pull request to comment on
    """
    status_string = "PASSED" if status else "FAILED"

    return bash(
    ('curl -H "Authorization: token %s" -X POST '
        '-d \'{ "body": "Pull request:%s %s testing!" }\' '
        'https://github.rackspace.com/api/v3/repos/%s/%s/issues/%s/comments') % (github_creds['oauth_token'], 
        branch, status_string, github_creds['git_user'], github_creds['git_repo'], branch))

def main():
    """
    :command line arg 1: the pull request branch to build
    """
    success = False
    branch = sys.argv[1]
    github_cred_file = sys.argv[2]
    github_creds = get_github_credentials(github_cred_file)

    setup_pull_request_branches()
    pr_branch = "pr/%s" % branch
    bash("git checkout %s" % pr_branch)

    try:
        test()
        success = True
    except subprocess.CalledProcessError as cpe:
        print cpe.output
        print "Pull Request %s failed!" % branch
        success = False

    bash("git checkout master")
    bash("mv .git/config.bak .git/config")

    if success:
        post_pull_request_comment(True, branch, github_creds)
    else:
        print "Failed branch commit detail:"
        print "Branch %s:" % branch
        bash("git log master.." + pr_branch)
        bash("git branch -D " + pr_branch, False)
        post_pull_request_comment(False, branch, github_creds)
        raise RuntimeError("There was a failure running tests!")

if  __name__ =='__main__':main()
