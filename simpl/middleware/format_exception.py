# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Exception formatting middleware.

Works with the bottle microframework.

Catches unexpected errors and returns
a preset response to avoid leaking any
sensitive information.
"""

import httplib
import logging
import sys

import bottle
import webob

from simpl import threadlocal
from simpl.utils import http as http_utils

LOG = logging.getLogger(__name__)


# TODO(sam): will need custom simpl exception for UnexpectedError

def error_formatter(exception):
    """Format exception into http error message information.

    The returned dict is expected to become part of an error response body
    which is in the format:
        error:  wrapper and json root element
            code: the http error code (ex. 404)
            message: the http message matching the code (ex. Not Found)
            description: hopefully useful information about the error
    :param exception: any python exception
    :returns: dict where content is:
            code:          - the HTTP error code (ex. 404)
            description:   - the plain english, user-friendly description. Use
                             this to to surface a UI/CLI. non-technical message
    """
    output = {}

    if isinstance(exception, cmexc.CheckmateException):
        output['code'] = 400
        output['description'] = exception.friendly_message
    elif isinstance(exception, AssertionError):
        output['code'] = 400
        output['description'] = str(exception)
        LOG.error(exception)
    elif isinstance(exception, bottle.HTTPError):
        output['code'] = exception.status_code
        output['description'] = exception.message or exception.body
        LOG.error(exception)
    elif exception:
        output['code'] = 500
        output['description'] = cmexc.UNEXPECTED_ERROR

    return output


def bottle_error_formatter(bottle_error):
    """Format error for bottle.

    This is called directly by bottle.

    We return all errors formatted according to requested format. We default to
    json if we don't recognize or support the content.
    :param bottle_error: the bottle.HTTPError passed in by bottle.
    :returns: appropriate wsgi response where content is formatted from this
        dict:
        error:             - this is the wrapper for the returned error object
            code:          - the HTTP error code (ex. 404)
            message:       - the HTTP error code message (ex. Not Found)
            description:   - the plain english, user-friendly description. Use
                             this to to surface a UI/CLI. non-technical message
            reason:        - (optional) any additional technical information to
                             help a technical user help troubleshooting
    """
    output = error_formatter(bottle_error.exception)
    if 'description' not in output:
        if bottle_error.status_code == 404:
            output['description'] = bottle_error.body
        else:
            output['description'] = cmexc.UNEXPECTED_ERROR
    bottle_error.output = output['description']

    if 'code' in output and output['code'] != bottle_error.status_code:
        bottle_error._status_code = output['code']  # pylint: disable=W0212

    accept = bottle.request.get_header("Accept") or ""
    if "application/x-yaml" in accept:
        bottle_error.headers.update({"content-type": "application/x-yaml"})
    else:  # default to JSON
        bottle_error.headers.update({"content-type": "application/json"})

    output['message'] = httplib.responses[bottle_error.status_code]

    bottle_error.apply(bottle.response)
    return http_utils.write_body(
        {'error': output}, bottle.request, bottle.response)


class FormatExceptionMiddleware(object):  # pylint: disable=R0903

    """Format outgoing exceptions.
    Uses and is compatible-with bottle exception formatting.
    - Handle Bottle Exceptions (even when catchall=False).
    - Handle SimplExceptions, SimplHTTPError, etc.
    - Handle other exceptions.
    - Fail-safe to a generic error (UNEXPECTED_ERROR)
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        """Catch exceptions and format them based on config."""
        try:
            return self.app(environ, start_response)
        except bottle.HTTPError as exc:
            LOG.debug("Formatting a bottle exception.",
                      exc_info=exc)
            exc_info = sys.exc_info()
            exc.traceback = exc_info[1]
            start_response(exc.status_line, exc.headerlist)
            return [bottle_error_formatter(exc.exception)]
        except cmexc.CheckmateException as exc:
            LOG.debug("Formatting a Checkmate exception.",
                      exc_info=exc)
            exc_info = sys.exc_info()
            bottle_exc = bottle.HTTPError(
                status=exc.http_status, body=exc.friendly_message,
                exception=exc, traceback=exc_info[2])
            response = bottle_error_formatter(bottle_exc)
            start_response(bottle_exc.status_line, bottle_exc.headerlist)
            return [response]
        except Exception as exc:  # pylint: disable=W0703
            LOG.debug("Formatting a standard, unexpected exception.",
                      exc_info=exc)
            exc_info = sys.exc_info()
            bottle_exc = bottle.HTTPError(
                status=500, body=cmexc.UNEXPECTED_ERROR, exception=exc,
                traceback=exc_info[2])
            response = bottle_error_formatter(bottle_exc)
            # For other errors, log underlying cause
            req = webob.Request(environ)
            errmsg = "%s - %s" % (bottle_exc.status_code, repr(exc))
            context = {
                'request': "%s %s" % (req.method, req.path_url),
                # TODO(sam): the threadlocal object used here should
                # probably be of a specific namespace.
                # Maybe "simpl-middleware"?
                # A .get method for the threadlocal module might be nice
                # .... threadlocal.get('simpl-middleware')
                'user': threadlocal.default().get('username'),
                'query': req.query_string,
            }
            LOG.critical(errmsg, extra=context, exc_info=exc_info)
            start_response(bottle_exc.status_line, bottle_exc.headerlist)
            return [response]
