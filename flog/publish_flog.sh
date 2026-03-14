#!/usr/bin/env bash
set -euo pipefail

: "${KAFKA_BOOTSTRAP_SERVERS:=kafka-broker:9092}"
: "${KAFKA_TOPIC:=web-logs}"
: "${LOG_PROFILE:=web}"
: "${BATCH_SIZE:=100}"
: "${LOOP_DELAY:=1}"

build_flog_command() {
  case "$LOG_PROFILE" in
    web)
      echo "flog -f apache_common -n ${BATCH_SIZE}"
      ;;
    syslog)
      echo "flog -f rfc5424 -n ${BATCH_SIZE}"
      ;;
    json)
      echo "flog -f apache_combined -o json -n ${BATCH_SIZE}"
      ;;
    winevent)
      echo "flog -f rfc5424 -n ${BATCH_SIZE}"
      ;;
    *)
      echo "flog -f apache_common -n ${BATCH_SIZE}"
      ;;
  esac
}

FLOG_CMD="$(build_flog_command)"

echo "Starting flog producer for topic '${KAFKA_TOPIC}' with profile '${LOG_PROFILE}'"

while true; do
  if ! eval "$FLOG_CMD" | kcat -P -b "$KAFKA_BOOTSTRAP_SERVERS" -t "$KAFKA_TOPIC"; then
    echo "Kafka publish failed, retrying in 3s..."
    sleep 3
    continue
  fi

  sleep "$LOOP_DELAY"
done
