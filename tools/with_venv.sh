#!/bin/bash
TOOLS=`dirname $0`
VENV=$TOOLS/../venv-checkmate
source $VENV/bin/activate && $@

