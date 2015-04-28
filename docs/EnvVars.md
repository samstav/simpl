# Environment Variables

The following environment variables can be set to configure checkmate:

**BERKSHELF_PATH**: the directory that will be used for Berkshelf's
centralized cookbooks repository.  This directory is effectively a cookbook
cache for any blueprint that uses Berkshelf (has a Berksfile file).  Using
Berkshelf makes a blueprint more fault-tolerant (less reliant on the git hosts
being up).

**CHECKMATE_AUTH_ENDPOINTS**: a json string representation of a list of auth
endpoints to support. The uri and middleware keys are required. Any additional
arguments added in the `kwargs` section will be appended to the HTTP headers.
A sample is:

```
[{
    'middleware': 'checkmate.middleware.TokenAuthMiddleware',
    'default': true,
    'uri': 'https://identity.api.rackspacecloud.com/v2.0/tokens',
    'kwargs': {
            'protocol': 'Keystone',
            'realm': 'US Cloud',
            'priority': '1'
        }
}, {
    'middleware': 'checkmate.middleware.TokenAuthMiddleware',
    'uri': 'https://lon.identity.api.rackspacecloud.com/v2.0/tokens',
    'kwargs': {
            'protocol': 'Keystone',
            'realm': 'UK Cloud'
        }
}]
```

This will produce these headers:

```
> HTTP/1.0 200 OK
> WWW-Authenticate: Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud", priority="1"
> WWW-Authenticate: Keystone uri="https://lon.identity.api.rackspacecloud.com/v2.0/tokens" realm="UK Cloud"
```

Note: to make Checkmate work with iNova use the following to work around the
fact that iNova does not support validating tokens.

```
  {
    "middleware": "checkmate.middleware.TokenAuthMiddleware",
    "uri": "https://inova.dfw.ohthree.com:5000/v2.0/tokens",
    "kwargs": {
      "protocol": "Keystone",
      "realm": "iNova",
      "cache_catalog": true
    }
  }
```
and `export NOVA_INSECURE=True` because the catalog points to IPs instead of DNS
names.


**CHECKMATE_CONNECTION_STRING**: a sql-alchemy or mongodb connection string
pointing to the database store for checkmate. Examples:

    sqlite:////var/checkmate/data/db.sqlite
    mongodb://localhost/checkmate

Note: to connect to mongodb, also install the pymongo client library:

    $ pip install pymongo  # you probably need to sudo this

**CHECKMATE_SIMULATOR_CONNECTION_STRING**: a sql-alchemy or mongodb
connection string pointing to the database store for checkmate simulations.

**CHECKMATE_CACHE_CONNECTION_STRING**: connection string for a shared
cache. Currently only support Redis using URI syntax:

    redis://:secret@redis.example.com:6379/0

**CHECKMATE_DOMAIN**: a default DNS domain to use for resources created.

**CHECKMATE_PUBLIC_KEY**: a public key string to push to all created servers
to allow ssh access to them. If you set this to the contents of your
`~/.ssh/id_rsa.pub` file you will be able to log on to all checkmate-created
servers without having to suply a password.

**CHECKMATE_CHEF_LOCAL_PATH**: checkmate uses chef to configure applications
on servers. Checkmate supports using chef with and without a chef server. When
using it without a chef server, checkmate has a provider called chef-solo
that stores all deployments in a multi-tenant capable and scalable file
structure. This setting points to the directory where this structure should
be hosted.  If not specified, Checkmate will try to default to
/var/local/checkmate/deployments.

**CHECKMATE_CHEF_PATH**: when using checkmate with a server, checkmate needs
to know the path for the chef client deployment. This points to that path. The
knife.rb file should be in there.

**CHECKMATE_CHEF_OMNIBUS_VERSION**: the omnibus version to use by default.
If not specified, 10.12.0-1 is used. This can also be overridden by a constraint
in a deployment.

**CHECKMATE_BROKER_USERNAME**: the username to use to connect to the message
queue

**CHECKMATE_BROKER_PASSWORD**: the password to use to connect to the message
queue.

Note: set this value if you are using the CHECKMATE_BROKER_URL override with a
password. Checkmate will use this to replace your password with ***** in logs.

**CHECKMATE_BROKER_HOST**: the IP address or resolveable name of the message
queue server

**CHECKMATE_BROKER_PORT**: the port to use to connect to the message queue
server

**CHECKMATE_BROKER_URL**: Alternatively, a full url with username and
password can be supplied. This *overrides* the previous four settings.
Checkmate server and queue listener will report out what settings they are using
when they start up.

To use mongodb as a broker instead of rabbitmq, set this value to your
[mongodb endpoint](http://www.mongodb.org/display/DOCS/Connections):

    mongodb://localhost/checkmate

For mongodb, in username and passwords reserved characters like :, /, + and @
must be escaped following RFC 2396.

Note: all CHECKMATE_BROKER_* values are picked by code in the
checkmate.celeryconfig module. If you use an alternate config file, these
variable may be ignored. See **CELERY_CONFIG_MODULE**.

**CHECKMATE_RESULT_BACKEND**: default is 'database'. Checkmate needs to
query task results and status. [tested with 'database' only]. This value is
picked up from checkmate.celeryconfig. If you use an alternate config file,
this variable may be ignored. See **CELERY_CONFIG_MODULE**.

In preliminary testing is the "mongodb" setting:

    CELERY_RESULT_BACKEND = "mongodb"
    CELERY_MONGODB_BACKEND_SETTINGS = {"host": "localhost", "port": 27017, "database": "checkmate", "taskmeta_collection": "celery_task_meta"}

**CHECKMATE_RESULT_DBURI**: defaults to 'sqlite://../data/celerydb.sqlite'
under the checkmate directory. Use this to set an alternate location for the
celery result store. This value is picked up from checkmate.celeryconfig. If you
use an alternate config file, this variable may be ignored. See
**CELERY_CONFIG_MODULE**.

**CHECKMATE_OVERRIDE_URL**: If provided, will be used to override the base
url that would normally be built using HTTP_HOST or SERVER_NAME. This can be
used to 'hide' an internal URL.

**CELERY_CONFIG_MODULE**: use checkmate.celeryconfig by default. See celery
instructions for more detail. THis module also picks up the values from some of
the other environment variables. If you use a different config module, the other
checkmate variables may get ignored.

**CELERY_ALWAYS_EAGER**: forces celery to run synchronously, in-process
instead of using the message queue. May be useful for debugging, development,
and troubleshooting.

Deprecated: not used anymore

CELERYD_FORCE_EXECV (as of celery 3.x)

CHECKMATE_DATA_PATH

CHECKMATE_PRIVATE_KEY

CHECKMATE_CHEF_REPO

CHECKMATE_CHEF_USE_DATA_BAGS
