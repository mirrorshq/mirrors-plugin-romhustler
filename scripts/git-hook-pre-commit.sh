#!/bin/bash

LIBFILES=""
LIBFILES="${LIBFILES} $(find ./romhustler -name '*.py' | tr '\n' ' ')"
ERRFLAG=0

OUTPUT=`pyflakes ${LIBFILES} 2>&1`
if [ -n "$OUTPUT" ] ; then
    echo "pyflake errors:"
    echo "$OUTPUT"
    echo ""
    ERRFLAG=1
fi

OUTPUT=`pycodestyle ${LIBFILES} | grep -Ev "E501|E402"`
if [ -n "$OUTPUT" ] ; then
    echo "pycodestyle errors:"
    echo "$OUTPUT"
    echo ""
    ERRFLAG=1
fi

if [ "${ERRFLAG}" == 1 ] ; then
    exit 1
fi
