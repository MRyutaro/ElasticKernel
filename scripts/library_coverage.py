#!/usr/bin/env python3
"""Generate the library checkpoint-coverage table and sync it into the READMEs (issue #48).

For every specimen in ``tests/library_specimens.py`` this runs the
``record_event -> checkpoint -> load_checkpoint`` round trip in a **separate
subprocess** (so a crash in one library -- e.g. a native segfault -- cannot take the
whole run down) and classifies the result as Migrated / Recomputed / Failed. It then:

- prints the Markdown table to stdout,
- appends it to ``$GITHUB_STEP_SUMMARY`` when running in GitHub Actions,
- and rewrites the table between the coverage markers in ``README.md`` / ``README.ja.md``.

Usage::

    python scripts/library_coverage.py            # run + update the READMEs in place
    python scripts/library_coverage.py --check     # run + fail (exit 1) if a README is stale

``--check`` is the CI drift gate: it never writes, and exits non-zero when the committed
table no longer matches a fresh run (e.g. a dependency bump changed a verified version,
or a library regressed from Migrated to Recomputed/Failed).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from importlib import metadata

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.library_specimens import SPECIMENS  # noqa: E402

BEGIN_MARKER = "<!-- BEGIN LIBRARY COVERAGE -->"
END_MARKER = "<!-- END LIBRARY COVERAGE -->"

# Per-path cell symbols. "unserializable" only happens for the Migrate path: the object
# cannot be serialized, so ElasticKernel restores it by recomputing instead.
_MIGRATE_SYMBOL = {
    "ok": "✅",
    "unserializable": "➖",
    "wrong": "❌",
    "error": "❌",
    "skipped": "⚠️",
}
_RECOMPUTE_SYMBOL = {
    "ok": "✅",
    "wrong": "❌",
    "error": "❌",
    "skipped": "⚠️",
}


def _version(pip_name: str) -> str:
    try:
        return metadata.version(pip_name)
    except metadata.PackageNotFoundError:
        return "—"


def _classify(spec, workdir: str) -> dict:
    """Run one specimen in an isolated subprocess and return its result dict."""
    proc = subprocess.run(
        [sys.executable, "-m", "tests.library_specimens", spec.key, workdir],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"migrate": "error", "recompute": "error"}
    # The round trip routes library chatter to stderr, but stay defensive and take the
    # last JSON-parseable stdout line as the result.
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"migrate": "error", "recompute": "error"}


def build_table(workdir: str) -> str:
    rows = [
        "| Library | Object | Migrate | Recompute | Verified version |",
        "| --- | --- | :---: | :---: | --- |",
    ]
    prev_library = None
    for spec in SPECIMENS:
        result = _classify(spec, os.path.join(workdir, spec.key))
        migrate = _MIGRATE_SYMBOL.get(result.get("migrate"), "❓")
        recompute = _RECOMPUTE_SYMBOL.get(result.get("recompute"), "❓")
        # Show the library name only on its first row to keep the grouping readable.
        library = "" if spec.library == prev_library else spec.library
        prev_library = spec.library
        rows.append(
            f"| {library} | `{spec.object_type}` "
            f"| {migrate} | {recompute} | {_version(spec.pip_name)} |"
        )
    return "\n".join(rows)


def _splice(text: str, table: str) -> str:
    start = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER)
    return text[: start + len(BEGIN_MARKER)] + "\n" + table + "\n" + text[end:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if a README's table is out of date",
    )
    parser.add_argument(
        "--workdir",
        default=os.path.join(REPO_ROOT, ".library_coverage"),
        help="scratch directory for per-library checkpoints",
    )
    args = parser.parse_args()

    table = build_table(args.workdir)
    print(table)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## Library checkpoint coverage\n\n" + table + "\n")

    readmes = [
        os.path.join(REPO_ROOT, "README.md"),
        os.path.join(REPO_ROOT, "README.ja.md"),
    ]
    stale = []
    for path in readmes:
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
        if BEGIN_MARKER not in current or END_MARKER not in current:
            print(f"error: coverage markers not found in {path}", file=sys.stderr)
            return 2
        updated = _splice(current, table)
        if updated == current:
            continue
        if args.check:
            stale.append(path)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(updated)
            print(f"updated {os.path.basename(path)}", file=sys.stderr)

    if args.check and stale:
        names = ", ".join(os.path.basename(p) for p in stale)
        print(
            f"\nerror: {names} out of date. "
            "Run `python scripts/library_coverage.py` and commit the result.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
