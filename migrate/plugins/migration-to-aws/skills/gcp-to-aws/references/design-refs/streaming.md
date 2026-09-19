# Streaming Services Design Rubric

**Applies to:** Cloud Dataflow (`google_dataflow_job`, `google_dataflow_flex_template_job`)

**Quick lookup (no rubric):** Dataflow has no deterministic direct mapping — always apply this rubric.

**Pub/Sub ingestion layer:** If a `google_pubsub_topic` is present alongside Dataflow, apply `messaging.md` for
the Pub/Sub resource separately. This rubric covers the Dataflow stream-processing layer only.

## Eliminators (Hard Blockers)

| GCP Service | AWS            | Blocker                                                                                                                     |
| ----------- | -------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Dataflow    | Managed Flink  | Pipeline uses Apache Beam SDK → Managed Service for Apache Flink (Beam portable runner targets Flink backend)               |
| Dataflow    | MSK            | Pipeline reads/writes Kafka topics via KafkaIO connector → MSK replaces Pub/Sub + avoids connector shim                     |
| Dataflow    | Glue Streaming | ETL-only pipeline with no stateful aggregations, throughput < 10 MB/s → AWS Glue Streaming ETL (lower operational overhead) |

## Signals (Decision Criteria)

### Dataflow job (streaming pipeline)

- **Apache Beam SDK, multi-runner portability** → Managed Service for Apache Flink (Flink runner for Beam)
- **Pub/Sub source + stateful processing (windowing, aggregations)** → Kinesis Data Streams (ingestion) + Managed Service for Apache Flink (processing)
- **Kafka-native APIs required (consumer groups, compacted topics, Schema Registry, KSQL)** → MSK
- **ETL-centric, no stateful joins or windows, throughput < 10 MB/s** → AWS Glue Streaming ETL
- **High throughput (> 10 MB/s), complex windowing, exactly-once semantics** → Kinesis Data Streams + Managed Service for Apache Flink

### Dataflow Flex Template job

- Same signals as Dataflow job above
- **Containerized custom runner or portable pipeline** → Managed Service for Apache Flink (custom application JAR/container)

## 6-Criteria Rubric

Apply in order:

1. **Eliminators**: Does the pipeline use Apache Beam SDK, Kafka-native APIs, or an ETL-only pattern?
   - Beam portability → Managed Service for Apache Flink
   - Kafka-native → MSK
   - ETL-only, low throughput → AWS Glue Streaming ETL
2. **Operational Model**: Fully managed with auto-scaling?
   - Prefer Managed Service for Apache Flink (serverless, auto-scaling) over self-managed Flink on EC2/EKS
   - MSK Serverless if Kafka-native and cluster sizing is unpredictable
3. **User Preference**: From `preferences.json`: `design_constraints.availability`?
   - All three primary targets are multi-AZ by default — no special config needed for HA
   - If `multi-region` required: Kinesis Data Streams cross-region replication + Managed Service for Apache Flink per region
4. **Feature Parity**: Does the pipeline require features that differ across targets?
   - Exactly-once semantics, Apache Beam portability → Managed Service for Apache Flink
   - Kafka consumer groups, compacted topics, Schema Registry → MSK
   - Simple SQL-based streaming transformations → AWS Glue Streaming ETL
5. **Cluster Context**: Are other resources already using Kinesis, MSK, or Glue?
   - If Kinesis Data Streams already present → pair with Managed Service for Apache Flink
   - If MSK already present → use MSK as both transport and consumer coordination
6. **Simplicity**: Prefer the target that minimises new services
   - Pub/Sub + Dataflow → SNS/SQS (messaging.md) + Managed Service for Apache Flink (this rubric)
   - Kafka + Dataflow → MSK handles both transport and consumer coordination

## Trade-offs

| Dimension               | Kinesis Data Streams + Managed Flink         | MSK + Managed Flink                            | AWS Glue Streaming ETL     |
| ----------------------- | -------------------------------------------- | ---------------------------------------------- | -------------------------- |
| Operational complexity  | Low (fully managed, serverless auto-scaling) | Medium (broker config, partition sizing)       | Very low (serverless)      |
| Throughput ceiling      | High (up to 200 MB/s on-demand per stream)   | Very high (partition-limited, no hard ceiling) | Low–medium (ETL-oriented)  |
| Latency                 | Milliseconds                                 | < 20 ms (Kafka native)                         | Seconds (micro-batch)      |
| Apache Beam portability | Yes (Flink runner)                           | Yes (Flink runner + Kafka connector)           | No                         |
| Kafka-native APIs       | No                                           | Yes                                            | No                         |
| Best for                | Pub/Sub → AWS migration, new streaming apps  | Kafka-native pipelines, existing Kafka tooling | Simple ETL, low throughput |

## Examples

### Example 1: Pub/Sub + Dataflow streaming pipeline (Apache Beam)

- GCP: `google_dataflow_job` (streaming=true, Apache Beam pipeline reading from `google_pubsub_subscription`)
- Signals: Streaming pipeline, Pub/Sub source, Apache Beam SDK, stateful windowing
- Criterion 1 (Eliminators): Beam portability → Managed Service for Apache Flink
- Criterion 2 (Operational Model): Fully managed → Managed Service for Apache Flink
- → **AWS: Kinesis Data Streams (ingestion) + Managed Service for Apache Flink (processing)**
- Note: Apply `messaging.md` to the `google_pubsub_topic`/`google_pubsub_subscription` resources
  separately. Kinesis Data Streams replaces Pub/Sub as the durable, ordered ingestion stream.
- Confidence: `inferred`

### Example 2: Dataflow pipeline with Kafka source (KafkaIO connector)

- GCP: `google_dataflow_job` (pipeline reads from Kafka via KafkaIO connector)
- Signals: Kafka-native APIs, KafkaIO connector, existing Kafka tooling
- Criterion 1 (Eliminators): Kafka-native → MSK
- → **AWS: MSK (transport) + Managed Service for Apache Flink (processing)**
- Confidence: `inferred`

### Example 3: Dataflow Flex Template (ETL, low throughput)

- GCP: `google_dataflow_flex_template_job` (ETL pipeline, no stateful aggregations, throughput < 5 MB/s)
- Signals: ETL-only pattern, low throughput, no complex windowing or stateful joins
- Criterion 1 (Eliminators): ETL-only, low throughput → AWS Glue Streaming ETL
- → **AWS: AWS Glue Streaming ETL**
- Confidence: `inferred`

## Output Schema

```json
{
  "gcp_type": "google_dataflow_job",
  "gcp_address": "analytics-pipeline",
  "gcp_config": {
    "on_delete": "cancel",
    "parameters": {
      "inputSubscription": "projects/my-project/subscriptions/my-sub",
      "outputTableSpec": "my-project:dataset.table"
    }
  },
  "aws_service": "Kinesis Data Streams + Managed Service for Apache Flink",
  "aws_config": {
    "kinesis_stream_name": "analytics-pipeline-input",
    "flink_application_name": "analytics-pipeline",
    "flink_runtime_environment": "FLINK-1_19"
  },
  "confidence": "inferred",
  "rationale": "Dataflow streaming pipeline with Pub/Sub source → Kinesis Data Streams (ingestion) + Managed Service for Apache Flink (stream processing)"
}
```
