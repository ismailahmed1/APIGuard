import argparse
import re
import sys
from pathlib import Path

import httpx

from apiguard import __version__
from apiguard.config import ConfigError, load_config
from apiguard.openapi import SpecError, get_response, load_spec


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate and run reusable API tests.")
    parser.add_argument("--version", action="version", version=__version__)

    commands = parser.add_subparsers(dest="command", required=True)

    check_parser = commands.add_parser(
        "check",
        help="Check configuration, connectivity and the OpenAPI specification.",
    )
    check_parser.add_argument("app", help="Application name, such as nexstock.")

    for command in ("generate", "run", "report"):
        command_parser = commands.add_parser(
            command,
            help="Not implemented yet.",
        )
        command_parser.add_argument("app")

    args = parser.parse_args(argv)

    if args.command != "check":
        print(f"Error: '{args.command}' is not implemented yet.", file=sys.stderr)
        return 2

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.app):
        print("Error: invalid application name.", file=sys.stderr)
        return 2

    config_path = Path("configs") / f"{args.app}.yaml"

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    location = config["spec_location"]
    timeout = config["timeouts"]["request_seconds"]

    try:
        load_spec(location, timeout)
        # A remote spec already proves connectivity; local files do not.
        if "://" not in location:
            get_response(config["base_url"], timeout)
    except SpecError as exc:
        print(f"Specification error: {exc}", file=sys.stderr)
        return 2
    except httpx.TimeoutException:
        print("Connection error: the request timed out.", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as exc:
        print(
            f"Connection error: server returned HTTP {exc.response.status_code}.",
            file=sys.stderr,
        )
        return 1
    except httpx.RequestError:
        print(
            "Connection error: could not reach the application. "
            "Check that it is running and the configured address is correct.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {config['name']} is reachable and its OpenAPI specification is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
