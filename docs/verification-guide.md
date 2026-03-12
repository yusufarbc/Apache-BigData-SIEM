# Verification Guide (Distributed Status)

## 1) Start the Full Stack

```bash
docker compose up -d --build
```

Check container status:

```bash
docker compose ps
```

## 2) Verify Hadoop HDFS Distribution

Check NameNode UI:

- http://localhost:9870

Confirm DataNode count from CLI (should be 2 live nodes):

```bash
docker exec -it namenode hdfs dfsadmin -report
```

Look for:

- `Live datanodes (2)`

Optionally verify HDFS write/read path:

```bash
docker exec -it namenode hdfs dfs -mkdir -p /tmp/healthcheck
docker exec -it namenode hdfs dfs -ls /
```

## 3) Verify Hive Metastore + HiveServer2

Confirm metastore thrift service:

```bash
docker exec -it hive-metastore /opt/hive/bin/hive --service metatool -listFSRoot
```

Run a Hive SQL test through HiveServer2:

```bash
docker exec -it hive-server2 /opt/hive/bin/beeline -u jdbc:hive2://localhost:10000 -e "SHOW DATABASES;"
```

## 4) Verify Kafka Broker + Topics

List topics:

```bash
docker exec -it kafka-broker kafka-topics.sh --bootstrap-server kafka-broker:9092 --list
```

You should see topics auto-created by flog producers:

- `web-logs`
- `syslogs`
- `app-logs`

Consume sample events:

```bash
docker exec -it kafka-broker kafka-console-consumer.sh --bootstrap-server kafka-broker:9092 --topic web-logs --from-beginning --max-messages 5
```

## 5) Verify Spark Cluster Distribution

Spark Master UI:

- http://localhost:8080

Worker UIs:

- http://localhost:8081
- http://localhost:8082

In Spark Master UI, confirm both workers are registered.

## 6) Run and Verify the ETL Job

Submit ETL job from Spark Master:

```bash
docker exec -it spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
  /opt/bitnami/spark/jobs/etl_process.py
```

After a minute, validate Hive table population:

```bash
docker exec -it hive-server2 /opt/hive/bin/beeline -u jdbc:hive2://localhost:10000 -e "SELECT source_topic, COUNT(*) FROM siem.logs_parsed GROUP BY source_topic;"
```

## 7) Failure Isolation Quick Checks

If Kafka is not receiving logs:

```bash
docker logs flog-web --tail 50
docker logs flog-syslog --tail 50
docker logs flog-app --tail 50
```

If Spark cannot write to Hive:

```bash
docker logs spark-master --tail 100
docker logs hive-metastore --tail 100
```

If HDFS is unhealthy:

```bash
docker logs namenode --tail 100
docker logs datanode-1 --tail 100
docker logs datanode-2 --tail 100
```
