#!/usr/bin/env python
import os
from subprocess import call
import sys


def main_func():
    if len(sys.argv) > 1 and sys.argv[1] == 'START':
        params = [sys.executable]
        if '--newrelic' in sys.argv:
            sys.argv.pop(sys.argv.index('--newrelic'))
            params = ['NEW_RELIC_CONFIG_FILE=newrelic.ini', 'newrelic-admin',
                    'run-program']
#        params.extend(['celeryd', '--config=checkmate.celeryconfig', '-I',

        params.extend(['-m', 'celery.bin.celeryd',
                       '--config=checkmate.celeryconfig', '-I',
                'checkmate.orchestrator,checkmate.ssh,checkmate.deployments,'
                'checkmate.providers.rackspace,checkmate.providers.opscode,'
                'checkmate.celeryapp',
                '--events', 
                ])
        if '--verbose' in sys.argv:
            sys.argv.pop(sys.argv.index('--verbose'))
            params.extend(['-l', 'debug'])

        # Append extra parameters
        if len(sys.argv) > 2:
            params.extend(sys.argv[2:])

        try:
            print 'Running: %s' % ' '.join(params)
            call(params)
        except KeyboardInterrupt:
            print "\nExiting by keyboard request"
    elif len(sys.argv) > 1 and sys.argv[1] == 'MONITOR':
        params = [sys.executable, '-m', 'celery.bin.celeryev',
                  '--config=checkmate.celeryconfig']
        try:
            print 'Running: %s' % ' '.join(params)
            call(params)
        except KeyboardInterrupt:
            pass
    else:
        print """
        *** (Opinionated) CheckMate Queue Command-line Utility ***

        Starts the CheckMate Celery Queue Listener with some default settings

        Usage:

            checkmate-queue START [options]
            checkmate-queue MONITOR

        Options:

            --newrelic: enable newrelic monitoring (place newrelic.ini in your
                        directory)
            --verbose:  turn up logging to DEBUG (default is INFO)

        Note: any additional parameters supplied will be appended to the
        command line for celery (ex. you can use --autoreload when debugging)


        Settings:
        """
        for key in os.environ:
            if key.startswith('CHECKMATE_') or key.startswith('CELERY'):
                if key.startswith('CHECKMATE_CLIENT'):
                    pass
                else:
                    print key, '=', os.environ[key]

if __name__ == '__main__':
    main_func()
