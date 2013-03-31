# Cloud Cafe & Checkmate
![Checkmate](https://github.rackspace.com/checkmate/rook/raw/master/rook/static/img/checkmate.png)

## Installing Cloud Cafe
In order to run the QE tests for Checkmate, you will need to start with the [install of Cloud Cafe](https://github.rackspace.com/Cloud-QE/CloudCAFE-Python)

## Running the QE Tests
In your Cloud Cafe install (git cloned) dir (i.e. \<workspace\>/CloudCafe-Python/) you should now be able to run:

__bin/runner.py__

With no options will give the help menu

To run the checkmate smoke tests, run:

__bin/runner.py checkmate \<config\> -m smoketest__

where \<config\> is the .config file to run the tests against (i.e. localhost/dev/qa/staging/prod)

## Where to find the QE checkmate configurations
\<workspace\>/CloudCafe-Python/config/checkmate

## Where to find the QE checkmate test cases
\<workspace\>/CloudCafe-Python/lib/testrepo/checkmate

## SPECIAL: Offline Blueprint development testing

Set blueprint_test_path variable set in your localhost.config file

To run tests against blueprints that you (blueprint developer) are actively developing, please run:


__cd \<workspace\>/CloudCafe-Python__

**bin/runner.py checkmate localhost.config -m offline_blueprint_validation**

