## Usage

To start the checkmate REST API server:

```
$ bin/checkmate-server START [options] [address[:port]]

Options:
-h, --help            show this help message and exit
--logconfig LOGCONFIG Optional logging configuration file
-d, --debug           turn on additional debugging inspection and output
                      including full HTTP requests and responses. Log output
                      includes source file path and line numbers.
-v, --verbose         turn up logging to DEBUG (default is INFO)
-q, --quiet           turn down logging to WARN (default is INFO)
--newrelic            enable newrelic monitoring (place newrelic.ini in your
                      directory
--statsd server:port  enable statsd logging to specified ip:port
-t, --trace-calls     display call hierarchy and errors to stdout
-u, --with-ui         enable support for browsers and HTML templates
-s, --with-simulator  enable support for the deployment simulator
-a, --with-admin      enable /admin calls (authorized to admin users only)
-e, --eventlet        use the eventlet server (recommended in production)
--backdoor-port       port to use for eventlet backdoor to listen on
--access-log FILE     file to log HTTP calls to (only works with --eventlet)
--eager               all celery (queue) tasks will be executed in-process.
                      Use this for debugging only. There is no need to start
                      a queue instance when running eager.
--worker              start the celery worker in-process as well
--webhook             Enable blueprints GitHub webhook responder
-g, --github-api GITHUB_API
                      Root github API uri for the repository containing
                      blueprints. ex: https://api.github.com/v3
-o ORGANIZATION, --organization ORGANIZATION
                      The github organization owning the blueprint
                      repositories
-r REF, --ref REF     Branch/tag/reference denoting the version of blueprints
                      to use.
--cache-dir CACHE_DIR
                      cache directory
--preview-ref PREVIEW_REF
                      version of deployment templates for preview
--preview-tenants PREVIEW_TENANTS
                      preview tenant IDs
--group-refs GROUP_REFS
                      Auth Groups and refs to associate with them as a
                      comma-delimited list. Ex. --group-refs
                      tester=master,prod=stable
```

Once up, you can issue curl commands (or point your browser at it if you
  started the server --with-ui) to use checkmate.

To execute deployments, checkmate uses a message queue. You need to have celery
running with the checkmate tasks loaded. You can run it in the server process
using `--worker` as mentioned above or run it separately:

  $ bin/checkmate-queue START

## Authentication

Checkmate supports multiple authentication protocols and endpoints
simultaneously.

### Authenticating through a Browser

By default, two authentication domains are enabled. In a browser, if you are prompted for credentials, enter the following:

- To log in to a Rackspace US Cloud Account: use US\username and password.

- To log in to a Rackspace UK Cloud Account: use UK\username and password.

### Authenticating using REST HTTP calls

Checkmate supports standard Rackspace\OpenStack authentication with a token. Get a token from your auth endpoint (US or UK) and provide it in the X-Auth-Header:

curl -H "X-Auth-Token: ccdcd4f9-d72d-5677-8b1a-f329389cc539" http://localhost:8080/4500/deployments -v

Checkmate will try the US and then UK endpoints.

To avoid hitting the US for each UK call, and to be a good citizen, tell Checkmate which endpoint your token came from using the X-Auth-Source header:

curl -H "X-Auth-Source: https://lon.identity.api.rackspacecloud.com/v2.0/tokens" -H "X-Auth-Token: ccdcd4f9-d72d-5677-8b1a-f329389cc539" http://localhost:8080/1000002 -v

Note: This is a Checkmate extension to the auth mechanism. This won't work on any other services in OpenStack or the Rackspace Cloud.

## Tools

### Monitoring

To monitor running tasks and events in celery run `celery events`. This requires starting celeryd using -E or --events, which Checkmate does automatically for you:

celeryd -l debug --config=checkmate.celeryconfig -I checkmate.orchestrator,checkmate.ssh,checkmate.providers.rackspace,checkmate.providers.opscode --events

And then use celery events from the checkmate directory to watch events and tasks:

celey events --config=checkmate.celeryconfig

### Tuning

The following has been tested to run up to 10 simultaneous workflows using amqp::

checkmate-queue START --autoscale=10,2
