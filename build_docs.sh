#!/bin/bash
#
# Build Checkmate HTML Documentation
#

python setup.py build
sphinx-apidoc -F -o docs build/lib/checkmate
cd docs
make html
cd ..

