from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("success", "nonzero", "timeout", "no-output"), required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--stdout-bytes", type=int, default=0)
    parser.add_argument("--stderr-bytes", type=int, default=0)
    args = parser.parse_args()

    if args.stdout_bytes:
        sys.stdout.write("O" * args.stdout_bytes)
        sys.stdout.flush()
    if args.stderr_bytes:
        sys.stderr.write("E" * args.stderr_bytes)
        sys.stderr.flush()

    if args.mode == "timeout":
        time.sleep(args.sleep)
        return 0
    if args.mode == "nonzero":
        return 7
    if args.mode == "no-output":
        return 0
    if args.input is None:
        raise SystemExit("--input is required for success mode")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
