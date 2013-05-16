A Browser UI for Checkmate
==========================

This is a browser-based graphical user interface for Checkmate. It can be loaded as python WSGI middleware or as a Chrome plug-in.


Enabling it on a Checkmate Server
---------------------------------
To load it as middleware, install the python package and add
rook.middleware.BrowserMiddleware to your WSGI chain. The Checkmate server has
the built-in capability to load the middleware using the '--with-ui'
command-line argument. Once loaded, browsers should be able to hit your
server's root path and will get an HTML response.


The Code
--------
Rook is built using AngularJS (which uses jQuery) and styled using Twitter
Bootstrap.


Rackspace Features
------------------

To enable the Global Auth SSO and Impersonation features, make sure the checkmate server has the right setting for the auth endpoints:

```bash
export CHECKMATE_AUTH_ENDPOINTS='[
  {
    "default": true,
    "middleware": "checkmate.middleware.TokenAuthMiddleware",
    "uri": "https://identity.api.rackspacecloud.com/v2.0/tokens",
    "kwargs": {
      "protocol": "Keystone",
      "realm": "US Cloud",
      "priority": "1"
    }
  },
  {
    "middleware": "checkmate.middleware.TokenAuthMiddleware",
    "uri": "https://lon.identity.api.rackspacecloud.com/v2.0/tokens",
    "kwargs": {
      "protocol": "Keystone",
      "realm": "UK Cloud"
    }
  },
  {
    "middleware": "rook.middleware.RackspaceSSOAuthMiddleware",
    "uri": "https://identity-internal.api.rackspacecloud.com/v2.0/tokens",
    "kwargs": {
      "realm": "Rackspace SSO",
      "protocol": "GlobalAuth"
    }
  },
  {
    "middleware": "rook.middleware.RackspaceImpersonationAuthMiddleware",
    "uri": "https://identity-internal.api.rackspacecloud.com/v2.0/RAX-AUTH/impersonation-tokens",
    "kwargs": {
      "realm": "Rackspace SSO",
      "protocol": "GlobalAuthImpersonation"
    }
  }
]'
```

For Global Auth validation:
- add the service 'username' and 'password' to the GlobalAuth entry kwargs
For Global Auth admin auth-z:
- add the 'admin_role' name to the kwargs


Contributing
------------
Fork it. Make your changes. Push them. And submit a pull request.

Layout:

Trying to keep versioning clean, avoid duplication, and make it predictable to
where to find things.

- All libraries go in /lib.
- Each library gets a folder, unless it consists of one file (a .min extra file
  doesn't count, so jquery, for example, has two files in /lib)
- The folder must contain a version identifier (ex. /lib/bootstrap-2.0.4)
- Put file types in /img, /css. and /js IF it is option. Some libraries
  hard-code those; we don't need to modify that.
- If desired, create an unversioned folder for the latest version of a library
  (ex. /bootstrap containing a copy of /bootstrap-2.0.4). So consumers can link
  to latest and deal with breaking changes, or link to a fixed version.
- Add a readme in a folder if there is something special about it (for example,
  the boostrap download is using the precompiled option available from their
  site which includes all plugins in bootstrap.js)

Exceptions are fine, but document in read me if possible.


TODO
----
There are still dependencies between the two projects to be removed:

1. Rook uses checkmate.utils to register static paths (using the STATIC variable)

2. Rook uses Environments and Providers directly from the checkmate engine.

3. Checkmate loads rook using a hard-coded import.
