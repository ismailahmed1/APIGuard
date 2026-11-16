"""Build one internal model of the operations in a validated OpenAPI 3.x document.

The generator, validator and metrics all read this model instead of the raw document.
Local `$ref` references are resolved, so callers never follow references themselves.
"""

from dataclasses import dataclass
from urllib.parse import unquote

from apiguard.openapi import SpecError

# OpenAPI 3.2 adds the QUERY method; earlier versions simply never use the key.
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace", "query")


@dataclass(frozen=True)
class Parameter:
    name: str
    location: str  # path, query, header or cookie
    required: bool
    schema: dict | None


@dataclass(frozen=True)
class RequestBody:
    required: bool
    content: dict  # media type -> schema (None if the media type has no schema)


@dataclass(frozen=True)
class Operation:
    method: str  # upper case, such as GET
    path: str
    operation_id: str | None
    summary: str | None
    tags: tuple
    parameters: tuple  # of Parameter
    request_body: RequestBody | None
    responses: dict  # status code (string) -> {media type -> schema}
    security: tuple  # of {scheme name: [scopes]}; an empty dict allows anonymous access

    @property
    def requires_auth(self):
        """True when every security requirement names at least one scheme."""
        return bool(self.security) and all(self.security)

    @property
    def security_schemes(self):
        """Names of the schemes that can authorize this operation, in spec order."""
        names = []
        for requirement in self.security:
            for name in requirement:
                if name not in names:
                    names.append(name)
        return names


def extract_operations(document):
    """Return every operation in the document, in the order the spec lists them."""
    resolver = _Resolver(document)
    global_security = document.get("security", [])
    operations = []

    for path, raw_item in (document.get("paths") or {}).items():
        item = resolver.resolve(raw_item)
        shared_parameters = item.get("parameters", [])

        for method in HTTP_METHODS:
            # Already resolved with its path item; resolving again would expand kept references.
            operation = item.get(method)
            if operation is None:
                continue
            operations.append(
                Operation(
                    method=method.upper(),
                    path=path,
                    operation_id=operation.get("operationId"),
                    summary=operation.get("summary"),
                    tags=tuple(operation.get("tags", [])),
                    parameters=_merge_parameters(
                        shared_parameters, operation.get("parameters", [])
                    ),
                    request_body=_request_body(operation.get("requestBody")),
                    responses=_responses(operation.get("responses", {})),
                    # An operation-level list, even an empty one, replaces the global list.
                    security=tuple(operation.get("security", global_security)),
                )
            )
    return operations


def _merge_parameters(shared, own):
    """Operation parameters replace path-item parameters with the same name and location."""
    merged = {}
    for parameter in [*shared, *own]:
        merged[(parameter["name"], parameter["in"])] = Parameter(
            name=parameter["name"],
            location=parameter["in"],
            required=parameter.get("required", False),
            schema=parameter.get("schema") or _first_schema(parameter.get("content")),
        )
    return tuple(merged.values())


def _request_body(body):
    if body is None:
        return None
    return RequestBody(required=body.get("required", False), content=_media(body.get("content")))


def _responses(responses):
    return {str(status): _media(response.get("content")) for status, response in responses.items()}


def _media(content):
    return {media_type: value.get("schema") for media_type, value in (content or {}).items()}


def _first_schema(content):
    for value in (content or {}).values():
        return value.get("schema")
    return None


class _Resolver:
    """Replace local `$ref` objects with copies of their targets.

    A reference that points back into itself (a recursive schema) cannot be expanded,
    so the inner occurrence is kept as the original `{"$ref": ...}` object.
    """

    def __init__(self, document):
        self.document = document

    def resolve(self, value, active=()):
        if isinstance(value, list):
            return [self.resolve(child, active) for child in value]
        if not isinstance(value, dict):
            return value

        reference = value.get("$ref")
        if not isinstance(reference, str):
            return {key: self.resolve(child, active) for key, child in value.items()}

        if reference in active:
            return dict(value)
        target = self.resolve(self._lookup(reference), (*active, reference))
        siblings = {key: child for key, child in value.items() if key != "$ref"}
        if not siblings:
            return target
        if not isinstance(target, dict):
            raise SpecError(f"{reference}: a reference with sibling keys must point to an object.")
        # OpenAPI 3.1 allows keys such as "description" next to "$ref"; they take precedence.
        return {**target, **self.resolve(siblings, active)}

    def _lookup(self, reference):
        if not reference.startswith("#"):
            raise SpecError(f"{reference}: external references are not supported.")
        current = self.document
        fragment = unquote(reference[1:])
        for part in fragment.split("/")[1:] if fragment else []:
            part = part.replace("~1", "/").replace("~0", "~")
            try:
                current = current[int(part)] if isinstance(current, list) else current[part]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise SpecError(f"{reference}: reference target does not exist.") from exc
        return current
