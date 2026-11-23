def changed_outcomes(first_run, second_run):
    """Compare two complete runs of the same suite under the same conditions."""
    first = {test["id"]: test["outcome"] for test in first_run}
    second = {test["id"]: test["outcome"] for test in second_run}

    if first.keys() != second.keys():
        raise ValueError("The two runs contain different tests.")

    return sorted(test_id for test_id in first if first[test_id] != second[test_id])
