# Verification Guide (Distributed Status)

This guide provides instructions to verify that the 13 platform containers of the Apache BigData SIEM platform are healthy and communicating correctly.

---

## 1) Start the Full Stack

Clone the repository and launch the orchestrator stack using Docker Compose:

```bash
docker compose up -d --build
```

Check the health status of all container nodes:

```bash
docker compose ps
```

All 13 containers should display as `running (healthy)` or `running`.

---

## 2) Verify Hadoop HDFS Distribution

Check the HDFS NameNode Web Console:

- [http://localhost:9870](http://localhost:9870)

Confirm the HDFS DataNode status from the command line (should register 1 live datanode container):

```bash
docker exec -it namenode hdfs dfsadmin -report
```

Look for:

- `Live datanodes (1)`

Verify that the HDFS file path can be written to and read successfully:

```bash
docker exec -it namenode hdfs dfs -mkdir -p /tmp/healthcheck
docker exec -it namenode hdfs dfs -ls /
```

---

## 3) Verify Hive Metastore + Spark Thrift Server

Confirm the Hive Metastore is listening and reachable on the metadata port:

```bash
docker exec -it hive-metastore /opt/hive/bin/hive --service metatool -listFSRoot
```

Execute a test query against the Spark Thrift JDBC server (which maps SparkSQL tables toport `10000` on the `spark-thrift` container):

```bash
docker exec -it spark-thrift /opt/bitnami/spark/bin/beeline -u jdbc:hive2://localhost:10000 -e "SHOW DATABASES;"
```

---

## 4) Verify Kafka Broker + Ingested Topics

List the active Kafka topics inside the KRaft broker:

```bash
docker exec -it kafka-broker kafka-topics.sh --bootstrap-server localhost:9092 --list
```

You should see topics auto-created by the `kafka-producer` container as it streams Zeek and syslog network events:

- `real_network_logs` (Zeek connection logs used for streaming K-Means)
- `web-logs` (Zeek HTTP request logs)
- `dns-logs` (Zeek DNS lookup logs)
- `ssl-logs` (Zeek SSL/TLS handshake logs)
- `ssh-logs` (Zeek SSH session logs)
- `syslogs` (Host log signals)
- `app-logs` (Application level logs)

Consume sample event packets from the Kafka broker:

```bash
docker exec -it kafka-broker kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic real_network_logs --from-beginning --max-messages 5
```

---

## 5) Verify Spark Cluster Distribution

Examine the Spark Master Web Console to monitor jobs, active streaming queries, and worker allocations:

- [http://localhost:8080](http://localhost:8080)

In the Spark Master Web UI, confirm that both Spark Worker replicas (each allocated 2 Cores and 2GB RAM by the compose manifest) are fully registered and healthy.

---

## 6) Run and Verify the Streaming ETL & NDR Engines

The Spark streaming applications are automatically submitted at boot-up by the dedicated **`siem-engine`** container. You can monitor the streaming loops and anomaly scoring metrics by reviewing the container logs:

```bash
# Monitor the PySpark Structured Streaming ETL and NDR K-Means logs
docker logs siem-engine --tail 100 -f
```

After logs have streamed for a few minutes, query the Hive warehouse table `siem.logs_parsed` through the Spark Thrift client to verify database insertion:

```bash
docker exec -it spark-thrift /opt/bitnami/spark/bin/beeline -u jdbc:hive2://localhost:10000 -e "SELECT source_topic, COUNT(*) FROM siem.logs_parsed GROUP BY source_topic;"
```

---

## 7) Failure Isolation Quick Checks

If Kafka is not receiving log event streams:

```bash
# Check the Python Zeek/syslog streamer log output
docker logs kafka-producer --tail 100
```

If the Spark Streaming engine cannot write Parquet files to the HDFS storage layer:

```bash
docker logs siem-engine --tail 100
docker logs spark-master --tail 100
docker logs hive-metastore --tail 100
```

If the HDFS Distributed storage layer is reporting unhealthy states:

```bash
docker logs namenode --tail 100
docker logs datanode --tail 100
```
