import subprocess
import sys


def test_version_command():
    result = subprocess.run(
        [sys.executable, "-m", "apiguard.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0"
