#! /usr/bin/env python

from __future__ import print_function

import argparse
import json
import os
import sys


def get_env_dict(file):
    if file == "-":
        env_json = sys.stdin.read()
    else:
        env_json = open(file).read()

    return json.loads(env_json)


def merge_env(env_dict1, env_dict2):
    combined_env = env_dict2.copy()
    combined_env.update(env_dict1)
    return combined_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', nargs='*',
                        help='executable file to exec()')
    parser.add_argument('-f', '--file', dest='input_file',
                        type=str, default='-',
                        help=('path from which to read a json map '
                              'to be used as the process environment. '
                              '"-" will read from stdin and is the default.'))
    args = parser.parse_args()

    env_dict = get_env_dict(args.input_file)

    print("exec()ing {} with {} loaded env vars...".format(args.executable,
                                                           len(env_dict)),
          file=sys.stderr)

    os.execvpe(args.executable[0], args.executable,
               merge_env(os.environ, env_dict))

if __name__ == "__main__":
    main()
