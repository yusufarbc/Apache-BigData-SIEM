from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName('query-test') \
    .config('spark.sql.catalogImplementation', 'hive') \
    .config('spark.hadoop.fs.defaultFS', 'hdfs://namenode:8020') \
    .config('spark.hadoop.hive.metastore.uris', 'thrift://hive-metastore:9083') \
    .enableHiveSupport() \
    .getOrCreate()

print("--- SHOW TABLES ---")
spark.sql('SHOW TABLES IN siem').show(truncate=False)

print("--- QUERY RESULTS ---")
spark.sql('SELECT * FROM siem.logs_parsed LIMIT 5').show(truncate=False)

print("SUCCESS")
