# APIGuard and Schemathesis on NexStock (Issue #27)

Run on 2026-11-28 with `python scripts/evaluate_faults.py`. The raw result is in
[nexstock-fault-evaluation.json](nexstock-fault-evaluation.json).

## Conditions

- NexStock commit `616e053ebda66294f5d3532dae4b3d752acc6cb0`, original app and the six seeded faults F01–F06.
- Each run starts from the same seed data.
- APIGuard: suite `20261116-232058` (Method B, structured definitions), 118 tests, no AI model at run time.
- Schemathesis: the baseline in `configs/nexstock.yaml` (25 examples, seed 4907), on the same operation tags.
- A fault is detected when a tool reports a new failure on the operation that the fault changes, compared with the original app.

## Fault detection

| Fault | Type | APIGuard | Schemathesis |
|---|---|---|---|
| F01 | Unauthorized access | Detected | Missed |
| F02 | Wrong status code | Detected | Detected |
| F03 | Input validation removed | Detected | Missed |
| F04 | Broken authorization | Missed | Missed |
| F05 | Business logic | Missed | Missed |
| F06 | Stateful workflow | Missed | Missed |

## Metrics (section 3.5.2)

| Metric | APIGuard | Schemathesis |
|---|---|---|
| Fault-detection rate | 3/6 (50%) | 1/6 (17%) |
| False positives (new failures on other operations) | 0 | 1 (F02: `Stateful tests`) |
| Operations that fail on the original app | 6 | 16 |
| Endpoint coverage | 17 of 28 operations (61%); all operations of the selected tags | 17 operations and the stateful group |
| Executable-test rate | 118 of 120 generated tests (98%) | Not applicable |
| Generation time | 140.9 s, one time | None |
| Execution time for each run | 27.7–32.0 s | 4.7–5.3 s |
| AI usage | 4 calls, 5,001 input and 19,169 output tokens, about $0.41, one time | None |
| Test stability | Not measured here; see #38 | Not measured here |
| Setup effort | Not measured here; see #40 | Not measured here |

The six operations that fail on the original app are known NexStock v1 defects, such as HTTP 500 for every authenticated `GET /api/inventory` and `GET /api/auth/me` request.

## Findings

- APIGuard finds the faults that its test types cover: authentication (F01), status codes (F02) and input validation (F03).
- Both tools miss F04, F05 and F06. The suite has no authorization, business-logic or stateful workflow tests. #20 adds these test types.
- Schemathesis reports more failures on the original app. Most are undocumented status codes and content types, not seeded faults.
- APIGuard runs are about six times slower, because the app is reset before each change-making test.

## Number of faults for the other apps

Proposal for the team to approve: use six faults for each app, one for each fault type in section 3.5.3. This is the NexStock set. It lets us compare the apps directly.

## Open items

- #19: compare Method A and Method B, then run this comparison again with the selected method.
- #20: add the missing test types, then run this comparison again.

## Second run with all test types (Issue #20)

Suite `20261128-020639` (Method B) has all seven test types, response value checks and multi-step workflows. Its NexStock coverage table has no empty applicable cells. Raw result: [nexstock-fault-evaluation-all-types.json](nexstock-fault-evaluation-all-types.json).

| Fault | Type | APIGuard | Schemathesis |
|---|---|---|---|
| F01 | Unauthorized access | Detected | Missed |
| F02 | Wrong status code | Detected | Detected |
| F03 | Input validation removed | Detected | Missed |
| F04 | Broken authorization | Detected | Missed |
| F05 | Business logic | Detected | Missed |
| F06 | Stateful workflow | Detected | Missed |

- Fault-detection rate: APIGuard 6/6, Schemathesis 1/6. APIGuard had no false positives.
- 171 tests; 152 pass on the original app. The 19 failures are known NexStock v1 defects (HTTP 500).
- Generation: 7 model calls (4 groups and 3 requests for missing cells), 12,003 input and 29,677 output tokens, about $0.66, 220 s.
