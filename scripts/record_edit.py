"""CLI used by .github/workflows/edit.yml after a successful edit run.
Appends the edit instruction to data/edit_log.jsonl so future generations can
learn from past edit patterns."""

import argparse
from lib.preferences import record_edit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", required=True)
    parser.add_argument("--instruction", required=True)
    args = parser.parse_args()
    record_edit(args.format, args.instruction)
    print(f"Recorded edit for format={args.format!r}: {args.instruction!r}")


if __name__ == "__main__":
    main()
