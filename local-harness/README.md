# Local telemetry harness

A localhost stand-in for BLEND's `PutPluginTelemetryEvent` endpoint, for exercising
the migration telemetry emitter without touching AWS.

It is **not a fake**. It loads the real Lambda handler and the real Smithy-generated
validation from the built `SawsStartupsAdvisor-IDEExtensionApi` package and stubs only
the SNS client, so a wrong payload shape produces a genuine `400` rather than an
invented one.

## Prerequisites

The API package must be **built**, because the harness requires its compiled output
(`dist/handlers/...`, `dist/clients/sns.js`):

```bash
cd <workspace>/src/SawsStartupsAdvisor-IDEExtensionApi
brazil-build release
```

## Running

From a Brazil workspace, the default path resolves and no configuration is needed:

```bash
node local-harness/server.js 4010
```

From this repository, point `IDE_EXT_API_PKG` at the built package:

```bash
IDE_EXT_API_PKG=$HOME/workplace/SawsAdvisorApiModel/src/SawsStartupsAdvisor-IDEExtensionApi \
  node local-harness/server.js 4010
```

Then point the emitter at it:

```bash
export AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT=http://127.0.0.1:4010/v1/plugin-telemetry-event
```

## Checking it is alive

A `400` on an empty body is the **correct** response — it means Smithy validation is
wired up:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  http://127.0.0.1:4010/v1/plugin-telemetry-event \
  -H 'content-type: application/json' -d '{}'
```

## Reading the output

**`HTTP 200` is not the success oracle.** Three separate paths return 200 while
publishing nothing at all. Assert on the harness's own `published=yes` instead — that
is the only signal that the event reached the (stubbed) topic.

The harness also reports the `metricType` message attribute it would have published
under, which is what a consumer's subscription filter matches on. An event that
publishes under the wrong attribute is dropped downstream with no error, no
dead-letter entry and no replay source, so this is worth reading on every run.

## Stopping it

Kill by **listening port**, never by name — `pkill -f "server.js 4010"` matches the
calling shell too and will kill your own terminal:

```bash
P=$(ss -ltnp | grep ':4010' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
[ -n "$P" ] && kill "$P"
```

## Do not ship this upstream

This directory is test scaffolding for a fork. It must not reach `awslabs/startups`,
and it must never be committed into a Brazil package — it is deliberately kept
outside them so it cannot be picked up by a code review.
