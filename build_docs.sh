#!/bin/bash
#
# Build Checkmate HTML Documentation
#

# Build the checkmate package
python setup.py build

# Generate the automatic docs from the modules
sphinx-apidoc -f -o docs build/lib/checkmate

# Build the full set of docs (API docs and other docs we create manually)
cd docs
make html
cd ..

echo "To view the docs in a browser: open docs/.build/html/index.html"
