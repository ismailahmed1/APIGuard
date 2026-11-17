from apiguard.baseline import _redact, compare_baselines, parse_junit

# Shaped like a Schemathesis 4 JUnit report.
REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="schemathesis">
<testcase name="POST /api/categories">
<failure type="failure" message="ST103">1. Test Case ID: rZdAMF

- ST103 Undocumented status code

    Received: 400
    Documented: 201, 422
</failure>
<failure type="failure" message="ST205">1. Test Case ID: teFuLx

- ST205 Allow header mismatch

    `Allow: GET` does not match the schema.
</failure>
</testcase>
<testcase name="GET /api/products"/>
</testsuite></testsuites>
"""


def test_parse_junit_keeps_received_status(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(REPORT)
    assert parse_junit(path) == {
        "POST /api/categories": [
            "ST103 Undocumented status code (received 400)",
            "ST205 Allow header mismatch",
        ],
        "GET /api/products": [],
    }


def test_compare_finds_new_findings_only():
    base = {"failures": {"POST /api/categories": ["ST103 Undocumented status code (received 400)"]}}
    run = {
        "failures": {
            "POST /api/categories": [
                "ST103 Undocumented status code (received 200)",
                "ST103 Undocumented status code (received 400)",
            ],
            "GET /api/products": [],
        }
    }
    assert compare_baselines(base, run) == [
        ("POST /api/categories", "ST103 Undocumented status code (received 200)")
    ]


def test_redact_removes_tokens():
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln"
    assert _redact(f"Authorization: Bearer {token} other eyJa.eyJb.c", token) == (
        "Authorization: Bearer [REDACTED] other [REDACTED-TOKEN]"
    )
