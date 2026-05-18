# 🐘⚡ Unified Database and Caching Tiers (PostgreSQL & Redis) Optimization Report

This comprehensive systems-level report details the operational strategies, memory geometries, concurrency mechanics, and high-availability configurations of the underlying storage and caching infrastructure backing the Apache Big Data SIEM. It examines both **PostgreSQL (v15+)**—which manages metadata catalogs for Hive and Apache Superset—and **Redis (v7+)**—which functions as a real-time caching, probabilistic filtering, and asynchronous task broker tier.

---

## 🏛️ Part I: PostgreSQL Core Architecture & Transaction Integrity

Security log telemetry and analytical metadata must never be compromised or lost due to hardware faults, kernel panics, or sudden power disruptions. PostgreSQL guarantees transaction integrity by adhering to strict ACID (Atomicity, Consistency, Isolation, Durability) principles backed by its Write-Ahead Logging (WAL) subsystem.

```
       Transactions (INSERT/UPDATE)
                  │
                  ▼
 ┌────────────────────────────────┐
 │     Shared Memory Buffers      │
 └────────────────────────────────┘
   │                            │
   │ (Asynchronous Page Sync)   │ (Synchronous Sequential Write)
   ▼                            ▼
Data Files (Random I/O)      WAL Log Segments (Sequential I/O)
```

### 1. ACID Compliance and Transactional Consistency
PostgreSQL enforces database constraints and invariants. If a transaction violates integrity constraints or encounters a runtime exception, the engine rolls back the entire transaction rather than just the failing statement. This ensures strict **Atomicity** (all-or-nothing execution).

For high-frequency schema modifications typical of dynamic security environments, PostgreSQL handles Data Definition Language (DDL) operations transactionally. Unlike database systems where DDL actions auto-commit, PostgreSQL wraps operations like table creation, partition registration, and index allocation within standard transaction blocks (`BEGIN ... COMMIT`). If a migration fails mid-way, a `ROLLBACK` reverts the schema to its exact pre-transaction state, preventing partial updates and ensuring consistency during dynamic partition allocations.

### 2. Write-Ahead Logging (WAL) and the Log Sequence Number (LSN)
To maximize write throughput, PostgreSQL avoids synchronously flushing modified 8 KB data pages to disk for every transaction. Instead, it records changes sequentially in a transaction journal known as the **Write-Ahead Log (WAL)**.

WAL changes are written to segment files (typically 16 MB, configurable via `--wal-segsize`) under the `pg_wal` directory. Each record is assigned a unique, monotonically increasing 64-bit integer called a **Log Sequence Number (LSN)**, representing its byte offset within the WAL stream.

LSN positions are exposed via the `pg_lsn` data type. Measuring the byte delta between LSN markers is a critical system metric for monitoring replication lag on standby nodes and tracking Point-In-Time Recovery (PITR) progress:

$$\text{LSN Format: } \text{Hex32} / \text{Hex32} \quad (\text{e.g., } \text{16/B374D848})$$

The binary layout of a WAL record is structured by C structs defined in `access/xlogrecord.h`:

| XLogRecord Header Field | C Data Type | Architecture & Function |
| :--- | :--- | :--- |
| **`xl_tot_len`** | `uint32` | Total length of the record, including payload, in bytes. |
| **`xl_xid`** | `TransactionId` | The unique Transaction ID (XID) that modified the record. |
| **`xl_prev`** | `XLogRecPtr` | The LSN pointer to the preceding WAL record. |
| **`xl_info`** | `uint8` | Flags specifying the record type and operation flags. |
| **`xl_rmid`** | `RmgrId` | Resource Manager ID (e.g., `RM_HEAP`, `RM_BTREE`) handling the log block. |
| **`xl_crc`** | `pg_crc32c` | CRC32C checksum verifying block data integrity on disk. |

During an `INSERT` of an alert payload, the record header is stamped with resource manager `RM_HEAP` and committed sequentially to the active WAL segment. This sequential logging model minimizes disk head movements on HDDs and avoids write amplification on SSDs, optimizing high-volume ingestion performance.

### 3. Crash Recovery and Page Idempotency
During reboots following an unexpected shutdown, the engine reads the `pg_control` file to identify the last valid Checkpoint (the REDO point). It then replays WAL transactions starting from this point to restore consistency.

To prevent corruption from duplicate executions (ensuring idempotency), the engine checks the `pd_lsn` value stored in the header of each 8 KB data page. If the WAL record's LSN is less than or equal to the page's `pd_lsn`, the modification is already present on disk and the record is safely skipped. If the LSN is greater, the update is applied. This protects the database against partial page write corruptions.

Unlike databases that maintain dedicated **Undo Logs** (e.g., Oracle or InnoDB-based MySQL) to roll back uncommitted changes, PostgreSQL does not physically delete or roll back aborted transactions. Instead, aborted records remain on disk but are ignored by other transactions using MVCC visibility rules.

This design eliminates Undo segment contention, reduces disk allocation latencies under heavy write workloads, and accelerates recovery times by performing only forward REDO actions.

---

## ⚡ Part II: Concurrency and MVCC (Multi-Version Concurrency Control)

SIEM systems handle highly concurrent operations. Agents continuously insert security events while analysts execute resource-intensive `SELECT` queries for threat hunting.

To prevent writes from blocking reads and vice versa, PostgreSQL leverages **Multi-Version Concurrency Control (MVCC)**. When a row is updated or deleted, PostgreSQL does not modify the existing record in-place; instead, it writes a new version of the row (tuple) to disk.

```
                  ┌────────────────────────────────────────┐
                  │          Active Heap Block             │
                  │                                        │
 [INSERT Tuple]  ──► [Tuple v1] (xmin: 101, xmax: 102)     │
                  │      │                                 │
 [UPDATE Tuple]   │      ▼ (ctid points to new version)    │
                  │  [Tuple v2] (xmin: 102, xmax: 0)       │
                  └────────────────────────────────────────┘
```

### 1. Tuple Visibility Metadata: `xmin` and `xmax`
To determine row visibility across concurrent transactions, PostgreSQL appends internal metadata columns to every row header (defined in `htup_details.h` as `HeapTupleHeaderData`, introducing roughly 23 bytes of overhead per tuple):

| Header Column | Size (Bytes) | Role in SIEM Concurrency |
| :--- | :---: | :--- |
| **`t_xmin`** | 4 | The Transaction ID (XID) that created this row version. |
| **`t_xmax`** | 4 | The XID that deleted or updated this row version (0 if active). |
| **`t_cid`** | 4 | Command Identifier (CID) tracking statement order within a transaction. |
| **`t_ctid`** | 6 | Physical pointer (block ID, offset) mapping to the newest version of the row. |
| **`t_infomask`** | 2 | Flag bits describing row state (e.g., if the tuple is frozen or contains nulls). |

#### Visibility Evaluation Rules:
* **Creation Rule:** A row is visible to a transaction if `t_xmin` was successfully committed before the current transaction started.
* **Deletion Rule:** If `t_xmax` is populated, the row remains visible only if the transaction that deleted or updated it (matching `t_xmax`) has not yet committed.

### 2. The SnapshotData Memory Structure
When a query or transaction initializes, it receives a transaction snapshot structured by the `SnapshotData` C-struct:

| `SnapshotData` Field | Role in Transaction Visibility |
| :--- | :--- |
| **`xmin`** | The lowest active Transaction ID (XID) at snapshot creation. All transactions below `xmin` are committed and visible. |
| **`xmax`** | The highest assigned XID. All transactions at or above `xmax` are uncommitted and invisible. |
| **`xip_list`** | Array of XIDs that were active (in-progress) when the snapshot was taken. Their changes remain invisible. |

For example, a snapshot state represented as `100:104:100,102` sets `xmin=100`, `xmax=104`, and `xip_list=[100, 102]`. When querying rows:
* Row changes committed by XID 99 are visible.
* Changes from active XIDs 100 and 102 are invisible.
* Changes from committed XIDs 101 and 103 are visible.
* Any XID at or above 104 is treated as future state and remains invisible.

At the default `Read Committed` isolation level, a new snapshot is generated for each statement. Under `Repeatable Read`, a single snapshot is preserved for the duration of the transaction, ensuring consistent views for complex correlations.

### 3. XID Wraparound Protection & Row Freezing
Transaction IDs are represented as 32-bit integers, providing up to 4.2 billion unique transactions. In high-volume SIEM platforms, this limit can be exhausted within months.

Without intervention, wrapping past 4.2 billion transactions would cause older transactions to appear to have occurred in the "future" under modulo-2^32 arithmetic, rendering historical logs invisible.

To prevent this, the `VACUUM` subsystem freezes older records by assigning them a special XID called `FrozenTransactionId` (value 2). Modern PostgreSQL releases preserve the original `xmin` for forensic audits but set a flag in the `t_infomask` header column to mark the row as frozen. This ensures frozen rows are treated as older than all active and future transactions, preserving their visibility indefinitely.

---

## 🧹 Part III: Database Maintenance: Dead Tuples and Autovacuum

Because MVCC creates new row versions during updates and deletions rather than performing in-place edits, outdated versions remain on disk as **"Dead Tuples."** High-volume updates or log retention pruning can generate significant dead tuples, leading to table and index bloat. Bloat fragments physical storage, increases disk I/O demands, and reduces shared buffer cache hit ratios.

### 1. Free Space Map (FSM) and Visibility Map (VM)
PostgreSQL utilizes two key metadata maps to manage space allocation and query optimization:
* **Free Space Map (FSM) (`.fsm`):** Tracks available space within each 8 KB page using a hierarchical tree structure. When new rows are inserted, the engine consults the FSM to find a page with sufficient space, reducing unnecessary table growth.
* **Visibility Map (VM) (`.vm`):** Tracks pages that contain only tuples visible to all current and future transactions (meaning they contain no dead tuples). The VM optimizes maintenance tasks and enables **Index-Only Scans**, returning results directly from the index if the VM confirms the target pages contain no dead tuples.

### 2. Autovacuum Tuning for High-Volume Systems
The `autovacuum` daemon automatically reclaims space occupied by dead tuples, updates the FSM and VM, and freezes older records to prevent XID wraparound.

Autovacuum triggers are determined by two primary threshold equations:

$$\text{Vacuum Threshold} = \text{autovacuum\_vacuum\_threshold} + (\text{autovacuum\_vacuum\_scale\_factor} \times \text{Live Tuples})$$

$$\text{Insert Threshold} = \text{autovacuum\_vacuum\_insert\_threshold} + (\text{autovacuum\_vacuum\_insert\_scale\_factor} \times \text{Inserted Tuples})$$

The default scale factor is set to 20% (`0.2`). In a table with 1 billion rows, this default requires 200 million modifications before a vacuum is triggered, allowing significant bloat to accumulate. For high-volume SIEM deployments, this threshold should be set to much more aggressive levels (e.g., 1% or `0.01`) on active tables:

```sql
ALTER TABLE firewall_logs SET (autovacuum_vacuum_scale_factor = 0.01);
```

Autovacuum impact on write performance is managed using cost-based rate limits. Each page read or write action accumulates cost credits. When these credits reach `autovacuum_vacuum_cost_limit` (default: 200), the process sleeps for `autovacuum_vacuum_cost_delay` (default: 2 ms) to prevent I/O saturation. On high-performance NVMe storage arrays, these limits should be increased to optimize vacuum throughput:

```sql
ALTER SYSTEM SET autovacuum_vacuum_cost_limit = 2000;
ALTER SYSTEM SET autovacuum_vacuum_cost_delay = 2;
```

PostgreSQL 17 optimizes vacuum memory management, significantly reducing RAM utilization and accelerating autovacuum operations in high-concurrency environments. For severe bloat recovery on live systems without locking tables, administrators should leverage external utilities like `pg_repack`.

---

## 🔍 Part IV: SIEM Metadata Indexing Strategies

SIEM environments manage distinct data types: structured, sequential fields (such as timestamps, IP addresses, and port numbers) alongside unstructured payloads (such as JSONB structures, log lines, and threat intelligence arrays). Applying the same index type to all columns degrades write performance and increases storage overhead.

```
[ B-Tree Index ]  ──► B-Tree Nodes ──► Specific Row IDs (Exact / Range Lookups)
[ GIN Index ]     ──► Inverted Keys ──► Array of Row IDs (Nested JSONB / Arrays)
[ BRIN Index ]    ──► Block Ranges  ──► Min/Max Values per Page Range (Time Series)
```

### 1. B-Tree Index (Exact & Range Queries)
The B-Tree is the default indexing model in PostgreSQL. It is highly optimized for scalar equality and range comparisons (`<`, `<=`, `=`, `>=`, `>`). B-Tree searches scale with $O(\log n)$ complexity, making them ideal for lookups on fields like `host_id`, `mac_address`, or single IP values.

### 2. GIN Index (Generalized Inverted Index)
To query nested JSONB payloads or arrays, PostgreSQL utilizes the **Generalized Inverted Index (GIN)**. GIN maps internal keys (such as JSON keys or array elements) to the records containing them, similar to a search engine index.

Using GIN indexes enables sub-millisecond lookups on complex nested fields:
```sql
SELECT * FROM raw_logs WHERE metadata @> '{"status": "malicious"}';
```
To optimize GIN write performance, PostgreSQL uses the `fastupdate` mechanism. New writes are appended to a temporary pending list (`gin_pending_list_limit`), which is flushed to the main index in batches during idle periods or autovacuum cycles. Additionally, using the `jsonb_path_ops` operator class rather than the default `jsonb_ops` index type reduces index footprints and speeds up lookups by indexing only JSON path-value hashes.

| GIN Configuration | Insert Latency (100k Rows) | Write Overhead vs. Baseline |
| :--- | :---: | :---: |
| **No Index (Baseline)** | 1.58s | - |
| **`jsonb_ops` (Default)** | 2.84s | +79% write latency |
| **`jsonb_path_ops` (Optimized)** | 1.84s | +16% write latency |

### 3. BRIN Index (Block Range Index)
SIEM events are highly chronological, written sequentially to disk blocks in time order. Creating B-Trees on these massive time-series tables results in enormous index files.

**Block Range Indexes (BRIN)** are designed specifically for these sequentially ordered datasets. Rather than mapping individual rows, BRIN indexes summarize sequential blocks of pages (typically 128 pages, or 1 MB) by recording only the minimum and maximum values within each range. For a 10-million-row log table, a B-Tree index can occupy ~214 MB of storage, while a BRIN index on the same column requires only ~48 KB—a 4000x reduction in storage footprint.

To optimize BRIN performance on highly ordered datasets, SREs can reduce the `pages_per_range` parameter (e.g., to 32 or 64). This increases index precision and page pruning accuracy, accelerating query execution times:
```sql
CREATE INDEX idx_brin_time ON firewall_logs USING BRIN (event_timestamp) WITH (pages_per_range = 32);
```

| Index Type | Optimal SIEM Use Case | Index Footprint | Optimization Notes |
| :--- | :--- | :--- | :--- |
| **B-Tree** | Scalar exact match lookups (e.g., `host_id`, `mac_address`). | Large (MB to GB scale) | High-performance range filtering; does not support JSONB internals. |
| **GIN** | Complex JSONB searches, array elements, and full-text searches. | Medium-Large | Enable `fastupdate`; use `jsonb_path_ops` to minimize write overhead. |
| **BRIN** | Highly ordered time-series columns (e.g., timestamps). | Extremely Small (KB scale) | Requires sequential data; updates degrade indexing accuracy. |

---

## ⚡ Part V: Redis Event-Loop Architecture & Probabilistic Filtering

High-throughput distributed systems typically scale by adding more CPU cores and application threads. However, Redis’s core execution model relies on a **Single-Threaded Event Loop** to process commands sequentially, eliminating multithreaded synchronization bottlenecks while delivering millions of operations per second in memory.

```
       [ Concurrent Client Network Requests ]
            │             │             │
            ▼             ▼             ▼
      ┌─────────────────────────────────────┐
      │  I/O Multiplexing (epoll / kqueue)  │
      └─────────────────────────────────────┘
                         │
             (Sequential Event Queue)
                         ▼
      ┌─────────────────────────────────────┐
      │       Single-Threaded Core          │
      │        (In-Memory Command Execution)│
      └─────────────────────────────────────┘
```

### 1. I/O Multiplexing and Cache Locality
Redis avoids the *thread-per-connection* model by leveraging **I/O Multiplexing** algorithms (such as Linux `epoll` or macOS `kqueue`) at the operating system kernel level. Because commands are executed sequentially in memory, Redis avoids lock mechanisms, completely eliminating **Lock Contention** and **Deadlock** conditions across concurrent operations.

Furthermore, on multi-socket servers using **NUMA (Non-Uniform Memory Access)** architectures, binding the Redis process to a specific CPU core (**CPU Affinity**) ensures that memory allocations remain local to the active socket, maximizing hardware efficiency.

While command execution remains single-threaded, Redis 7 spreads the overhead of parsing raw client network packets and formatting outbound responses across background helper threads:
```ini
io-threads 4
io-threads-do-reads yes
```

### 2. Listpack Encoding and Memory Efficiency
Redis 7 replaces legacy `ziplist` structures with **Listpack** encoding. Listpacks store small lists, sets, and hashes within a tightly packed contiguous byte array, eliminating pointer overheads and memory fragmentation.

Using parameters in `redis.conf`, engineers can enforce Listpack representations for metadata keys (such as asset logs or threat hashes), ensuring they fit within a single CPU cache line for O(1) lookups:
```ini
hash-max-listpack-entries 512
hash-max-listpack-value 64
list-max-listpack-size -2
```

### 3. Probabilistic Data Filtering: Bloom Filters
SIEM architectures must continuously cross-reference millions of incoming IP addresses, domain names, or file hashes against Threat Intelligence blacklists. Storing 10 million indicator strings in a standard `SET` structure requires gigabytes of RAM due to key string and pointer metadata overheads.

To optimize memory usage, engineers can deploy **Bloom Filters**. A Bloom Filter maps keys to a fixed-size bit array using multiple independent hash functions ($k$). A Bloom Filter with a configured 0.01% false positive rate requires only a fraction of the RAM of a standard set:

$$\text{Memory Size (bits)} \approx - \frac{n \ln(p)}{(\ln 2)^2}$$

When a log packet arrives at the ingestion pipeline, the IP is checked using the `BF.EXISTS` command.
* If the filter returns `0` (False), the IP is guaranteed not to be in the blacklist, allowing the log to bypass downstream database lookups.
* If the filter returns `1` (True), the system confirms a potential match and routes the query to disk-based relational storage (PostgreSQL) for verification.

This design reduces redundant database IOPS by up to 99% during active security incidents, preserving database resources.

---

## 📊 Part VI: SOC Dashboard Caching & State Management

In a Security Operations Center (SOC), analysts use Business Intelligence (BI) platforms (such as Apache Superset) to monitor security trends. Generating these dashboards requires executing complex, long-running SQL queries across cold storage engines, which can saturate analytical databases under concurrent access.

Redis serves as a high-speed caching and metadata coordination layer between analytical engines and the dashboard layer.

```
 [ Apache Superset Dashboard ]
              │
      (Explore / Cache Miss)
              ▼
   ┌──────────────────────────────────┐
   │     L1 Local App RAM Cache       │
   └──────────────────────────────────┘
              │ (Cache Miss)
              ▼
   ┌──────────────────────────────────┐
   │  L2 Distributed Redis Cache      │
   └──────────────────────────────────┘
              │ (Cache Miss)
              ▼
    [ Cold Data Lake / Spark Engine ]
```

### 1. Apache Superset Caching Layers
Apache Superset utilizes Flask-Caching to manage dashboard state across four distinct Redis-backed caching layers:

| Config Parameter | Dependency Status | Operational Role in Caching |
| :--- | :---: | :--- |
| **`FILTER_STATE_CACHE_CONFIG`** | Required | Caches active UI filters, selected IP scopes, and custom time ranges for analysts, preserving state across page transitions. |
| **`EXPLORE_FORM_DATA_CACHE_CONFIG`** | Required | Caches active query form parameters, allowing analysts to iterate on search filters without losing context. |
| **`CACHE_CONFIG`** | Optional | Caches internal metadata (user permissions, panel schemas) to speed up application routing. |
| **`DATA_CACHE_CONFIG`** | Optional | **Critical Performance Layer:** Caches JSON-serialized query results. Repeated requests pull data directly from Redis in milliseconds rather than re-running queries on cold storage. |

### 2. Multi-Level Caching (L1/L2) and Distributed Invalidation
While Redis provides sub-millisecond lookups, high-volume dashboard endpoints can optimize query times further by using a **Multi-Level Caching** strategy:
* **L1 Cache (Local Memory):** The application server caches highly requested keys in its local RAM (using LRU dictionaries), achieving nanosecond-level access times.
* **L2 Cache (Redis Cluster):** If a key is missing from L1, the query falls back to the shared Redis cluster.

To maintain consistency between L1 and L2 caches, Redis uses its **Pub/Sub** messaging engine to broadcast invalidation signals when a key is modified:
```
[ Update Key ] ──► [ Redis L2 ] ──► Pub/Sub Invalidation Broadcast ──► [ App Node 1 ] ──► Clear L1 Cache
                                                                    ──► [ App Node 2 ] ──► Clear L1 Cache
```
This prevents application nodes from serving stale cached states during active incidents.

### 3. Distributed Query Lock Management
To prevent **Cache Stampedes** (where multiple application servers simultaneously query the underlying database for an expired cache key), Superset uses Redis to manage distributed locks. Using the atomic `SET NX EX` command, the first thread to request the missing data registers a temporary lock, forcing subsequent requests to wait for the cached result to be populated rather than generating redundant query loads.

---

## ⚙️ Part VII: Task Orchestration and Event-Driven Pipelines

SIEM architectures offload CPU-intensive operations (such as IP lookup enrichment, OSINT threat queries, ML anomaly inferences, and SOAR response playbooks) to asynchronous task workers managed by **Celery** with Redis acting as the message broker.

```
[ Ingestion App ] ──(LPUSH Task Payload)──► [ Redis List (Queue) ] ◄──(BRPOP Task Payload)── [ Celery Workers ]
```

### 1. Redis as a Message Broker and Results Backend
Celery routes tasks to background workers using Redis lists:
* **Task Queuing:** The application adds JSON task payloads to a target list using the `LPUSH` command.
* **Worker Fetching:** Idle Celery workers retrieve tasks from the list using the blocking `BRPOP` command.

The `BRPOP` command blocks the connection until a task is available, preventing workers from consuming CPU cycles with continuous polling loops. Once a task completes, the worker writes the execution state and results to Redis (acting as the Celery Results Backend) using Redis Hashes with custom TTLs to prevent memory leaks.

### 2. High-Load Queue Management and Congestion Mitigation
During severe security events (such as a volumetric DDoS attack), task ingestion rates can outpace worker consumption rates, leading to queue backlog and processing delays. SREs should implement the following configurations:
1. **Priority Queue Separation:** Separate tasks into dedicated queues based on severity (e.g., `critical_alerts`, `threat_enrichment`, and `default_tasks`), allocating dedicated worker instances to high-priority queues.
2. **Adjusting Visibility Timeouts:** For long-running ML analytics, increase the visibility timeout (`visibility_timeout`) in the Celery broker configuration to prevent redundant task re-deliveries:
   ```python
   broker_transport_options = {
       'visibility_timeout': 3600,  # 1 hour
   }
   ```
3. **Transient Queues:** Configure short-lived tasks (such as periodic agent health checks) to run on transient queues (`transient_queues`), bypassing disk persistence writes to reduce IOPS demands on the Redis storage layer.

### 3. Event-Driven Pipelines: Redis Streams
For critical security pipeline events, **Redis Streams** store messages in a append-only log structure. Multiple consumer groups can read from the stream independently, tracking their consumption progress using offsets.

```
[ Stream Ingestion ] ──► [ XADD Alert Stream ] ──(PEL Tracker)──► [ Consumer Group Worker ]
                                                                          │
                                                                   (Process & ACK)
                                                                          ▼
                                                                  Remove from PEL
```

If a worker crashes while processing a stream message, the message is not lost; it remains in the **Pending Entries List (PEL)**. When the worker recovers or a peer takes over, the unacknowledged message is retrieved, processed, and acknowledged (`XACK`), guaranteeing **at-least-once** delivery across the pipeline.

---

## 💾 Part VIII: Memory Eviction Policies and Hybrid Persistence

Because Redis operates primarily in-memory, engineers must design strategies to manage storage limits and protect data persistence against system failures.

### 1. Memory Eviction Policies
The `maxmemory-policy` setting in `redis.conf` defines how Redis reclaims space when it reaches its maximum memory limit:

| Eviction Policy | Algorithmic Mechanism | Optimal SIEM Use Case |
| :--- | :--- | :--- |
| **`noeviction`** | Returns write errors to clients when memory is full, preserving existing data. | Ideal for critical message broker queues where data loss is unacceptable. |
| **`allkeys-lru`** | Evicts the **Least Recently Used** keys across the entire keyspace. | Best for general dashboard caching where older cached reports can be safely evicted. |
| **`allkeys-lfu`** | Evicts the **Least Frequently Used** keys across the entire keyspace. | **Highly Recommended for Threat Intel:** Preserves active hot keys (such as common threat hashes) in memory while evicting rare outliers. |
| **`volatile-ttl`** | Evicts keys with the shortest remaining Time-to-Live (TTL) values. | Ideal for session states or temporary task results with explicit expiration windows. |

#### Mitigating Cache Thrashing: LFU vs. LRU
Under standard LRU eviction, if a malicious actor generates millions of scan events with random source IPs, the cache fills up with these one-off keys. Because they are the "most recently accessed," the LRU policy preserves them while evicting critical, high-frequency blacklist entries that haven't been accessed in the last few minutes. This scenario is known as **Cache Thrashing**.

To prevent this, the **Least Frequently Used (LFU)** policy tracks access frequency using an 8-bit logarithmic counter alongside a decay interval:
```ini
lfu-log-factor 10
lfu-decay-time 1
```
Hot keys retain high frequency scores and remain protected in memory, while one-off scan events are quickly evicted.

### 2. Hybrid Persistence: Combining RDB and AOF
Redis 7 combines persistence methods into a **Hybrid Persistence** model. When AOF rewriting is triggered, the engine writes the active memory state as a compact RDB snapshot at the beginning of the AOF file, appending subsequent writes as sequential AOF logs:
```ini
aof-use-rdb-preamble yes
appendfsync everysec
```
During recovery, the engine loads the RDB snapshot at full speed and replays the short remaining AOF tail, delivering both low RPO data protection and low RTO recovery times.

---

## 🌐 Part IX: Deployment Topologies & High-Availability Configurations

Maintaining high database and caching availability is critical during active incidents. High Availability configurations differ significantly depending on whether the deployment is on cloud infrastructure or on-premises bare-metal servers.

### 1. PostgreSQL High Availability

#### Cloud High Availability (Managed DBaaS)
In AWS RDS, Multi-AZ deployments use a primary instance that replicates data to a standby instance in a different Availability Zone (AZ) at the storage volume layer using **synchronous, block-level replication**. This storage-layer replication ensures zero data loss (RPO=0) during failures, but adds write commit latency. Failover transitions are managed automatically by updating DNS records.

#### On-Premises High Availability (Patroni & Consensus)
For self-managed clusters, **Patroni** is the industry standard. Patroni uses Python-based daemons and a Distributed Configuration Store (DCS) (such as `etcd`) to maintain cluster state using the Raft consensus protocol.

```
                   ┌─── [Primary Node] (Leader Key) ───┐
                   │                                   ▼
 [Distributed CS] ◄┤                           [Streaming Replication]
   (etcd / Raft)   │                                   ▲
                   └─── [Replica Nodes] ───────────────┘
```

If the Primary node goes offline, the Patroni daemons detect the heartbeat loss. The leader key lease expires, and Patroni promotes the replica with the most up-to-date WAL LSN position to the Primary role. If a network partition occurs, Patroni leverages Watchdog timers to force-reboot or isolate the isolated primary node (fencing), preventing split-brain corruption.

PostgreSQL 17 enhances this by introducing **Failover Logical Slots**, synchronizing logical slots across nodes so subscribers automatically resume streaming from the new primary after a failover.

### 2. Redis High Availability

#### On-Premises Distributed Topologies
*   **Redis Sentinel (High Availability Focus):** Retains the entire dataset on a single Master node while maintaining read-only replicas. Sentinel daemons monitor node health and handle consensus failovers automatically. Ideal if the entire dataset fits within a single server's RAM.
*   **Redis Cluster (Throughput & Sharding Focus):** Splits the keyspace across multiple Master nodes using **Algorithmic Sharding** (16,384 Hash Slots). Keys are routed using CRC16 hashing:
    $$\text{Slot} = \text{CRC16}(\text{Key}) \pmod{16384}$$
    In a Redis Cluster, multi-key operations must locate all target keys on the same physical node. SREs use **Hash Tags** (e.g., `{alert_session_99}_src_ip`) to force related keys to resolve to the same slot, preventing `CROSSSLOT` errors.

#### Managed Cloud Architectures
AWS ElastiCache for Redis leverages Enhanced I/O Multiplexing to aggregate incoming commands from multiple Celery workers into a single pipeline, increasing write throughput by up to 72% while reducing latency. For global security operations distributed across multiple regions, managed CRDT-driven active-active replication merges regional updates asynchronously, preventing write collisions and ensuring high availability.

---

## 🏁 Part X: Conclusion & SRE Best Practices

PostgreSQL and Redis serve as highly performant and secure backing systems in enterprise SIEM architectures. 

To ensure optimal system performance under massive events per second (EPS) pressure, SREs must apply the following structural practices:
1.  **Aggressive Vacuuming:** Tune declarative partitioning boundaries and set the `autovacuum_vacuum_scale_factor` to `0.01` on active metadata tables to prevent dead tuple bloat from degrading storage read/write performance.
2.  **Custom GIN Indexing:** Optimize unstructured search paths using `jsonb_path_ops` indexes over JSONB parameters, and pair chronological log tables with extremely lightweight BRIN indexes (`pages_per_range = 32`) to achieve a 4000x index compression ratio.
3.  **Probabilistic blacklists:** Protect relational databases from heavy IOPS burdens by implementing Bloom Filters (`BF.EXISTS`) at the ingestion layer to filter out 99% of clean network traffic before querying relational databases.
4.  **LFU Cache Reclamation:** Set the eviction policy to `allkeys-lfu` with a customized decay time inside `redis.conf` to prevent cache thrashing caused by high-volume malicious scan events.

---

## 📝 References
1. *ACID Compliance and Transaction Processing*, PostgreSQL Global Development Group, 2026.
2. *Write-Ahead Logging (WAL) Internals*, PostgreSQL Documentation, 2025.
3. *GIN and BRIN Index Performance at Scale*, Crunchy Data Blog, 2025.
4. *Patroni High Availability Template*, Zalando, 2025.
5. *PostgreSQL 17 Feature Release Highlights*, PostgreSQL Global Development Group, 2024.
6. *Redis Core Internals and the Event Loop*, Salvatore Sanfilippo, 2024.
7. *Probabilistic Data Structures at Scale*, Confluent Developer, 2025.
8. *Redis Persistence and Hybrid Storage Options*, Redis Labs, 2025.
9. *Scaling Asynchronous Pipelines with Celery and Redis*, Celery Project Documentation, 2026.
10. *Multi-Region Replication using CRDTs*, Redis Enterprise Architecture, 2025.

---

## 🔗 Navigation & Links
*   ⬅️ **[Back to Root README](../README.md)**
*   📂 **[Go to Technical Documentation Library](README.md)**
