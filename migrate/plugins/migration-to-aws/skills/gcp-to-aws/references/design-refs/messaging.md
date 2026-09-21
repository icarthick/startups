# Messaging Services Design Rubric

**Applies to:** Pub/Sub, Cloud Tasks, Cloud Scheduler

**Quick lookup (no rubric):** Check `fast-path.md` first (Pub/Sub → SNS/SQS, etc.)

## Eliminators (Hard Blockers)

| GCP Service     | AWS                   | Blocker                                                                                                 |
| --------------- | --------------------- | ------------------------------------------------------------------------------------------------------- |
| Pub/Sub         | SNS                   | Exactly-once delivery required → SNS FIFO + SQS FIFO (SNS FIFO supports exactly-once via deduplication) |
| Pub/Sub         | SQS                   | Multiple subscribers per topic → SNS (not SQS)                                                          |
| Cloud Tasks     | SQS                   | Scheduled/delayed task execution → EventBridge + SNS/SQS                                                |
| Cloud Scheduler | EventBridge Scheduler | HTTP target to a non-AWS endpoint with no Lambda wrapper → requires Lambda shim                         |

## Signals (Decision Criteria)

### Pub/Sub

- **Multiple subscribers, broadcast** → SNS (pub/sub pattern)
- **Single consumer, durability** → SQS (queue pattern)
- **Exactly-once delivery** → SNS FIFO + SQS FIFO (deduplication enabled)
- **Real-time, low latency** → SNS (vs SQS polling delay)

### Cloud Tasks

- **HTTP callback execution** → EventBridge + SNS/SQS (route to Lambda/Fargate)
- **Delayed/scheduled queue** → SQS + Lambda (ScheduledEvents)

### Cloud Scheduler

- **Recurring cron-based invocation** → EventBridge Scheduler (cron expression)
- **One-time scheduled invocation** → EventBridge Scheduler (at expression)
- **Rate-based invocation** → EventBridge Scheduler (rate expression)
- **HTTP target** → EventBridge Scheduler → Lambda (to proxy the HTTP call)
- **Pub/Sub target** → EventBridge Scheduler → SNS or SQS

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

## Cloud Scheduler → EventBridge Scheduler: Key Differences

| Dimension            | GCP Cloud Scheduler                              | Amazon EventBridge Scheduler                                                        |
| -------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Schedule syntax      | 5-field unix cron (`min hr dom mon dow`)         | 6-field cron (`min hr dom mon dow year`), `rate(…)`, or `at(…)` for one-time        |
| One-time schedules   | Supported (single future execution)              | Supported via `at(yyyy-mm-ddThh:mm:ss)` expression                                  |
| Recurring schedules  | Supported (cron)                                 | Supported (cron and rate expressions)                                               |
| Target types         | HTTP endpoints, Pub/Sub topics, App Engine HTTP  | 270+ AWS services via universal target (Lambda, SQS, SNS, Step Functions, and more) |
| External HTTP target | Native (direct HTTP/HTTPS call)                  | Requires a Lambda function to proxy outbound HTTP calls                             |
| Retry policy         | Configurable max retry count and min/max backoff | Configurable retry window and max event age                                         |
| Time zone            | Configurable per job                             | Configurable per schedule                                                           |

**Migration note:** Convert 5-field GCP cron expressions to 6-field AWS cron by appending a year field (use `*` for any year). Example: GCP `0 9 * * MON-FRI` → AWS `cron(0 9 ? * MON-FRI *)`. AWS cron does not allow both `day-of-month` and `day-of-week` to be specified simultaneously — use `?` for the one not being constrained.

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

### Example 4: Cloud Scheduler Job (recurring cron)

- GCP: `google_cloud_scheduler_job` (schedule="0 9 * * MON-FRI", target=http_target)
- Signals: Recurring weekday invocation, HTTP target
- Criterion 1 (Eliminators): HTTP target to external endpoint → requires Lambda proxy shim
- Criterion 2 (Operational Model): EventBridge Scheduler (managed, fully serverless)
- → **AWS: EventBridge Scheduler** (`cron(0 9 ? * MON-FRI *)`) → **Lambda** (HTTP proxy)
- Note: Convert 5-field GCP cron to 6-field AWS cron — append `*` year field; use `?` for unconstrained day field.
- Confidence: `inferred`

### Example 5: Cloud Scheduler Job (one-time)

- GCP: `google_cloud_scheduler_job` (schedule="one-time", pubsub_target)
- Signals: Single future invocation, Pub/Sub target
- Criterion 1 (Eliminators): PASS
- → **AWS: EventBridge Scheduler** (`at(yyyy-mm-ddThh:mm:ss)`) → **SNS topic**
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
