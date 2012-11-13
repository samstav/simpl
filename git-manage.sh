#!/bin/bash
#=============================================
#
# FILE: git-manage.sh
#
# USAGE: git-manage.sh
#
# DESCRIPTION: Git-version managing for python projects. Tag current git branch, 
#              increment project version number, add and commit project, then push.
#
#=============================================

#MUST BE RUN AS . ./git-manage.sh to pass NEW_VERSION back to parent process
SRC_DIR=$PWD

if [ ! -d "$SRC_DIR/.git" ]; then
	echo "No git repo identified. Exiting"
	exit 1
fi

if [ ! -f "$SRC_DIR/setup.py" ]; then
	echo "No setup file found. Exiting"
	exit 1
fi

#Pull version number from setup.py
VERSION=`grep 'version=' $SRC_DIR/setup.py | awk -F\' '{print $2}'`

#Pull current tags
TAGS=`git tag`

for tag in ${TAGS}
do
	if [ "${tag}" = "${VERSION}" ]; then
		echo "Version has already been tagged and commited. Exiting."
		exit 0 #Counts as a successfull exit
	fi
done

git tag ${VERSION}

LAST_CHAR=${VERSION#${VERSION%?}} 
export NEW_VERSION=`echo $VERSION | sed 's/[0-9]$/'"$((LAST_CHAR+1))"'/'` #increments version (0.1 -> 0.2)
sed -i -e "s/\(version=\).*/\1\'${NEW_VERSION}\',/" $SRC_DIR/setup.py #writes new version back into setup.py

if [ -f "$SRC_DIR/setup.py-e" ]; then
	rm -rf $SRC_DIR/setup.py-e
fi

git add .
git commit -a -m "${NEW_VERSION}"

#If destination repo isn't specified, assume we're pushing back to origin
if [ -z "${DEST_REPO}" ]; then
	git push origin master
else
	git push $DEST_REPO
fi
