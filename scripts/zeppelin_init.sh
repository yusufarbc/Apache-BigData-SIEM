#!/bin/bash
# zeppelin_init.sh

echo "Starting Zeppelin in background..."
/usr/bin/tini -- bin/zeppelin.sh &

echo "Waiting for Zeppelin API to be ready..."
until curl -s http://localhost:8080/api/version > /dev/null; do
  echo "Zeppelin is still starting..."
  sleep 5
done

echo "Configuring Spark Interpreter..."
# Get ID of spark interpreter
INTERPRETER_ID=$(curl -s http://localhost:8080/api/interpreter/setting | python3 -c "import sys, json; print([i['id'] for i in json.load(sys.stdin)['body'] if i['group'] == 'spark'][0])")

# Update settings
curl -X PUT http://localhost:8080/api/interpreter/setting/$INTERPRETER_ID -d '{
  "name": "spark",
  "group": "spark",
  "properties": {
    "zeppelin.spark.master": { "value": "spark://spark-master:7077" },
    "zeppelin.spark.appName": { "value": "Zeppelin-SIEM" },
    "spark.cores.max": { "value": "2" },
    "spark.executor.memory": { "value": "1g" }
  },
  "dependencies": [],
  "option": {
    "remote": true,
    "isExistingProcess": false
  }
}'

echo "Configuring JDBC Interpreter for Hive..."
# Get ID of jdbc interpreter
JDBC_ID=$(curl -s http://localhost:8080/api/interpreter/setting | python3 -c "import sys, json; print([i['id'] for i in json.load(sys.stdin)['body'] if i['group'] == 'jdbc'][0])")

curl -X PUT http://localhost:8080/api/interpreter/setting/$JDBC_ID -d '{
  "name": "jdbc",
  "group": "jdbc",
  "properties": {
    "default.url": { "value": "jdbc:hive2://spark-master:10000/default" },
    "default.user": { "value": "hive" },
    "default.driver": { "value": "org.apache.hive.jdbc.HiveDriver" }
  },
  "dependencies": [],
  "option": {
    "remote": true,
    "isExistingProcess": false
  }
}'

echo "Zeppelin Configuration Complete."
wait
