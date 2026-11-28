# Method A and Method B on NexStock (Issue #19)

Both suites cover the Authentication, Categories, Products and Inventory tags of NexStock commit `616e053ebda66294f5d3532dae4b3d752acc6cb0`. Both use `claude-opus-5-5` with medium effort. The fault runs use the six seeded faults F01–F06 and reset seed data.

- **Method A** writes Pytest files directly: suite `20261128-014844`. Raw fault results: [method-a-fault-results.json](method-a-fault-results.json).
- **Method B** writes structured test definitions: suite `20261116-232058`. Raw fault results: [nexstock-fault-evaluation.json](nexstock-fault-evaluation.json).

## Metrics (section 3.5.2)

| Metric | Method A (Pytest) | Method B (definitions) |
|---|---|---|
| Tests saved | 164 in 4 files | 118 (2 of 120 rejected before saving) |
| Executable-test rate (runs correctly without manual fixes) | 157/164 (96%) | 118/120 (98%) |
| Generated-test errors at run time | 7 | 0 |
| Fault-detection rate | 4/6 (F01, F02, F03, F05) | 3/6 (F01, F02, F03) |
| False positives | 0 | 0 |
| Generation time | 164.9 s | 140.9 s |
| AI usage | 4 calls, 5,029 input and 23,354 output tokens, about $0.49 | 4 calls, 5,001 input and 19,169 output tokens, about $0.41 |
| Run time on NexStock | about 38 s | about 30 s (`apiguard run`), 6 s (`--docker`) |
| Failures on the original app | 29 (22 app defects, 7 test errors) | 14 (all app defects) |

Test stability over ten runs is #38.

## Findings

- Method A found F05 (the ignored category filter), because one test reads the response and checks each product's category. Method B cannot do this: a definition checks only the status code and the schema.
- Method A wrote 7 tests that fail on the original app because of their own mistakes. They read `id` or `sku` from the top of the response, but NexStock puts these values in `data`. The prompt gives no response schemas. APIGuard cannot find these mistakes before it saves the files: it checks only syntax and imports.
- Method B checks every definition against the specification before it saves it (FR-05). A failure is a structured result, so the rules in `src/apiguard/classifier.py` can classify it (FR-10). A Method A failure is often a Python exception, such as `KeyError`, which the rules cannot classify.
- Neither method found F04 (broken authorization) or F06 (deletion with no effect). Neither suite has authorization tests. The Method A deletion workflow test is one of the 7 broken tests.

## Decision

Select **Method B** for the remaining applications, and extend its definitions in #20:

- Add multi-step workflow definitions that save a response value and use it in the next step.
- Add response checks for field values, such as "each product has category_id 2".

These additions give Method B the checks that found F05 with Method A, and keep validation before saving and rule-based classification. The team can change this decision at the next meeting. If it does, record the new decision in `docs/PROJECT_CONTEXT.md`.
