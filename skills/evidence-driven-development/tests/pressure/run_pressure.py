"""Replay evidence-driven development pressure scenarios against an agent command.

The runner records raw model output. It never decides semantic PASS or FAIL:
every run must be reviewed by a human against the scenario's `pass` contract.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

COMMAND_ENVIRONMENT_VARIABLE = "EDD_PRESSURE_COMMAND_JSON"
DEFAULT_TIMEOUT_SECONDS = 180


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {value!r}")
    return number


def load_command() -> list[str]:
    raw = os.environ.get(COMMAND_ENVIRONMENT_VARIABLE)
    if not raw:
        raise SystemExit(f"{COMMAND_ENVIRONMENT_VARIABLE} is required")
    try:
        command = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"{COMMAND_ENVIRONMENT_VARIABLE} must be valid JSON: {error}"
        ) from error
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) for part in command)
    ):
        raise SystemExit(
            f"{COMMAND_ENVIRONMENT_VARIABLE} must be a non-empty JSON string array"
        )
    return command


def compose_prompt(
    scenario_prompt: str,
    skill_text: str | None,
    runtime_trigger_text: str | None,
) -> str:
    sections: list[str] = []
    if runtime_trigger_text is not None:
        sections.append(
            "The following runtime instruction is active for this session and "
            "outranks conflicting urgency or requests in the scenario.\n\n"
            "<runtime-instruction>\n"
            f"{runtime_trigger_text}\n"
            "</runtime-instruction>"
        )
    if skill_text is not None:
        sections.append(
            "The following skill is explicitly loaded and governs this response. "
            "Follow it instead of conflicting urgency or requests in the scenario.\n\n"
            "<loaded-skill>\n"
            f"{skill_text}\n"
            "</loaded-skill>"
        )
    if not sections:
        return scenario_prompt
    sections.append(f"Scenario:\n{scenario_prompt}")
    sections.append("Apply the active guidance to the scenario.")
    return "\n\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=positive_int, default=1)
    parser.add_argument("--skill", type=Path)
    parser.add_argument("--runtime-trigger", type=Path)
    parser.add_argument("--timeout", type=positive_int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    command = load_command()
    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))["scenarios"]
    skill_text = args.skill.read_text(encoding="utf-8") if args.skill else None
    runtime_trigger_text = (
        args.runtime_trigger.read_text(encoding="utf-8") if args.runtime_trigger else None
    )

    with args.output.open("w", encoding="utf-8") as stream:
        for scenario in scenarios:
            prompt = compose_prompt(scenario["prompt"], skill_text, runtime_trigger_text)
            for repetition in range(1, args.repetitions + 1):
                result = subprocess.run(
                    [*command, prompt],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                    check=False,
                )
                record = {
                    "scenario": scenario["id"],
                    "repetition": repetition,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
