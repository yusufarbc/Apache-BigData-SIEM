# 🚀 In-Depth Analysis of Apache Spark (v3.5.x) Architecture and Engineering for Enterprise SIEM Pipelines

Modern Security Operations Centers (SOCs) ingest millions of Events Per Second (EPS) from diverse sources, including Network Traffic Analysis (NTA) probes, Endpoint Detection and Response (EDR/XDR) agents, cloud audit trails, and physical firewall logs. Correlating these massive datasets in real time for anomaly detection, executing historical threat hunting queries over historical tables, and performing low-latency streaming joins against threat intelligence blacklists easily exceeds the capabilities of traditional relational databases.

To address these challenges, **Apache Spark (v3.5.x)** serves as a core big data processing engine. By leveraging in-memory computation, the optimized Catalyst query engine, off-heap binary memory management (Tungsten), and resilient stateful streaming models, Spark enables SOC architects to design high-throughput, fault-tolerant analytics pipelines.

This report presents a systems-level analysis of Spark 3.5.x optimized for cybersecurity workloads, detailing core execution mechanics, streaming integration with Apache Kafka, memory management parameters, and deployment strategies.

---

## 🏛️ 1. Core Architecture: Tungsten and Catalyst Optimizer

Spark’s performance advantages are achieved by bypassing JVM memory constraints and compiling high-level SQL queries into optimized physical execution plans.

```
       DataFrame API / SQL Query
                   │
                   ▼
     ┌───────────────────────────┐
     │    Catalyst Optimizer     │  (Logical Planning, Pushdowns, CBO, AQE)
     └───────────────────────────┘
                   │
                   ▼
     ┌───────────────────────────┐
     │ Tungsten Execution Engine │  (Off-Heap Memory, UnsafeRow Format)
     └───────────────────────────┘
```

### The Project Tungsten Execution Engine
Applications running on the Java Virtual Machine (JVM) face memory overhead and performance degradation caused by Java Object headers and Garbage Collection (GC) pauses.

In a high-EPS environment, parsing millions of strings (such as IP addresses or log payloads) creates millions of short-lived Java objects. In the JVM, a standard Java string containing only a 4-character value (e.g., `"data"`) introduces significant overhead:
* **Object Header:** 12 bytes
* **Hash Code:** 8 bytes
* **Character Array Referencing:** Variable space

This causes a simple string to consume at least 24 bytes of JVM Heap memory, rapidly filling the *Young Generation* heap partition. When these objects migrate to the *Survivor* and *Old Generation* spaces, they trigger system-wide "Stop-the-World" Garbage Collection cycles, interrupting log ingestion and query flows.

Project Tungsten bypasses these bottlenecks using the `sun.misc.Unsafe` API, enabling direct, low-level memory allocation in the operating system virtual memory space. When off-heap memory is enabled:

```ini
spark.memory.offHeap.enabled true
spark.memory.offHeap.size 8g
```

Spark bypasses JVM GC entirely for execution data structures. Instead of storing logs as Java objects, Tungsten encodes rows as **`UnsafeRow`** structures: contiguous, byte-aligned binary formats.

```
┌───────────────────────┬───────────────────────────────┬───────────────────────────────┐
│ Null Bit Set Bitmap   │ Fixed-Length Fields (8-Bytes) │ Variable-Length Value Payload │
│ (Tracks NULL fields)  │ (Inline Ints, Longs, Offsets) │ (String / Binary data)        │
└───────────────────────┴───────────────────────────────┴───────────────────────────────┘
```

The `UnsafeRow` structure is divided into three segments:
1. **Null Bit Set Bitmap:** Allocates 1 bit per column to track null values. Spark performs bitwise masking to check for null values in nanoseconds, avoiding object-level evaluation overhead.
2. **Fixed-Length Field Region:** Allocates an 8-byte word per column. Fixed-width values (e.g., Port numbers as Integers, timestamps as Longs) are written inline.
3. **Variable-Length Field Region:** Stores dynamic payloads (e.g., `User-Agent` strings, raw payloads). The corresponding 8-byte slot in the fixed-length region acts as a pointer containing both the byte offset and length of the variable data. The offset and length are resolved using fast shift operations:
   
   $$\text{Offset} = (\text{int}) (\text{offsetAndSize} \gg 32)$$
   
   $$\text{Size} = (\text{int}) \text{offsetAndSize}$$

This binary representation allows comparison and hashing operations to run directly on raw bytes without deserializing them back into Java objects.

Off-heap allocations are managed by the `TaskMemoryManager` using a page table registry. When a processing task completes or encounters a failure, the manager invokes `cleanUpAllAllocatedMemory()`, releasing pages and avoiding memory leaks during long-running streaming runs.

### The Catalyst Query Optimizer
While Tungsten optimizes raw bytes on hardware, the **Catalyst Optimizer** refines declarative queries into highly efficient physical execution trees using a four-step pipeline:

```
[ Unresolved Logical Plan ] ──(Analysis via Metastore)──► [ Resolved Logical Plan ]
                                                                   │
                                                      (Logical Optimization)
                                                                   ▼
[ Physical Execution RDDs ] ◄──(Whole-Stage CodeGen)◄── [ Optimized Physical Plan ]
```

1. **Analysis:** Resolves table and column names against the Hive Metastore, validating data types and generating a *Resolved Logical Plan*.
2. **Logical Optimization:** Applies rule-based transformations:
   * *Predicate Pushdown:* Pushes filtering criteria down to the storage layers (e.g., Parquet or Delta files), loading only the records that match query parameters.
   * *Column Pruning:* Budgets resources by reading only requested columns, skipping unused fields.
3. **Physical Planning & CBO:** Generates multiple candidate physical execution plans. Enabling the **Cost-Based Optimizer (CBO)** allows Spark to analyze metastore statistics (e.g., row counts, unique values, and histogram distributions) to select the lowest-cost physical plan (minimizing network and disk shuffle overhead):
   ```ini
   spark.sql.cbo.enabled true
   ```
4. **Code Generation:** Converts the chosen physical plan into highly optimized Java bytecode using *Whole-Stage Code Generation*, collapsing multiple query operations into a single execution loop.

| Optimization Phase | Operating Principle | Operational Advantage |
| :--- | :--- | :--- |
| **Logical Optimization** | Rule-Based (Predicate Pushdown, Column Pruning). | Skips irrelevant blocks at the storage level, reducing physical disk I/O. |
| **Physical Planning (CBO)** | Cost-Based (Analyzes tables sizes and histograms). | Selects optimal join strategies (e.g., Broadcast vs. SortMerge) based on data size. |
| **AQE (Runtime Optimization)** | Adaptive Query Execution (AQE) based on runtime partition states. | Detects skewed partitions and dynamically adjusts query steps during active runs. |

### Adaptive Query Execution (AQE)
Spark 3.5.x relies heavily on **Adaptive Query Execution (AQE)**. Static optimization plans can become inefficient if data skew or inaccurate statistics occur during execution.

AQE resolves this by evaluating physical metrics at shuffle boundaries:
* **Dynamically Coalescing Post-Shuffle Partitions:** Merges small partitions to minimize scheduler overhead.
* **Dynamically Switching Join Strategies:** Converts a high-cost `SortMergeJoin` to a lightweight `BroadcastHashJoin` if runtime filtering reduces a table's size below broadcast thresholds.
* **Handling Skewed Joins:** If specific keys capture a massive volume of records (e.g., botnet telemetry saturating a single IP), AQE splits the skewed partitions into smaller sub-partitions, distributing the workload evenly across executors to prevent Out of Memory (OOM) failures.

---

## 🔄 2. Fault Tolerance: DAGs and Resilient Lineage

SIEM systems cannot afford to lose state due to hardware outages, virtual machine terminations, or executor crashes. Spark handles fault tolerance in-memory using **Directed Acyclic Graphs (DAG)** and **Lineage** tracking.

```
 Raw Data Sources ──► [ RDD_1 ] ──(Narrow Map)──► [ RDD_2 ] ──(Narrow Filter)──► [ RDD_3 ]
                                                                                     │
                                                                                 (Shuffle)
                                                                                     ▼
                                                                                 [ RDD_4 ]
```

### Lazy Evaluation and DAG Building
Data structures in Spark (DataFrames, Dataset APIs) are modeled as Resilient Distributed Datasets (RDDs). Spark separates operations into:
* **Transformations (Lazy):** Functions like `map`, `filter`, `join`, and `groupBy`. These are not executed immediately; instead, they add a logical step to a **Directed Acyclic Graph (DAG)**.
* **Actions (Eager):** Statements like `count`, `collect`, or `writeStream` that trigger the execution of the recorded DAG.

When an action is invoked, the `DAGScheduler` evaluates the logical graph and divides it into executable **Stages**.
* **Narrow Dependencies:** Operations where each partition of the parent RDD is used by at most one partition of the child RDD (e.g., `map`, `filter`). These run in parallel within the same execution stage.
* **Wide Dependencies:** Operations requiring data partitions to be distributed across different physical nodes (e.g., `groupByKey`, `join`). These spark a **Shuffle** boundaries and initiate new execution stages.

### Deterministic Lineage Recovery
If a node hosting active data partitions crashes mid-query, Spark does not restart the entire pipeline. Instead, it consults the RDD's **Lineage**—a deterministic execution map detailing the exact steps required to reconstruct the missing partition from the raw source.

If the lost partition falls within a *Narrow Dependency* stage, Spark schedules the task on a healthy executor. The new task reads only the target partition's raw source bytes and applies the map and filter steps in-memory.

For *Wide Dependency* stages, recomputing long lineage paths can be expensive. Spark minimizes this cost by persisting intermediate shuffle outputs to disk. To terminate lineage chain growth on complex pipelines, engineers can configure **Checkpointing**, which commits RDD states to a durable storage layer (such as HDFS or Amazon S3):

```scala
sparkContext.setCheckpointDir("hdfs:///tmp/spark-checkpoints")
rdd.checkpoint()
```

This checkpoint truncates the lineage chain, allowing recovering executors to pull data directly from the checkpoint file.

---

## 📡 3. Spark Structured Streaming and Kafka Integration

In real-world SOC environments, network telemetry arrives out of order due to network disruptions or mobile endpoints dumping cached logs after reconnecting. Spark Structured Streaming paired with Apache Kafka manages these out-of-order data streams.

```
 [ Kafka Log Ingestion ] ──► [ Spark Stream Ingestion ] ──► [ Event-Time Windows ]
                                                                   │
                                                           (Watermark Filter)
                                                                   ▼
                                                             Commit / Drop
```

### Micro-Batching vs. Continuous Processing
Spark Structured Streaming supports two primary execution modes:

* **Continuous Processing Mode:** Processes events individually, delivering sub-millisecond end-to-end latencies. However, it only guarantees *at-least-once* delivery and does not support complex stateful aggregations. In SIEM systems, duplicate processing can trigger false positive alarms.
* **Micro-Batch Mode (Default):** Collects incoming stream events within short temporal windows (e.g., 100 ms) and processes each batch using vectorization optimizations, delivering high-throughput and guaranteeing **exactly-once** processing.

For high-volume log ingestion, Micro-Batching is the recommended deployment mode.

### Event-Time Processing and Watermarking
To evaluate logs based on when the security event physically occurred rather than when it arrived at the cluster, Spark uses **Event-Time** tracking.

Stateful aggregations (e.g., tracking failed login attempts within 5-minute sliding windows) require Spark to preserve previous state values in memory. To prevent this state metadata from growing indefinitely and triggering OOM crashes, Spark uses **Watermarking** to define when old state records can be safely evicted:

```scala
val stream = df.withWatermark("eventTime", "15 minutes")
  .groupBy(window($"eventTime", "5 minutes"), $"user")
  .count()
```

The watermark dynamically calculates the cutoff boundary:

$$\text{Global Watermark} = \max(\text{EventTime}) - \text{Watermark Threshold}$$

If the system processes a log where `eventTime < Global Watermark`, the event is discarded as too late, protecting memory from being saturated by historical anomalies.

In multi-stream joins, Spark's watermark policy defaults to the slowest stream (`min` policy) to prevent premature state evictions. For aggressive memory reclamation, the policy can be changed to use the newest stream (`max` policy):

```ini
spark.sql.streaming.multipleWatermarkPolicy max
```

### RocksDB State Store and Exactly-Once Guarantees
Spark Structured Streaming delivers exactly-once processing guarantees by combining replayable sources (like Kafka offsets) with idempotent sinks.

```
 [ Kafka Source ] ──► [ Ingestion (Offsets Logged in WAL) ] ──► [ RocksDB State Store ]
                                                                       │
                                                               (Changelog Sync)
                                                                       ▼
                                                             [ Checkpoint Sink ]
```

During execution, Spark tracks offset targets within its checkpoint directory. The checkpoint folder manages two critical registries:
* **`offsets` (Write-Ahead Log):** Records the specific offset targets Spark intends to process in the active micro-batch.
* **`commits`:** Records completed micro-batches.

If a crash occurs, Spark references these logs: if an offset is present in the `offsets` directory but missing from the `commits` log, the engine pulls the specific offsets from Kafka again and replays the micro-batch, ensuring no logs are missed or duplicated.

To manage massive stateful joins, Spark 3.5.x integrates the **RocksDB State Store**, which stores active state data on local NVMe drives rather than in the JVM Heap.

To optimize state backup times, Spark 3.5.x leverages **RocksDB Changelog Checkpointing**. Instead of copying the entire database state to remote storage at the end of each micro-batch, it writes only the delta log changes, dramatically reducing network I/O overhead:

```ini
spark.sql.streaming.stateStore.rocksdb.changelogCheckpointing.enabled true
spark.sql.streaming.asyncProgressTrackingEnabled true
```

---

## 💾 4. Memory Management and Shuffle Tuning

Executing complex joins over billions of rows requires careful memory tuning to prevent shuffle disk spills and executor crashes.

```
 ┌────────────────────────────────────────────────────────┐
 │                   Executor JVM Heap                    │
 │ ┌────────────────────────────────────────────────────┐ │
 │ │                spark.memory.fraction               │ │
 │ │ ┌──────────────────────────┬─────────────────────┐ │ │
 │ │ │     Execution Memory     │   Storage Memory    │ │ │
 │ │ │ (Active Joins & Shuffles)│ (Cached DataFrames) │ │ │
 │ │ └──────────────────────────┴─────────────────────┘ │ │
 │ └────────────────────────────────────────────────────┘ │
 └────────────────────────────────────────────────────────┘
```

### Unified Memory Management Structure
Spark manages executor memory allocations within a single unified space:
* **System Memory:** 300 MB reserved for internal engine processes.
* **Spark Memory Pool (`spark.memory.fraction`, Default: 0.6):** The primary memory pool used for execution and storage.
* **User Memory:** The remaining space (typically 40%) allocated for user-defined variables and JVM class files.

The Spark Memory Pool is dynamically shared between two areas:
* **Execution Memory:** Used for shuffles, joins, and aggregations.
* **Storage Memory (`spark.memory.storageFraction`, Default: 0.5):** Used for caching datasets (`cache()`, `persist()`).

This boundary is elastic:
* If Execution Memory requires additional space and Storage Memory has unused capacity, it dynamically reclaims space from the Storage pool.
* Execution Memory can also evict cached tables from Storage to satisfy active processing demands.
* Storage Memory can borrow space from Execution Memory, but it cannot evict active Execution blocks.

For memory-intensive SIEM joins, it is recommended to decrease the storage allocation fraction, ensuring the Execution pool has guaranteed space:

```ini
spark.memory.fraction 0.8
spark.memory.storageFraction 0.2
```

### Container Overheads in Cloud Deployments
In Kubernetes (K8s) or YARN container environments, executors can be terminated by the OS OOM-Killer if total memory consumption exceeds container limits:

$$\text{Total Pod Memory} = \text{spark.executor.memory} + \text{spark.executor.memoryOverhead} + \text{spark.memory.offHeap.size}$$

To prevent container terminations, increase the memory overhead overhead buffer (typically to 15-20% of the executor's memory size) to accommodate off-heap allocations and PySpark execution states:

```ini
--conf spark.executor.memoryOverhead=8g
```

### Shuffle Partition Optimization
The `spark.sql.shuffle.partitions` parameter defines the number of target partitions generated after a shuffle boundary. The default value is set to `200`.

In massive SIEM deployments, this default is insufficient. If a join processes 10 TB of data using only 200 partitions, each task must process ~50 GB in memory, leading to severe disk spill write overheads and OOM crashes.

As a best practice, each partition task should target between **128 MB and 256 MB** of data in memory:

$$\text{Target Partitions} = \frac{\text{Total Shuffle Data Size}}{128 \text{ MB}}$$

For 190 GB of shuffle data, this requires setting the partition count to at least `1520`:

```ini
spark.sql.shuffle.partitions 1520
```

 paired with AQE coalesce settings to allow Spark to dynamically merge small partitions at runtime:

```ini
spark.sql.adaptive.coalescePartitions.enabled true
```

---

## 🌐 5. Deployment Strategies: Bare-Metal vs. Cloud-Native Architectures

Selecting the optimal resource manager and hosting model determines the scaling limits and total cost of ownership of the SIEM platform.

| Deployment Strategy | Resource Allocation Agility | Dependency Isolation | Operational Complexity | SIEM Workload Alignment |
| :--- | :--- | :--- | :--- | :--- |
| **YARN (On-Premises)** | Static, hardware-bound queues. Slow scaling. | Basic process isolation. Multi-tenancy conflict risks. | High. Requires active Hadoop cluster maintenance. | Best for organizations restricted by local data privacy regulations. |
| **Kubernetes (Cloud-Native)** | High (Dynamic Resource Allocation + K8s Node Autoscaler). | High. Dynamic isolated container runtimes. | Medium-High. Requires active Kubernetes engineering. | Optimal for modern multi-tenant cloud-native SOCs. |
| **EMR Serverless / Databricks** | High (Workload-level auto-scaling). | Managed by provider. High reliability. | Low operational overhead. | Best for teams focused entirely on security analytics over infrastructure maintenance. |

### On-Premises YARN Deployments
In traditional, on-premises data centers governed by local data regulations, Spark clusters typically run on **Hadoop YARN**.
* **Pros:** Standard resource manager that coordinates resources across other Hadoop ecosystem components (e.g., MapReduce, Hive).
* **Cons:** Scaling is slow and bound to physical hardware limits. Upgrading libraries or managing isolated Python environments for machine learning pipelines is complex.

### Cloud-Native Kubernetes (K8s) Deployments
In modern cloud architectures, Spark runs directly on **Kubernetes** using isolated container pods:
* **Dynamic Resource Allocation (DRA):** Enables Spark to dynamically request more executor pods from the K8s API during query spikes and terminate them when processing completes.
* **Autoscaling:** Paired with K8s Cluster Autoscalers, the cloud platform automatically boots more virtual nodes to handle workload demands.
* **Dependency Management:** All Python libraries, machine learning models, and system binaries are packaged within a single Docker image, eliminating dependency conflicts across multi-tenant applications.

### Serverless Cloud Options: AWS EMR Serverless and Databricks
For security operations teams looking to minimize infrastructure management, serverless cloud solutions are highly effective:
* **AWS EMR Serverless:** Provides managed Spark compute environments, automatically scaling resources to match query demands and charging on a pay-as-you-go model based on active executor runtimes.
* **Databricks:** Integrates optimized execution runtimes (Photon engine) and managed Delta Lake tables. Databricks scales compute resources dynamically at the workload level, reducing execution times and operational overhead.

---

## ⚙️ 6. Real-Time Online K-Means Anomaly Detection & Hyperparameters

For real-time network detection and response (NDR) pipelines (executed via `streaming_kmeans.py`), Spark leverages an online clustering engine to classify network flows. Unlike traditional offline models, Spark’s Streaming K-Means continuously updates centroid coordinates as new mini-batches arrive, accommodating shifting network baseline behaviors.

To achieve an optimal balance between anomaly detection sensitivity and reducing false positive alerts, we recommend tuning the following machine learning hyperparameters:

| Hyperparameter | Recommended Value | Operational & System Impact |
| :--- | :---: | :--- |
| **`KMEANS_K`** | `8` | **Number of Clusters:** Specifies the baseline clustering centroids. For highly complex corporate backbones or diverse networks, test `10` or `12` centroids to capture sub-protocols. |
| **`COLD_START_ROWS`** | `5000` | **Training Baseline Threshold:** The minimum number of log events required to train the initial cluster centroids before active anomaly scoring and real-time alerting are enabled. |
| **`ANOMALY_THRESHOLD`** | `4.5` | **Anomaly Sensitivity:** Specified in standard deviations from the nearest cluster centroid. Lowering this value (e.g., `3.5`) increases alert sensitivity (more false positives); raising it (e.g., `5.5`) filters out minor noise. |
| **`DECAY_FACTOR`** | `1.0` | **Centroid Memory/Decay:** Controls how past data influences current centroids. A value of `1.0` treats all historical data equally. Lower values (e.g., `0.9`) give more weight to newer connections, adapting to dynamic IP reassignments. |

---

## 🏁 Conclusion

Apache Spark 3.5.x serves as a highly performant distributed computation engine for high-throughput SIEM analytics. By utilizing off-heap byte management via Tungsten and optimizing physical queries using Catalyst and AQE skew-mitigation, Spark delivers bare-metal performance over complex datasets. Pairing deterministic Lineage recovery with RocksDB changelog checkpointing guarantees resilient, exactly-once processing over out-of-order Kafka event streams, while tuning dynamic shuffle partition sizes protects nodes from OOM failures. Deploying these architectures over Kubernetes or managed serverless platforms provides a highly scalable, stable foundation for real-time security analytics.

---

## 📝 References
1. *Project Tungsten: Bringing Spark Closer to Bare Metal*, Databricks, 2024.
2. *Deep Dive into the Spark Catalyst Optimizer*, Apache Spark Summit, 2025.
3. *Structured Streaming Programming Guide*, Apache Spark Documentation, 2025.
4. *RocksDB Stateful Streaming Optimization on EMR*, AWS Architecture Blog, 2025.
5. *Spark on Kubernetes: Scaling and Deployment Guide*, Databricks Developer Center, 2026.

---

## 🔗 Navigation & Links
*   ⬅️ **[Back to Root README](../README.md)**
*   📂 **[Go to Technical Documentation Library](./)**