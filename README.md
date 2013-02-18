A Browser UI for Checkmate
==========================

This is a browser-based graphical user interface for Checkmate. It can be
loaded as python WSGI middleware or as a Chrome plug-in.


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

To enable the Global Auth SSO and Impersonation features, make sure the
checkmate server has the right setting for ther aurth endpoints:


export CHECKMATE_AUTH_ENDPOINTS='[{"default": true, "middleware": "checkmate.middleware.TokenAuthMiddleware", "uri": "https://identity.api.rackspacecloud.com/v2.0/tokens", "kwargs": {"protocol": "Keystone", "realm": "US Cloud"}}, {"middleware": "checkmate.middleware.TokenAuthMiddleware", "uri": "https://lon.identity.api.rackspacecloud.com/v2.0/tokens", "kwargs": {"protocol": "Keystone", "realm": "UK Cloud"}}, {"middleware": "rook.middleware.RackspaceSSOAuthMiddleware", "uri": "https://identity-internal.api.rackspacecloud.com/v2.0/tokens", "kwargs": {"realm": "Rackspace SSO", "protocol": "GlobalAuth"}}, {"middleware": "rook.middleware.RackspaceImpersonationAuthMiddleware", "uri": "https://identity-internal.api.rackspacecloud.com/v2.0/RAX-AUTH/impersonation-tokens", "kwargs": {"realm": "Rackspace SSO", "protocol": "GlobalAuthImpersonation"}}]'

For Global Auth validation:
- add the service 'username' and 'password' to the GlobalAuth entry kwargs
For Global Auth admin auth-z:
- add the 'admin_role' name to the kwargs


Contributing
------------
Fork it. Make your changes. Push them. And submit a pull request.

TODO
----
There are still dependencies between the two projects to be removed:

1. Rook uses checkmate.utils to register static paths (using the STATIC
   variable)

2. Rook uses Environments and Providers directly from the checkmate engine.

3. Checkmate loads rook using a hard-coded import.
