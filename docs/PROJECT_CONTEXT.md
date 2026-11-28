# APIGuard Project Context

## Project Overview

APIGuard is an AI-assisted platform for API testing and security monitoring. It will use information from a FastAPI application's OpenAPI specification to generate relevant API tests. The platform will also run the tests, record and classify the results, and examine application logs for suspicious behaviour.

The AI component will help generate the tests, but the saved tests must be executable without calling the AI model again. This will make repeated test runs more consistent and reduce the cost and availability concerns of requiring the model during execution.

## Core Workflow

1. The user provides a FastAPI application, its OpenAPI specification and any required authentication information.
2. APIGuard reads the specification to identify the application's endpoints, request and response schemas, and security requirements.
3. The AI component uses this information to generate API tests.
4. APIGuard validates and saves the generated tests.
5. The platform runs the application and its tests in an isolated Docker environment.
6. Test results are recorded and classified so that the user can understand what failed.
7. The platform examines application logs using security rules and reports suspicious behaviour, such as repeated failed logins or unauthorized access attempts.

## Test Types

Where applicable, APIGuard will generate:

- **Happy-path tests:** Confirm that valid requests produce the expected responses.
- **Schema-validation tests:** Confirm that invalid or incorrectly typed request data is rejected.
- **Authentication tests:** Confirm that protected endpoints reject unauthenticated requests.
- **Authorization tests:** Confirm that authenticated users cannot access operations or resources outside their permissions.
- **Boundary-value tests:** Test values at or near accepted limits.
- **Fuzz and robustness tests:** Send unexpected or unusual inputs to identify crashes and other incorrect behaviour.
- **Stateful workflow tests:** Test related operations in the correct order, such as creating, updating and deleting a resource.

## Evaluation Plan

APIGuard will be evaluated on five open-source FastAPI applications containing intentionally seeded faults. Its results will be compared with Schemathesis using the same applications, faults and test conditions. Possible measures include the number of faults detected, endpoint coverage, invalid generated tests, execution time and the usefulness of failure classifications.

The first prototype will use NexStock. The team will try both direct Pytest-file generation and structured test definitions that are converted into executable tests. The results will be recorded before one approach is selected for the remaining applications.

## Open Design Questions

- Should failure classification be rule-based, AI-assisted or a combination of both?
- What application context, beyond the OpenAPI specification, is needed to classify failures accurately?
- Should APIGuard generate Pytest files directly or generate structured test definitions first?
- Which AI model and provider should be used after comparative evaluation of the prototype?
- How will logs be collected and standardized across different FastAPI applications?

## Design Decision Log

Record important decisions here as they are made. Each entry should include the date, the selected approach, the alternatives considered and the reason for the decision.

| Date | Decision | Alternatives Considered | Reason |
|---|---|---|---|
| 2026-11-28 | Turn off the FastAPI Banking System rate limits in the APIGuard container (Issue #28). Seed two local test users, because the app does not create its admin user. | Keep the limits and slow down the test runs. | Login allows five requests each minute. Test results would then depend on timing (NFR-01). |
| 2026-11-27 | Record the tested application's pinned upstream SHA through optional `app_commit` configuration in each `run.json` (Issue #14); use `null` when unavailable. Keep this value synchronized with the integration's Dockerfile or submodule pin. Retain `spec_sha256` and `suite_id` from saved suite metadata. Seed recording is out of scope. | Infer the commit from APIGuard's Git checkout or parse integration-specific build files during every run. | APIGuard's commit does not identify the tested application. Explicit configuration works across Docker and submodule integrations without guessing when upstream information is unavailable. |
| 2026-11-24 | Use F06 for product deletion that reports success while leaving the product available. Preserve authentication and missing-product checks. | Stock-out accepting insufficient stock | Evaluate stateful workflow checks that verify persisted state after a successful response. |
| 2026-11-25 | Retain Anthropic/Claude for the prototype, with `claude-opus-5-5` and medium effort as configured in `configs/nexstock.yaml` (Issue #10). | Other Claude models, other hosted providers, or a locally hosted model. | The existing Anthropic adapter already supports streamed responses, JSON-schema output, prompt caching and usage accounting needed by the structured-definition prototype. Keeping it avoids another integration while evaluating test generation. This is a practical prototype choice, not evidence that this model is best; no comparative model benchmarks establish that here. |

### AI usage limits and records (Issue #10)

`AIClient` checks cumulative usage before each generation request. NexStock currently sets
`max_calls: 10`, `max_output_tokens: 150000` and `max_cost_usd: 5.00`. Once a recorded
value reaches its threshold, the next generation request is blocked. The generator then
validates and saves the tests already returned, including valid tests from the response
that reached or exceeded a threshold, and records `stopped_reason` in `suite.json`.

These are checks between requests. An in-flight request is not interrupted, and its output
tokens or estimated cost can exceed the remaining allowance. The request's `max_tokens`
is a separate per-response limit; it is not reduced to the remaining cumulative allowance.
The estimated spending threshold is therefore not a guaranteed hard cap.

Each saved `suite.json` contains `generation_seconds` for the generation loop and `ai_usage`
with calls, input/output tokens, cache-write/read tokens, request time (`seconds`) and
estimated `cost_usd`. Cost uses the local per-model price table and includes cache usage;
it is not a billing record. Calls and tokens are recorded for completed responses, including
unusable answers. SDK retries, server-side fallback attempts and requests that fail without
returning usage are not separately accounted for. Fallback billing may differ from the
configured model's estimate. For models absent from the price table, cost is `null` and the
cost threshold cannot be enforced; support for enforcing it on unpriced models remains open.

Generation tests inject `FakeAnthropic`, remove AI credentials and reject construction of
the real SDK client. They verify all three limits preserve saved valid tests, including
token/cost overshoot, and verify saved usage and timing without making model calls.
