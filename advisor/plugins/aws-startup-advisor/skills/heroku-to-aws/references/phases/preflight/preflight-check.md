---
_fragment: check
_of_phase: preflight
_contributes: preflight-report.json
---

# Preflight — Check Regional Availability and Default Quotas

> **Fragment unit.** Queries the AWS documentation-lookup capability for each
> proposed AWS service in `aws-design.json` to verify (a) the service class /
> instance type is offered in the user's selected region and (b) the resource
> count fits default account quotas. Accumulates blockers and quota-increase
> items; the assembler writes `preflight-report.json`.

**Do NOT hardcode quota numbers. Source every threshold at runtime via the
AWS documentation-lookup capability.**

---

## Step 1: Load inputs

1. Read `$MIGRATION_DIR/aws-design.json`. Extract `services[]` — the list of
   proposed AWS services. Each entry has at minimum `aws_service` and
   `aws_config`.
2. Read `$MIGRATION_DIR/preferences.json`. Extract `region` (default
   `us-east-1` if absent).

---

## Step 2: For each service, check regional availability

For each entry in `aws-design.json services[]`:

1. Identify the **service class / instance type** from `aws_config`:
   - RDS / Aurora: `instance_class` (e.g., `db.t4g.micro`)
   - ElastiCache: `node_type` (e.g., `cache.t4g.micro`)
   - Elastic Beanstalk: `instance_type` (e.g., `t3.micro`)
   - Fargate: no instance check needed — Fargate is region-level availability
   - MSK: `broker_instance_type` (e.g., `kafka.m5.large`)
   - Any other service: use the primary sizing field in `aws_config`
2. Use the **AWS documentation-lookup capability** to verify the instance
   class / instance type is offered in `preferences.region`. Phrase the query
   as: "Is `<instance_type>` available in `<region>` for `<aws_service>`?"
3. If the documentation confirms unavailability, append a blocker:

   ```json
   {
     "service_id": "<aws_config.service_id or aws_service>",
     "aws_service": "<aws_service>",
     "issue": "instance_not_in_region",
     "detail": "<instance_type> is not offered in <region>",
     "remediation": "Choose a supported instance type for <region>, or change region in the what-if workshop."
   }
   ```

4. If availability cannot be determined (documentation-lookup returns
   inconclusive), append a quota item flagged as `"needs_manual_check": true`
   rather than a hard blocker.

---

## Step 3: For each service, check default account quotas

For each entry in `aws-design.json services[]`:

1. Identify the relevant **resource count** from `aws_config`:
   - RDS: number of DB instances (count `1` unless `aws_config.multi_az` → 1
     primary + 1 standby → `2` instances toward the DB instances quota)
   - ElastiCache: number of nodes; number of clusters
   - Elastic Beanstalk: number of environments
   - Fargate: number of tasks (if specified in `aws_config`, otherwise skip
     the count check — task count is dynamic)
   - MSK: number of brokers
2. Use the **AWS documentation-lookup capability** to retrieve the **default
   account quota** for the resource type in the target region. Phrase the
   query as: "What is the default service quota for `<resource type>` in AWS
   `<aws_service>` in region `<region>`?"
3. Compare the designed count to the default quota:
   - If designed count **exceeds** the default quota, append a blocker:

     ```json
     {
       "service_id": "<service_id>",
       "aws_service": "<aws_service>",
       "issue": "quota_exceeded",
       "detail": "Designed count <N> exceeds the default quota of <Q> for <resource_type> in <region>.",
       "remediation": "Request a quota increase via the AWS Service Quotas console before deployment.",
       "quota_source": "<URL or doc reference returned by documentation-lookup>"
     }
     ```

   - If designed count is **within 80% of** the default quota (a warn
     threshold), append a quota item:

     ```json
     {
       "service_id": "<service_id>",
       "aws_service": "<aws_service>",
       "issue": "quota_near_limit",
       "detail": "Designed count <N> is within 80% of the default quota <Q> for <resource_type> in <region>.",
       "remediation": "Monitor usage and consider a preemptive quota increase.",
       "quota_source": "<URL or doc reference>"
     }
     ```

   - If the quota cannot be determined, append as `"needs_manual_check": true`
     quota item.

---

## Step 4: Accumulate results

Maintain two lists as you iterate the services:

- `blockers[]` — hard stops (instance not in region, quota exceeded)
- `quota_items[]` — advisory items (near-limit, needs manual check)

After iterating all services, derive the roll-up `status`:

- `"blocked"` — if `blockers[]` is non-empty
- `"warn"` — if `blockers[]` is empty and `quota_items[]` is non-empty
- `"pass"` — if both lists are empty

Pass these three values (`blockers`, `quota_items`, `status`) to the
assembler (`preflight-assemble.md`).
