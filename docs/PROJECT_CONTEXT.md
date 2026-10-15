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
- Which AI model and provider should be used?
- How will logs be collected and standardized across different FastAPI applications?

## Design Decision Log

Record important decisions here as they are made. Each entry should include the date, the selected approach, the alternatives considered and the reason for the decision.

| Date | Decision | Alternatives Considered | Reason |
|---|---|---|---|
| TBD | TBD | TBD | TBD |
