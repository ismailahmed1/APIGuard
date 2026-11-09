import argparse
import re
import sys
from pathlib import Path

import httpx

from apiguard import __version__
from apiguard.config import ConfigError, load_config


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate and run reusable API tests.")
    parser.add_argument("--version", action="version", version=__version__)

    commands = parser.add_subparsers(dest="command", required=True)

    check_parser = commands.add_parser(
        "check",
        help="Check configuration and application connectivity.",
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

    # Check the specification URL when one is configured.
    # For a local specification file, check the application base URL instead.
    location = config["spec_location"]
    url = location if "://" in location else config["base_url"]

    try:
        response = httpx.get(
            url,
            timeout=config["timeouts"]["request_seconds"],
            follow_redirects=True,
        )
        response.raise_for_status()
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

    print(f"OK: {config['name']} is reachable (HTTP {response.status_code}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
