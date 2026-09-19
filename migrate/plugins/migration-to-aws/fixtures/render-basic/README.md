# Fixture: render-basic

Golden fixture for the render-to-aws skill — tests the Discover → Design path for a
basic Render app with all four core service types: Web Service, Background Worker,
PostgreSQL, and Key Value (Redis).

## What it tests

- **web_service → Elastic Beanstalk** (default compute target)
- **background_worker → ECS Fargate** (always, regardless of compute_target default)
- **postgres → RDS PostgreSQL** (plan-based instance sizing)
- **key_value → ElastiCache Redis** (plan-based node sizing)
- **Render plan sizing tables** — all Fargate rows in web-service-fargate and
  worker-fargate tables have valid Fargate CPU/memory pairings per the AWS spec

## Fixture structure

```
render-basic/
├── seed/
│   ├── render-resource-inventory.json   # 4-service Render inventory from render.yaml
│   └── preferences.json                 # fast-path clarify output, us-west-2, multi-az
├── after-design/
│   └── aws-design.json                  # expected design output
├── expected-render-basic.json           # asserter spec
├── check_expected_render_basic.py       # asserter
└── README.md
```

## Running the asserter

```bash
python3 check_expected_render_basic.py path/to/.migration/run-dir
```
