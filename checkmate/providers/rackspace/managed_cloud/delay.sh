STOP=$(($(date +%s)+300))
COMPLETE_FILE="/etc/rackspace/checkmate/.complete"
while [ ! -f ${COMPLETE_FILE} && $(date +%s) -lt $STOP ];
do
  sleep 1
done