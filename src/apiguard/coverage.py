"""Find the test types that apply to each operation, and the applicable cells with no test (FR-04)."""

from apiguard.validator import MUTATING_METHODS, TEST_TYPES

CONSTRAINTS = (
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
    "enum",
)


def applicable_types(operation, permissions, roles):
    """The test types that apply to one operation.

    `permissions` maps "METHOD /path" to the roles that may call it. An operation that some
    configured roles may not call needs an authorization test.
    """
    key = f"{operation.method} {operation.path}"
    inputs = bool(operation.parameters) or operation.request_body is not None
    types = {"happy_path"}
    if operation.requires_auth:
        types.add("authentication")
        allowed = permissions.get(key)
        if allowed is not None and set(roles) - set(allowed):
            types.add("authorization")
    if inputs:
        types.update({"schema_validation", "fuzz"})
    if _has_constraints(operation):
        types.add("boundary_value")
    # A change by a logged-in user can be read back; a login has no state to check.
    if operation.method in MUTATING_METHODS and operation.requires_auth:
        types.add("stateful_workflow")
    return types


def coverage(tests, operations, permissions, roles):
    """Return {operation key: {test type: number of tests, or None when not applicable}}."""
    counts = {}
    for test in tests:
        key = f"{test['method']} {test['path']}"
        counts.setdefault(key, {}).setdefault(test["type"], 0)
        counts[key][test["type"]] += 1
    table = {}
    for operation in operations:
        key = f"{operation.method} {operation.path}"
        types = applicable_types(operation, permissions, roles)
        table[key] = {t: counts.get(key, {}).get(t, 0) if t in types else None for t in TEST_TYPES}
    return table


def missing_cells(table):
    """The (operation, test type) pairs that apply and have no test."""
    return [(key, t) for key, row in table.items() for t, count in row.items() if count == 0]


def format_coverage(table):
    """Plain-text coverage table: a number of tests, '-' if not applicable, 'MISSING' if empty."""
    from apiguard.reporting import table as text_table

    short = {
        "happy_path": "happy",
        "schema_validation": "schema",
        "authentication": "authn",
        "authorization": "authz",
        "boundary_value": "boundary",
        "fuzz": "fuzz",
        "stateful_workflow": "workflow",
    }
    rows = [("OPERATION", *(short[t] for t in TEST_TYPES))]
    for key, row in table.items():
        rows.append((key, *("-" if row[t] is None else row[t] or "MISSING" for t in TEST_TYPES)))
    missing = missing_cells(table)
    lines = text_table(rows)
    lines.append("")
    lines.append(f"{len(missing)} applicable cells have no test.")
    return "\n".join(lines)


def _has_constraints(operation):
    schemas = [p.schema for p in operation.parameters]
    if operation.request_body:
        schemas += list(operation.request_body.content.values())
    return any(_constrained(schema) for schema in schemas)


def _constrained(schema):
    if isinstance(schema, dict):
        if any(key in schema for key in CONSTRAINTS):
            return True
        return any(_constrained(value) for value in schema.values())
    if isinstance(schema, list):
        return any(_constrained(value) for value in schema)
    return False
