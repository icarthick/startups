#!/usr/bin/env node
/**
 * Local harness for the plugin telemetry endpoint.
 *
 * Runs BLEND's REAL PutPluginTelemetryEvent Lambda handler over localhost HTTP:
 * API Gateway event -> SSDK deserialization -> Smithy validation -> the handler's
 * own feature gate / future-timestamp check / metricType derivation -> response.
 *
 * The only thing stubbed is the SNS client, so no AWS account, credentials,
 * topic, or deployed stack is needed. What *would* have been published is
 * printed instead, including the metricType message attribute -- which is the
 * field a real consumer's subscription filter matches on.
 *
 * This lives outside every Brazil package on purpose: it is a development
 * harness and must never end up in a CR.
 *
 *   node local-harness/server.js [port]
 *   POST http://127.0.0.1:4010/v1/plugin-telemetry-event
 */
const http = require("node:http");
const path = require("node:path");
const { AsyncLocalStorage } = require("node:async_hooks");

/** Per-request collector for stubbed SNS publishes. */
const requestScope = new AsyncLocalStorage();

const PORT = Number(process.argv[2] ?? 4010);

/**
 * The built IDE-extension API package, whose real handler this harness loads.
 *
 * Overridable because the harness now lives in the plugin repository while the
 * package it loads lives in a Brazil workspace, so the relative default only
 * resolves when running from inside that workspace. Set IDE_EXT_API_PKG to the
 * package directory when running from anywhere else.
 */
const API_PKG =
  process.env.IDE_EXT_API_PKG ??
  path.join(__dirname, "..", "src", "SawsStartupsAdvisor-IDEExtensionApi");

// The handler reads both of these at module load.
process.env.PLUGIN_TELEMETRY_ENABLED = "true";
process.env.PLUGIN_TELEMETRY_TOPIC_ARN =
  process.env.PLUGIN_TELEMETRY_TOPIC_ARN ?? "arn:aws:sns:us-east-1:000000000000:local-harness-topic";
process.env.AWS_REGION = process.env.AWS_REGION ?? "us-east-1";

// Stub SNS BEFORE requiring the handler. The handler imports this exact object
// and hands it to the publisher, so mutating `send` here is what the publisher
// ends up calling. Nothing leaves the machine.
//
// Publishes are collected into per-request storage rather than one shared array.
// Concurrent requests interleave across the handler's `await`, so attributing
// them by index into a shared array reports one request's message against
// another's — which silently corrupts the published=yes/no signal that is the
// only reliable success oracle here.
let published = 0;
const snsModule = require(path.join(API_PKG, "dist/clients/sns.js"));
snsModule.snsClient.send = async (command) => {
  requestScope.getStore()?.push(command.input);
  return { MessageId: "local-harness-" + ++published };
};

const { lambdaHandler } = require(path.join(API_PKG, "dist/handlers/put-plugin-telemetry-event-handler.js"));

/** Build the API Gateway proxy event shape the handler's wrapper expects. */
const toApiGatewayEvent = (req, body) => ({
  resource: "/v1/plugin-telemetry-event",
  path: req.url.split("?")[0],
  httpMethod: req.method,
  headers: Object.fromEntries(Object.entries(req.headers).map(([k, v]) => [k, Array.isArray(v) ? v.join(",") : v])),
  multiValueHeaders: {},
  queryStringParameters: null,
  multiValueQueryStringParameters: null,
  pathParameters: null,
  stageVariables: null,
  requestContext: {
    requestId: "local-" + Date.now(),
    resourcePath: "/v1/plugin-telemetry-event",
    httpMethod: req.method,
    path: req.url.split("?")[0],
    stage: "local",
    identity: { sourceIp: "127.0.0.1", userAgent: req.headers["user-agent"] ?? "local-harness" },
  },
  body,
  isBase64Encoded: false,
});

const server = http.createServer((req, res) => {
  const chunks = [];
  req.on("data", (c) => chunks.push(c));
  req.on("end", () => {
    const body = Buffer.concat(chunks).toString("utf8") || null;
    const emitted = [];

    // Run the whole request inside its own scope so the SNS stub collects into
    // `emitted` no matter how many other requests are in flight.
    requestScope.run(emitted, async () => {
      let result;
      try {
        result = await lambdaHandler(toApiGatewayEvent(req, body), {}, () => undefined);
      } catch (err) {
        // A throw here is a harness fault, not a handler outcome — surface it.
        console.error("harness error:", err);
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ message: "harness error", error: String(err) }));
        return;
      }

      const metricType = emitted[0]?.MessageAttributes?.metricType?.StringValue;

      // Emitted as ONE write so concurrent requests cannot interleave halfway
      // through a record. `published=no` on a 200 is the silent-drop case worth
      // watching for: accepted, but nothing sent downstream.
      const detail = emitted.length
        ? `\n  message: ${emitted[0].Message}`
        : result.statusCode >= 400
          ? `\n  rejected: ${result.body}`
          : "";

      process.stdout.write(
        [
          new Date().toISOString(),
          `${req.method} ${req.url}`,
          `-> ${result.statusCode}`,
          `published=${emitted.length ? "yes" : "no"}`,
          metricType ? `metricType=${metricType}` : "",
        ]
          .filter(Boolean)
          .join("  ") + `${detail}\n`,
      );

      res.writeHead(result.statusCode, result.headers ?? { "content-type": "application/json" });
      res.end(result.body ?? "");
    });
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`plugin-telemetry harness on http://127.0.0.1:${PORT}/v1/plugin-telemetry-event`);
  console.log("SNS is stubbed — nothing leaves this machine. Ctrl-C to stop.\n");
});
