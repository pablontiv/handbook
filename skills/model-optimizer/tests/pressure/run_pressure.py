from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skill", type=Path)
    args = parser.parse_args()

    command = os.environ.get("MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON")
    if not command:
        raise SystemExit("MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON is required")
    base = json.loads(command)
    if not isinstance(base, list) or not base or not all(isinstance(v, str) for v in base):
        raise SystemExit("MODEL_OPTIMIZER_PRESSURE_COMMAND_JSON must be a non-empty JSON string array")
    payload = json.loads(args.scenarios.read_text(encoding="utf-8"))

    with args.output.open("w", encoding="utf-8") as stream:
        for scenario in payload["scenarios"]:
            argv = [*base]
            if args.skill:
                argv.extend(["--skill", str(args.skill)])
            argv.append(scenario["prompt"])
            result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
            record = {
                "scenario": scenario["id"],
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
