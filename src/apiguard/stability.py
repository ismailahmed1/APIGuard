def changed_outcomes(first_run, second_run):
    """Compare two complete runs of the same suite under the same conditions."""
    first = {test["id"]: test["outcome"] for test in first_run}
    second = {test["id"]: test["outcome"] for test in second_run}

    if first.keys() != second.keys():
        raise ValueError("The two runs contain different tests.")

    return sorted(test_id for test_id in first if first[test_id] != second[test_id])


def flaky_tests(runs):
    """Return the IDs of tests whose outcome is not the same in every run."""
    flaky = set()
    for other in runs[1:]:
        flaky.update(changed_outcomes(runs[0], other))
    return sorted(flaky)


def validation_report(metadata, excluded, runs):
    """Saved, rejected and flaky tests of a suite after repeated runs (FR-05, NFR-01)."""
    flaky = flaky_tests(runs) if len(runs) > 1 else []
    outcomes = {}
    for results in runs:
        for result in results:
            outcomes.setdefault(result["id"], []).append(result["outcome"])
    return {
        "suite_id": metadata["suite_id"],
        "runs": len(runs),
        "saved": sorted(outcomes),
        "rejected": [{"id": _test_id(item), "reason": item["reason"]} for item in excluded],
        "flaky": [{"id": test_id, "outcomes": outcomes[test_id]} for test_id in flaky],
    }


def _test_id(item):
    test = item.get("test")
    return test.get("id") if isinstance(test, dict) else None
