#!/usr/bin/env python3
"""Secret Scanner.

Scans a directory tree for secrets that should never be committed:
cloud keys, API tokens, private keys, and suspicious high-entropy
values assigned to password-like names. Built for the moment before
`git commit`, and for CI: it exits non-zero when it finds anything.

Findings never print the secret itself. The matched value is masked
in output (first and last few characters only), so the report is safe
to paste into a ticket or a build log.

Rules (all regex, plus a Shannon-entropy check for long
base64/hex-looking values assigned to a secret-like name):
  AWS access key, AWS secret key, GitHub token, GitHub PAT,
  Slack token, Stripe live/restricted key, Google API key,
  JSON web token, private key header, generic password / secret /
  token / api_key assignment with a non-trivial value.

Skipped by default: .git, __pycache__, node_modules, .venv, venv,
binary files, files over 1 MiB, and anything matching
.secretscanignore (one glob per line, same syntax as .gitignore
basics) in the scanned root. A line ending in
`# secretscan:ignore` is skipped, and `--allowlist` takes a file
of regexes (one per line) for known test fixtures and examples.

Stdlib only, no dependencies.

Usage:
  python3 secretscan.py ~/Projects/my-app
  python3 secretscan.py ~/Projects/my-app --json
  python3 secretscan.py ~/Projects/my-app --exclude "*.min.js" --exclude "tests/fixtures/*"
  python3 secretscan.py ~/Projects/my-app --allowlist allowlist.txt
  python3 secretscan.py ~/Projects/my-app --max-size 524288

Exit codes:
  0  no secrets found
  1  one or more secrets found
  2  usage error (bad path, bad allowlist file)
"""

import argparse
import fnmatch
import json
import math
import re
import sys
from pathlib import Path

# Directories never descended into.
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".eggs"}

# File extensions that are almost always generated or binary.
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".o", ".a",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
    ".tar", ".gz", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4",
}

IGNORE_FILE = ".secretscanignore"
SUPPRESS_MARKER = "secretscan:ignore"
DEFAULT_MAX_SIZE = 1024 * 1024  # 1 MiB

# (rule name, severity, compiled pattern)
RULES = [
    ("aws-access-key", "high",
     re.compile(r"\b(AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    ("aws-secret-key", "high",
     re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?")),
    ("github-token", "high",
     re.compile(r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{20,}\b")),
    ("slack-token", "high",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-key", "high",
     re.compile(r"\b(rk|sk|pk)_(live|test)_[A-Za-z0-9]{16,}\b")),
    ("google-api-key", "high",
     re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("jwt", "medium",
     re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private-key", "high",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("generic-secret-assignment", "medium",
     re.compile(
         r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|"
         r"auth[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"]?"
         r"([A-Za-z0-9!@#$%^&*_\-+=/.]{8,})['\"]?")),
]

# Assignment names whose values get an entropy check even when no
# rule above matches. A long random-looking value here is almost
# certainly a real credential, not a placeholder.
ENTROPY_NAMES = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*['\"]?"
    r"([A-Za-z0-9+/=_-]{20,})['\"]?")
ENTROPY_THRESHOLD = 4.2  # bits per character; random base64 is ~6

# Values that are obviously placeholders, not real secrets.
PLACEHOLDERS = {
    "password", "changeme", "your-password", "your_api_key",
    "xxx", "xxxx", "example", "test", "dummy", "placeholder",
    "insert-key-here", "todo", "none", "null", "undefined",
}


def shannon_entropy(text):
    """Bits of entropy per character of a string."""
    if not text:
        return 0.0
    counts = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = len(text)
    return -sum(
        (count / total) * math.log2(count / total)
        for count in counts.values()
    )


def mask(value):
    """Show only the first 3 and last 2 chars of a secret."""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 5) + value[-2:]


def is_text_file(path, max_size):
    """True if a file is small enough and looks like text."""
    try:
        if path.stat().st_size > max_size:
            return False
        with open(path, "rb") as handle:
            chunk = handle.read(8192)
        return b"\x00" not in chunk
    except OSError:
        return False


def load_globs(path):
    """Read one glob per line, ignoring blanks and # comments."""
    globs = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                globs.append(line)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    return globs


def load_allowlist(path):
    """Read one regex per line, ignoring blanks and # comments."""
    patterns = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    patterns.append(re.compile(line))
                except re.error as exc:
                    print(f"error: bad allowlist regex {line!r}: {exc}",
                          file=sys.stderr)
                    sys.exit(2)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    return patterns


def is_excluded(relative, globs):
    """True if a relative path matches any glob (also matches basenames)."""
    text = relative.as_posix()
    name = relative.name
    return any(
        fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in globs
    )


# Rules whose pattern captures the secret itself as the last group,
# so the masked display should show that group, not the whole match
# (which includes the field name and quotes).
VALUE_GROUP_RULES = {"aws-secret-key", "generic-secret-assignment"}


def scan_line(line, lineno, path, allowlist):
    """Return findings (dicts) for one line, or an empty list."""
    findings = []
    if SUPPRESS_MARKER in line:
        return findings
    for name, severity, pattern in RULES:
        match = pattern.search(line)
        if not match:
            continue
        full = match.group(0)
        value = match.group(match.lastindex) if match.lastindex else full
        # A placeholder value is documentation, not a secret.
        if value.lower().strip("'\"") in PLACEHOLDERS:
            continue
        if any(p.search(line) for p in allowlist):
            continue
        findings.append({
            "file": str(path),
            "line": lineno,
            "rule": name,
            "severity": severity,
            "match": mask(value if name in VALUE_GROUP_RULES else full),
        })
        # One finding per line keeps the report readable; the
        # highest-severity rule is listed first.
        break
    if findings:
        return findings
    entropy_match = ENTROPY_NAMES.search(line)
    if entropy_match:
        value = entropy_match.group(2)
        if (value.lower() not in PLACEHOLDERS
                and shannon_entropy(value) >= ENTROPY_THRESHOLD
                and not any(p.search(line) for p in allowlist)):
            findings.append({
                "file": str(path),
                "line": lineno,
                "rule": "high-entropy-secret",
                "severity": "medium",
                "match": mask(value),
            })
    return findings


def scan(root, exclude_globs, allowlist, max_size):
    """Walk root and return (findings, files_scanned, files_skipped)."""
    findings = []
    scanned = 0
    skipped = 0
    ignore_path = root / IGNORE_FILE
    if ignore_path.is_file():
        exclude_globs = exclude_globs + load_globs(ignore_path)
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts[len(root.parts):-1]):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if (path.suffix.lower() in SKIP_EXTENSIONS
                or is_excluded(relative, exclude_globs)):
            skipped += 1
            continue
        if not is_text_file(path, max_size):
            skipped += 1
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            findings.extend(scan_line(line.rstrip("\n"), lineno, relative, allowlist))
    return findings, scanned, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan a directory tree for committed secrets.")
    parser.add_argument("path", type=Path, help="directory to scan")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="GLOB", help="skip paths matching a glob (repeatable)")
    parser.add_argument("--allowlist", type=Path, metavar="FILE",
                        help="file of regexes (one per line) to ignore")
    parser.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE,
                        metavar="BYTES", help="skip files larger than this (default 1 MiB)")
    parser.add_argument("--json", action="store_true",
                        help="print findings as JSON instead of text")
    args = parser.parse_args(argv)

    if not args.path.is_dir():
        print(f"error: {args.path} is not a directory", file=sys.stderr)
        return 2
    allowlist = load_allowlist(args.allowlist) if args.allowlist else []

    findings, scanned, skipped = scan(
        args.path.resolve(), list(args.exclude), allowlist, args.max_size)

    if args.json:
        print(json.dumps({"findings": findings, "files_scanned": scanned,
                          "files_skipped": skipped}, indent=2))
    else:
        for item in findings:
            print(f"{item['file']}:{item['line']} [{item['severity']}] "
                  f"{item['rule']}: {item['match']}")
        print(f"\nScanned {scanned} file(s), skipped {skipped}.")
        if findings:
            print(f"Found {len(findings)} potential secret(s). "
                  "Rotate any real credentials before committing.")
        else:
            print("No secrets found.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
