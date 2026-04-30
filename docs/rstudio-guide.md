# RStudio & Spark Analysis Guide

This guide explains how to use RStudio to analyze data processed by the SIEM stack using Spark.

## Accessing RStudio

Once the Docker stack is running, you can access RStudio via your web browser:

- **URL:** [http://localhost:8787](http://localhost:8787)
- **Username:** `rstudio`
- **Password:** `admin123`

## Initial Setup (One-time)

The first time you log in, you need to prepare the environment for Spark.

### 1. Install R Packages
```R
# Run this in the RStudio Console
install.packages(c("sparklyr", "dplyr", "DBI"))
```

### 2. Install Spark Client Binaries
Even though Spark runs in a separate container, RStudio needs local client binaries to communicate with the master.
```R
library(sparklyr)
spark_install(version = "3.5")
```

### 3. Fix File Permissions (If needed)
If you encounter "Permission denied" or "error in running command", run this:
```R
system("chmod -R +x ~/spark")
```

## Connecting to Spark

To connect to the Spark Master, you must specify the `spark_home` path explicitly to avoid environment resolution issues.

```R
library(sparklyr)
library(dplyr)

# Verify your Spark Home directory if needed: spark_home_dir()

sc <- spark_connect(
  master = "spark://spark-master:7077",
  spark_home = "/home/rstudio/spark/spark-3.5.8-bin-hadoop3"
)
```

## Example Analysis

Once connected, you can query the processed logs in the `siem` database.

### 1. List Available Tables
```R
src_databases(sc)
src_tables(sc)
```

### 2. Read SIEM Logs
```R
# Reference the parsed logs table
logs_tbl <- tbl(sc, "siem.logs_parsed")

# Show the first few rows
logs_tbl %>% head() %>% collect()
```

### 3. Basic Aggregation
```R
# Count events by topic
event_counts <- logs_tbl %>%
  group_by(source_topic) %>%
  tally() %>%
  collect()

print(event_counts)
```

## Troubleshooting

- **Java Not Found:** The RStudio image is pre-configured with JDK 11. Verify with `system("java -version")`.
- **Function Not Implemented:** This usually means your WSL2 kernel is outdated. Run `wsl --update` in PowerShell and restart Docker.
- **Connection Timeout:** Ensure `spark-master` is running and healthy in `docker compose ps`.
