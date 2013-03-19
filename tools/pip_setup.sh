### Set up virtual environment ###
PYENV_HOME=$WORKSPACE/../.checkmate_pyenv/

# Create virtualenv and install necessary packages
. $PYENV_HOME/bin/activate

if [ "$CLEAN_DEPS" != "false" ]
then
    pip install -U --force-reinstall -r $WORKSPACE/pip-requirements.txt $WORKSPACE/
else
    pip install -r $WORKSPACE/pip-requirements.txt $WORKSPACE/
fi

# make sure we pull the latest chef recipies
find ./checkmate -type d -name chef-stockton -exec rm -rf {} \; || exit 0