#!/usr/bin/python

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

def get_pull_requests():
    """
    Parses git fetch origin for any pull request branches.
    """
    pull_requests = bash("git fetch origin")
    return re.findall(r'\s*\*.*origin/pr/(\d+)', pull_requests)

def get_tested_pull_requests(pull_request_file):
    """
    Splits the pull request file's contents into an array

    :param pull_request_file: the file with pull requests to read
    """
    with open(pull_request_file, 'r') as pull_request_file:
        return pull_request_file.read().split('\n')

def test():
    """
    Runs unit tests and linting... this was copied directly from the checkmate jenkins job.

    TODO: check in the checkmate job's scripts instead of keeping them in
        the web console, that way we can reuse the code instead of copying 
        it here.
    """
    bash("bash tools/pip_setup.sh", True)
    bash("bash tools/run_tests.sh", True)
    bash("bash tools/run_pylint.sh", True)

def setup_pull_request_branches():
    TESTED_PULL_REQUEST_PATH = "tools/tested_pull_requests"
    #move to the checkmate workspace root
    bash('''
        cp .git/config .git/config.bak
        git config --add remote.origin.fetch '+refs/pull/*/head:refs/remotes/origin/pr/*'
        ''')
    REMOTE_PULL_REQUESTS = get_pull_requests()
    #print "REMOTE_PULL_REQUESTS " + " ,".join(REMOTE_PULL_REQUESTS)
    TESTED_PULL_REQUESTS = get_tested_pull_requests(TESTED_PULL_REQUEST_PATH)
    #print "TESTED_PULL_REQUESTS %s" % " ,".join(TESTED_PULL_REQUESTS)
    return [pr for pr in REMOTE_PULL_REQUESTS 
                    if pr not in TESTED_PULL_REQUESTS]

def teardown_pull_request_branches():
    bash("mv .git/config.bak .git/config")
