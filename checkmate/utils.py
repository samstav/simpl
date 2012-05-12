""" General utility functions

- handling content conversion (yaml/json)
- handling templating (Jinja2)
"""
# pylint: disable=E0611
from bottle import abort
from jinja2 import BaseLoader, TemplateNotFound, Environment
import json
import logging
import os
import sys
import yaml
from yaml.events import AliasEvent, ScalarEvent

LOG = logging.getLogger(__name__)


def import_class(import_str):
    """Returns a class from a string including module and class."""
    mod_str, _sep, class_str = import_str.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ImportError, ValueError, AttributeError), exc:
        LOG.debug('Inner Exception: %s', exc)
        raise


def import_object(import_str, *args, **kw):
    """Returns an object including a module or module and class."""
    try:
        __import__(import_str)
        return sys.modules[import_str]
    except ImportError:
        cls = import_class(import_str)
        return cls(*args, **kw)


def get_template_name_from_path(path):
    """ Returns template name fro request path"""
    parts = path.split('/')
    # IDs are 2nd or 3rd: /[type]/[id]/[type2|action]/[id2]/action
    if len(parts) >= 4:
        name = "%s.%s" % (parts[1][0:-1], parts[3][0:-1])
    elif len(parts) == 2:
        name = "%s" % parts[1]
    elif len(parts) == 3:
        name = "%s" % parts[1][0:-1]  # strip s
    else:
        name = 'default'
    return name


def resolve_yaml_external_refs(document):
    """Parses YAML and resolves any external references"""
    anchors = []
    for event in yaml.parse(document, Loader=yaml.SafeLoader):
        if isinstance(event, AliasEvent):
            if event.anchor not in anchors:
                # Swap out local reference for external reference
                new_ref = u'checkmate-reference://%s' % event.anchor
                event = ScalarEvent(anchor=None, tag=None,
                                    implicit=(True, False), value=new_ref)
        if hasattr(event, 'anchor') and event.anchor:
            anchors.append(event.anchor)

        yield event


def read_body(request):
    """Reads request body, taking into consideration the content-type, and
    return it as a dict"""
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
                         Dumper=yaml.SafeDumper))
    elif content_type == 'application/json':
        return json.load(data)
    elif content_type == 'application/x-www-form-urlencoded':
        obj = request.forms.object
        if obj:
            result = json.loads(obj)
            if result:
                return result
        abort(406, "Unable to parse content. Form POSTs only support objects "
                "in the 'object' field")
    else:
        abort(415, "Unsupported Media Type: %s" % content_type)


def write_body(data, request, response):
    """Write output with format based on accept header. json is default"""
    accept = request.get_header('Accept', ['application/json'])

    # YAML
    if 'application/x-yaml' in accept:
        response.add_header('content-type', 'application/x-yaml')
        return yaml.safe_dump(data, default_flow_style=False)

    # HTML
    if 'text/html' in accept:
        response.add_header('content-type', 'text/html')

        name = get_template_name_from_path(request.path)

        class MyLoader(BaseLoader):
            def __init__(self, path):
                self.path = path

            def get_source(self, environment, template):
                path = os.path.join(self.path, template)
                if not os.path.exists(path):
                    raise TemplateNotFound(template)
                mtime = os.path.getmtime(path)
                with file(path) as f:
                    source = f.read().decode('utf-8')
                return source, path, lambda: mtime == os.path.getmtime(path)
        env = Environment(loader=MyLoader(os.path.join(os.path.dirname(
            __file__), 'static')))
        env.json = json
        try:
            template = env.get_template("%s.template" % name)
            return template.render(data=data, source=json.dumps(data,
                    indent=2))
        except StandardError as exc:
            LOG.error(exc)
            try:
                template = env.get_template("default.template")
                return template.render(data=data, source=json.dumps(data,
                        indent=2))
            except StandardError as exc2:
                LOG.error(exc2)
                pass  # fall back to JSON

    #JSON (default)
    response.set_header('content-type', 'application/json')
    return json.dumps(data, indent=4)
