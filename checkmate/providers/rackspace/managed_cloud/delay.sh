#!/bin/bash
STOP=$(($(date +%s)+300))
COMPLETE_FILE="/tmp/checkmate-complete"
ME="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/$( basename ${BASH_SOURCE[0]} )"
while [[ ! -f "${COMPLETE_FILE}" && $(date +%s) -lt ${STOP} ]];
do
  sleep 1
done
rm -f ${ME}
