#!/usr/bin/python
import re
import subprocess
import sys


def bash(cmd, verbose=True, set_e=True, set_x=False):
    """
    Executes the specified cmd using the bash shell, redirects stderr to
    stdout.

    :param verbose: true if the command's output should be printed to the
                    console
    :param cmd: the command to execute
    raises CalledProcessError - if the run cmd returns a non-zero exit code.

    Inspect CalledProcessError.output or CalledProcessError.returncode for
    information.
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
                                         executable="/bin/bash")
        if verbose:
            print result
        return result
    except subprocess.CalledProcessError as proc_error:
        if verbose:
            print str(proc_error.returncode) + "\n" + proc_error.output
        raise proc_error


def get_github_credentials(filepath):
    with open(filepath, 'r') as cred_file:
        lines = cred_file.read()

        oauth_token = re.search(r'oauth_token\s*=\s*(\S+)\s*', lines).group(1)
        git_repo = re.search(r'git_repo\s*=\s*(\S+)\s*', lines).group(1)
        git_user = re.search(r'git_user\s*=\s*(\S+)\s*', lines).group(1)

        return {
            "oauth_token": oauth_token,
            "git_repo": git_repo,
            "git_user": git_user
        }


def post_pull_request_comment(success, branch, github_creds, url):
    """
    Posts a comment on the pull request specified by the branch, indicating if
    testing passed or failed.

    :param success: True if PASSED False if FAILED
    :param branch: the pull request to comment on
    """
    status_string = "PASS" if success else "FAIL"
    icon = ":+1:" if success else ":-1:"

    return bash(
        (
            'curl -H "Authorization: token %s" -X POST '
            '-d \'{ "body": "%s %s: Tests and basic simulations [%sed](%s)." }\' '
            'https://github.rackspace.com/api/v3/repos/checkmate/checkmate/issues/%s/'
            'comments'
        ) % (
            github_creds['oauth_token'], icon, status_string,
            status_string.lower(), url, branch
        ),
        verbose=False
    )


def main():
    """
    :command line arg 1: SUCCESS or FAILURE
    :command line arg 2: the pull request to comment on
    :command line arg 3: the file to read github auth credentials from
    :command line arg 4: the jenkins URL
    """
    success = sys.argv[1] == 'SUCCESS'
    branch = sys.argv[2]
    github_cred_file = sys.argv[3]
    jenkins_job_url = sys.argv[4]
    github_creds = get_github_credentials(github_cred_file)
    bash("git config core.filemode false")
    post_pull_request_comment(success, branch, github_creds, jenkins_job_url)


if __name__ == '__main__':
    main()
