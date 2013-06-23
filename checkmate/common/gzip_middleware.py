'''
    A WSGI middleware application that automatically gzips output
    to the client.
    Before doing any gzipping, it first checks the environ to see if
    the client can even support gzipped output. If not, it immediately
    drops out.
    It automatically modifies the headers to include the proper values
    for the 'Accept-Encoding' and 'Vary' headers.

    Example of use:

        from wsgiref.simple_server import WSGIServer, WSGIRequestHandler

        def test_app(environ, start_response):
            status = '200 OK'
            headers = [('content-type', 'text/html')]
            start_response(status, headers)
            return ['Hello gzipped world!']

        app = Gzipper(test_app, compresslevel=8)
        httpd = WSGIServer(('', 8080), WSGIRequestHandler)
        httpd.set_app(app)
        httpd.serve_forever()


The BSD 3-Clause License
The following is a BSD 3-Clause ("BSD New" or "BSD Simplified") license
template. To generate your own license, change the values of OWNER,
ORGANIZATION and YEAR from their original values as given here, and substitute
your own.

Note: You may omit clause 3 and still be OSD-conformant. Despite its colloquial
name "BSD New", this is not the newest version of the BSD license; it was
followed by the even newer BSD-2-Clause version, sometimes known as the
"Simplified BSD License". On January 9th, 2008 the OSI Board approved
BSD-2-Clause, which is used by FreeBSD and others. It omits the final
"no-endorsement" clause and is thus roughly equivalent to the MIT License.

Historical Background: The original license used on BSD Unix had four clauses.
The advertising clause (the third of four clauses) required you to acknowledge
use of U.C. Berkeley code in your advertising of any product using that code.
It was officially rescinded by the Director of the Office of Technology
Licensing of the University of California on July 22nd, 1999. He states that
clause 3 is "hereby deleted in its entirety." The four clause license has not
been approved by OSI. The license below does not contain the advertising
clause.

This prelude is not part of the license.

<OWNER> = Regents of the University of California
<ORGANIZATION> = University of California, Berkeley
<YEAR> = 1998

In the original BSD license, both occurrences of the phrase "COPYRIGHT
HOLDERS AND CONTRIBUTORS" in the disclaimer read "REGENTS AND CONTRIBUTORS".

Here is the license template:

Copyright (c) <YEAR>, <OWNER>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.
Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.
Neither the name of the <ORGANIZATION> nor the names of its contributors may be
used to endorse or promote products derived from this software without specific
prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
    SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.




Source: https://code.google.com/p/ibkon-wsgi-gzip-middleware/source/browse/
        trunk/gzip_middleware.py
        Modified: ZNS 2013-05-31
'''


from gzip import GzipFile
import cStringIO


__version__ = '1.0.1'


def compress(data, compression_level):
    ''' The `gzip` module didn't provide a way to gzip just a string.
        Had to hack together this. I know, it isn't pretty.
    '''
    _buffer = cStringIO.StringIO()
    gz_file = GzipFile(None, 'wb', compression_level, _buffer)
    gz_file.write(data)
    gz_file.close()
    return _buffer.getvalue()


def parse_encoding_header(header):
    ''' Break up the `HTTP_ACCEPT_ENCODING` header into a dict of
        the form, {'encoding-name':qvalue}.
    '''
    encodings = {'identity': 1.0}
    for encoding in header.split(','):
        if encoding.find(';') > -1:
            encoding, qvalue = encoding.split(';')
            encoding = encoding.strip()
            qvalue = qvalue.split('=', 1)[1]
            if qvalue != '':
                encodings[encoding] = float(qvalue)
            else:
                encodings[encoding] = 1
        else:
            encodings[encoding] = 1
    return encodings


def client_wants_gzip(accept_encoding_header):
    ''' Check to see if the client can accept gzipped output, and whether
        or not it is even the preferred method. If `identity` is higher, then
        no gzipping should occur.
    '''
    encodings = parse_encoding_header(accept_encoding_header)
    if 'gzip' in encodings:
        return encodings['gzip'] >= encodings['identity']
    elif '*' in encodings:
        return encodings['*'] >= encodings['identity']
    else:
        return False


DEFAULT_COMPRESSABLES = set(
    [
        'application/json',
        'application/x-yaml',
        'text/plain',
        'text/javascript',
        'application/x-javascript',
        'text/html',
        'text/css',
        'text/xml',
        'application/xml',
        'application/xml+rss',
    ]
)


class Gzipper(object):
    ''' WSGI middleware to wrap around and gzip all output.
        This automatically adds the content-encoding header.
    '''
    def __init__(self, app, content_types=None, compresslevel=6):
        self.app = app
        if content_types is None:
            self.content_types = DEFAULT_COMPRESSABLES
        else:
            self.content_types = content_types
        self.compresslevel = compresslevel

    def __call__(self, environ, start_response):
        ''' Do the actual work. If the host doesn't support gzip
            as a proper encoding,then simply pass over to the
            next app on the wsgi stack.
        '''
        if not client_wants_gzip(environ.get('HTTP_ACCEPT_ENCODING', '')):
            return self.app(environ, start_response)

        _buffer = {'to_gzip': False, 'body': ''}

        def _write(body):  # pylint: disable=C0111
            # for WSGI compliance
            _buffer['body'] = body

        def _start_response(status, headers, exc_info=None):
            ''' Wrapper around the original `start_response` function.
                The sole purpose being to add the proper headers automatically.
            '''
            for header in headers:
                field = header[0].lower()
                if field == 'content-encoding':
                    # if the content is already encoded, don't compress
                    _buffer['to_gzip'] = False
                    break
                elif field == 'content-type':
                    ctype = header[1].split(';')[0]
                    if ctype in self.content_types and not (
                            'msie' in environ.get('HTTP_USER_AGENT', '')
                            .lower() and
                            'javascript' in ctype):
                        _buffer['to_gzip'] = True

            _buffer['status'] = status
            _buffer['headers'] = headers
            _buffer['exc_info'] = exc_info
            return _write

        data = self.app(environ, _start_response)

        if _buffer['status'].startswith('200 ') and _buffer['to_gzip']:
            data = ''.join(data)
            if len(data) > 200:
                data = compress(data, self.compresslevel)
                headers = _buffer['headers']
                headers.append(('Content-Encoding', 'gzip'))
                # Added by write_x headers.append(('Vary', 'Accept-Encoding'))
                for i, header in enumerate(headers):
                    if header[0] == 'Content-Length':
                        headers[i] = ('Content-Length', str(len(data) +
                                      len(_buffer['body'])))
                        break
            data = [data]

        _writable = start_response(_buffer['status'], _buffer['headers'],
                                   _buffer['exc_info'])

        if _buffer['body']:
            _writable(_buffer['body'])
        return data
