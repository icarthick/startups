# Messaging Services Design Rubric

**Applies to:** Pub/Sub, Cloud Tasks

**Quick lookup (no rubric):** Check `fast-path.md` first (Pub/Sub → SNS/SQS, etc.)

## Eliminators (Hard Blockers)

| GCP Service | AWS | Blocker                                                                                                 |
| ----------- | --- | ------------------------------------------------------------------------------------------------------- |
| Pub/Sub     | SNS | Exactly-once delivery required → SNS FIFO + SQS FIFO (SNS FIFO supports exactly-once via deduplication) |
| Pub/Sub     | SQS | Multiple subscribers per topic → SNS (not SQS)                                                          |
| Cloud Tasks | SQS | Scheduled/delayed task execution → EventBridge + SNS/SQS                                                |

## Signals (Decision Criteria)

### Pub/Sub

- **Multiple subscribers, broadcast** → SNS (pub/sub pattern)
- **Single consumer, durability** → SQS (queue pattern)
- **Exactly-once delivery** → SNS FIFO + SQS FIFO (deduplication enabled)
- **Real-time, low latency** → SNS (vs SQS polling delay)

### Cloud Tasks

- **HTTP callback execution** → EventBridge + SNS/SQS (route to Lambda/Fargate)
- **Delayed/scheduled queue** → SQS + Lambda (ScheduledEvents)

#### Migration notes

- **Push vs pull**: Cloud Tasks pushes HTTP requests directly to a target URL (push model); SQS is pull-based — consumers poll with `ReceiveMessage`. Bridge the gap with an SQS→Lambda event-source mapping to restore push-invocation semantics for the worker.
- **Per-task delay and scheduling**: Cloud Tasks supports an arbitrary future `schedule_time` (hours or days ahead); SQS delay queues cap at **15 minutes** (`DelaySeconds` 0–900 s). Use **EventBridge Scheduler** for delays beyond 15 minutes — it supports one-time and recurring schedules with no time ceiling and can target SQS `SendMessage` or Lambda directly.
- **Delivery semantics**: Both Cloud Tasks and SQS Standard provide **at-least-once delivery** — workers must be idempotent on both sides. Use SQS FIFO if exactly-once processing is required.
- **Rate and concurrency controls**: Cloud Tasks exposes `max_dispatches_per_second` and `max_concurrent_dispatches` at the queue level; SQS Standard offers nearly unlimited throughput with no built-in rate throttle. Replicate controls via Lambda reserved concurrency, SQS event-source mapping `MaximumConcurrency`, or application-level throttling on the consumer.
- **Routing guidance**: prefer **EventBridge Scheduler** when the dominant requirement is timed or scheduled dispatch (especially >15 min, one-time, or cron-based); prefer a **direct Lambda invocation** for lightweight stateless HTTP workers that need no queue buffering; use **SQS** when the core need is durable async buffering, decoupled worker pools, or backpressure.

## 6-Criteria Rubric

Apply in order:

1. **Eliminators**: Does GCP config require AWS-unsupported features? If yes: switch
2. **Operational Model**: Managed (SNS, SQS, EventBridge) vs Custom queue?
   - Prefer managed
3. **User Preference**: From `preferences.json`: `design_constraints.availability`?
   - SNS and SQS are multi-AZ by default — no special config needed for HA
   - If ordering or exactly-once delivery required → SQS FIFO (see Eliminators)
4. **Feature Parity**: Does GCP config need features unavailable in AWS?
   - Example: Pub/Sub ordering guarantee → SQS FIFO (has ordering)
5. **Cluster Context**: Are other resources using SNS/SQS? Match if possible
6. **Simplicity**: SNS + SQS (coupled) vs separate services

## Examples

### Example 1: Pub/Sub Topic (broadcast)

- GCP: `google_pubsub_topic` (name="user-events", message_retention_duration="7d")
- Signals: Broadcast events, multiple subscribers likely
- Criterion 1 (Eliminators): PASS (retention not critical for broadcast)
- Criterion 2 (Operational Model): SNS (pub/sub)
- → **AWS: SNS Topic (Standard)**
- Note: SNS does not support message retention like GCP Pub/Sub. If retention is critical, use SQS instead.
- Confidence: `inferred`

### Example 2: Pub/Sub Topic (exactly-once)

- GCP: `google_pubsub_topic` + `google_pubsub_subscription` (exactly_once_delivery=true)
- Signals: Exactly-once delivery required
- Criterion 1 (Eliminators): Exactly-once required → **use SNS FIFO + SQS FIFO**
- → **AWS: SNS FIFO Topic + SQS FIFO Queue (deduplication enabled)**
- Confidence: `inferred`

### Example 3: Cloud Tasks Queue (scheduled)

- GCP: `google_cloud_tasks_queue` (rate_limits=1000 msg/sec, retry_config=[max_retries=5])
- Signals: Task scheduling, retry configuration
- Criterion 1 (Eliminators): PASS
- → **AWS: SQS (standard) + Lambda ScheduledEvents (for scheduling)**
- Confidence: `inferred`

## Output Schema

```json
{
  "gcp_type": "google_pubsub_topic",
  "gcp_address": "user-events",
  "gcp_config": {
    "message_retention_duration": "604800s",
    "subscribers": 3
  },
  "aws_service": "SNS",
  "aws_config": {
    "topic_name": "user-events",
    "display_name": "User Events"
  },
  "confidence": "inferred",
  "rationale": "Pub/Sub with multiple subscribers → SNS (broadcast pattern)"
}
```
