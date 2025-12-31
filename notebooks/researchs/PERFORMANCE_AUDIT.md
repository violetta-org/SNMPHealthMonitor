# Performance & Scalability Audit: SNMP Health Monitor System

## 1. SYSTEM TOPOGRAPHY & BOTTLENECKS
**Current Flow:**
The system operates on a **Pull-Push model**. The `Manager` service polls SNMP agents periodically (Pull), processes metrics, writes them to a MySQL database, and sends a UDP notification to the `Query Service`. The `Query Service` listens for UDP packets, transforms the payload for the frontend, and pushes updates via Socket.IO (Push).

**Critical Choke Points:**
1.  **Sequential SNMP Fetching (`fetch_snmp_metrics_async`)**: The collector loops through the OID list and `awaits` each SNMP request sequentially. With ~176 metrics, even a 20ms latency per request leads to substantial blocking time (e.g., 3.5s+), forcing the loop to overrun the 1s interval.
2.  **Synchronous Database Writes (`write_metrics_batch`)**: The main loop in `manager.py` performs blocking SQL inserts and commits *after* data collection, further delaying the next poll cycle.
3.  **Synchronous Notification Handling (`app.py`)**: The `on_new_data` callback in the Query Service processes data and broadcasting on the receiver thread, potentially blocking packet ingestion under high load.

**Resource Contention:**
*   **Network I/O**: The single-threaded (or effectively serial async) SNMP collection is I/O bound.
*   **Main Thread (Manager)**: Exhausted by blocking internal logic (DB write + Network Sync Wait).

**Improvement Matrix:**

| Area | Proposed Change | Tool/Mechanism | Impact |
| :--- | :--- | :--- | :--- |
| **Concurrency** | Parallelize SNMP OID fetching | `asyncio.gather` | **High** |
| **Parallelism** | Offload DB writes to separate worker | `threading.Thread` / `multiprocessing` | **Medium** |
| **Data Layer** | Batch database commits / Async DB | `aiomysql` or Background Queue | **Low** |
| **Messaging** | Decouple Manager from Query Service | `Redis Pub/Sub` (Future) | **Low** |

---

## 2. DEEP DIVE: WORKER & QUEUE STRATEGY
**Producer/Consumer Model:**
*   **Producer**: The SNMP Collection Loop. It should purely fetch data and push it into a local queue.
*   **Consumer 1 (DB Writer)**: A dedicated thread/process that pulls processed metrics from the queue and handles `INSERT` operations in bulk transaction batches (e.g., every 500 records or 5 seconds).
*   **Consumer 2 (Notifier)**: A separate lightweight thread that sends the UDP broadcast.

**Worker Configuration:**
*   **Manager Service**: 
    *   **1 Main Thread**: Orchestrator & Logic.
    *   **1 Async Event Loop**: For parallel SNMP fetching.
    *   **1 DB Worker Thread**: For blocking SQL I/O.
*   **Query Service**: Keep as-is (Gevent/Eventlet for Socket.IO handle concurrency well), ensuring `on_new_data` remains non-blocking for DB calls.

**Queue Reliability:**
*   Use local `queue.Queue` for inter-thread communication. 
*   If DB is down, the queue can act as a buffer (Ring Buffer) to prevent memory overlap, discarding oldest metrics if full.

---

## 3. OBSERVABILITY & SELF-HEALING (MySQL-Centric)

**Heartbeat Implementation:**
*   **Mechanism**: The Manager should update a `last_seen` timestamp in a `system_status` (or `devices`) table every cycle.
*   **Check**: The Query Service exposes an endpoint that checks:
    ```sql
    SELECT name, status FROM devices WHERE last_seen < NOW() - INTERVAL 10 SECOND;
    ```
    If this query returns rows, those devices are marked "OFFLINE".

**Telemetry Points (Stored in MySQL):**
Instead of exporting to Grafana, we log performance metrics into a new table `agent_diagnostics`:
*   **`collection_latency_ms`**: Time taken to fetch SNMP OIDs.
*   **`db_write_latency_ms`**: Time taken to commit the batch.
*   **`cycle_time_ms`**: Total loop time.

**Alerting Logic:**
*   **Query-Service Background Task**: A simplified periodic check (e.g., every 1 min) runs SQL queries to detect anomalies.
    *   **Critical**: `SELECT count(*) FROM agent_diagnostics WHERE cycle_time_ms > 2000 AND ts > NOW() - INTERVAL 1 MINUTE` (System is lagging).
    *   **Data Gap**: `SELECT count(*) FROM net_io_counters WHERE ts > NOW() - INTERVAL 1 MINUTE` returns 0 (Data pipeline broken).

---

## 4. IMPLEMENTATION CODE SNIPPET
**Most Impactful Change: Parallel SNMP Fetching**
Instead of `for` loop `await`, use `asyncio.gather` to fetch all OIDs concurrently.

```python
# rasberrypi/collectors/snmp.py

async def fetch_snmp_metrics_async(host, port, community, oids):
    transport = await UdpTransportTarget.create((host, port), timeout=1.5, retries=1)
    
    # helper for single request
    async def fetch_one(entry):
        try:
            if entry['method'] == 'walk':
                return await _walk_helper(transport, community, entry)
            else:
                return await _get_helper(transport, community, entry)
        except Exception:
            return []

    # FIRE CONCURRENT REQUESTS
    tasks = [fetch_one(entry) for entry in oids]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten results
    flat_metrics = []
    for res in results_list:
        if isinstance(res, list):
            flat_metrics.extend(res)
            
    return flat_metrics
```
