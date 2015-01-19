# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Checkmate module that registers/configures Celery tasks."""
import os
import subprocess
import sys


def main_func():
    "Called automatically when this module is executed."""
    from checkmate import entry_points
    entry_points.preconfigure()
    if len(sys.argv) > 1 and sys.argv[1] == 'START':
        params = []
        if '--newrelic' in sys.argv:
            sys.argv.pop(sys.argv.index('--newrelic'))
            params = ['newrelic-admin', 'run-python']
            if 'NEW_RELIC_CONFIG_FILE' not in os.environ:
                os.environ['NEW_RELIC_CONFIG_FILE'] = 'newrelic.ini'
        params.extend(['celery', 'worker'])

        task_modules = [
            'checkmate.orchestrator',
            'checkmate.ssh',
            'checkmate.rdp',
            'checkmate.deployments',
            'checkmate.workflows',
            'checkmate.providers.core',
            'checkmate.providers.rackspace',
            'checkmate.providers.opscode',
            'checkmate.celeryapp',
            'checkmate.common.tasks',
            'checkmate.deployments.workspaces',
        ]

        params.extend([
            '--config=checkmate.celeryconfig',
            '-I', ','.join(task_modules),
            '--events',
        ])

        if '--verbose' in sys.argv:
            # convert our --verbose into celery's -l debug
            sys.argv.pop(sys.argv.index('--verbose'))
            params.extend(['-l', 'debug'])
        elif '-l' not in sys.argv:
            # Info by default if not overriden (otherwise celery is too quiet)
            params.extend(['-l', 'info'])

        # Append extra parameters
        if len(sys.argv) > 2:
            params.extend(sys.argv[2:])

        try:
            print('Running: %s' % ' '.join(params))
            subprocess.call(params)
        except OSError as exc:
            if params[0] == 'newrelic-admin':
                print ("I got a 'File not found' error trying to run "
                       "newrelic-admin. Make sure the newrelic python agent "
                       "is installed")
            else:
                print(exc)

        except KeyboardInterrupt:
            print("\nExiting by keyboard request")
    elif len(sys.argv) > 1 and sys.argv[1] == 'MONITOR':
        params = [sys.executable, '-m', 'celery.bin.celeryev',
                  '--config=checkmate.celeryconfig']
        try:
            print('Running: %s' % ' '.join(params))
            subprocess.call(params)
        except KeyboardInterrupt:
            pass
    else:
        print("""
        *** (Opinionated) Checkmate Queue Command-line Utility ***

        Starts the Checkmate Celery Queue Listener with some default settings

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
        """)
        for key in os.environ:
            if key.startswith('CHECKMATE_') or key.startswith('CELERY'):
                if key.startswith('CHECKMATE_CLIENT'):
                    pass
                else:
                    print(key, '=', os.environ[key])

if __name__ == '__main__':
    main_func()
