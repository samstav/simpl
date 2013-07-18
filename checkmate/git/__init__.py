'''
Set up checkmate.git namespace

Allows:

    from checkmate import git
    wsgi_filter = git.Middlware(...)

'''
from .middleware import GitMiddleware as Middleware  # NOQA
