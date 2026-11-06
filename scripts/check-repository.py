"""Reject ignored runtime/dependency files accidentally added to the Git index."""
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--ignored", "--exclude-standard"],
        cwd=root, stdout=subprocess.PIPE, check=True,
    )
    paths = [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]
    if paths:
        print("Ignored files are still tracked by Git; untrack them without deleting local data:", file=sys.stderr)
        for path in paths:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("Repository check passed: no ignored files are tracked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
