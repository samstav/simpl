#!/usr/bin/python
import re, subprocess, sys

def bash(cmd, verbose=True, set_e=True, set_x=False):
    """
    Executes the specified cmd using the bash shell, redirects stderr to stdout.

    :param verbose: true if the command's output should be printed to the console
    :param cmd: the command to execute
    raises CalledProcessError - if the run cmd returns a non-zero exit code. 
        Inspect CalledProcessError.output or CalledProcessError.returncode for information.
    """
    try:
        script_heading = ""
        if set_e:
            script_heading += "set -e\n"
        if set_x:
            script_heading += "set -x\n"

        result = subprocess.check_output(script_heading + cmd, 
            shell=True, 
            stderr=subprocess.STDOUT,
            executable = "/bin/bash")
        if verbose: 
            print result
        return result
    except subprocess.CalledProcessError as proc_error:
        if verbose:
            print str(proc_error.returncode) + "\n" + proc_error.output  
        raise proc_error

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

        oauth_token = re.search(r'oauth_token\s*=\s*(\S+)\s*', lines).group(1)
        git_repo = re.search(r'git_repo\s*=\s*(\S+)\s*', lines).group(1)
        git_user = re.search(r'git_user\s*=\s*(\S+)\s*', lines).group(1)

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
        branch, status_string, github_creds['git_user'], github_creds['git_repo'], branch),
        verbose=False
    )

def main():
    """
    :command line arg 1: the pull request branch to build
    :command line arg 2: the file to read github auth credentials from
    """
    success = False
    branch = sys.argv[1]
    github_cred_file = sys.argv[2]
    github_creds = get_github_credentials(github_cred_file)
    bash("git config core.filemode false")

    setup_pull_request_branches()
    pr_branch = "pr/%s" % branch
    bash("git checkout %s" % pr_branch)
    try:
        for test in ("tools/pip_setup.sh", "tools/jenkins_tests.sh", "tools/run_pylint.sh"):
            #raise IOError if test file does not exist
            with open(test): pass
            bash("chmod +x %s" % test, set_x=True)
            bash(test, set_x=True)
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
