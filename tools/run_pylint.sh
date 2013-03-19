### Run Pylint ###

PYENV_HOME=$WORKSPACE/../.checkmate_pyenv/
. $PYENV_HOME/bin/activate
pylint -f parseable checkmate/ | tee pylint.out