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
