#!/usr/bin/env python3
"""Disk Usage Analyzer.

Answers "where did my disk space go?" for any folder: it walks the
tree once, totals the size of every directory, and reports the
largest files and the largest subdirectories, with a simple bar
chart so the hogs are obvious at a glance.

How it works:
  1. One os.walk pass collects every file's size (os.scandir is
     used where it is faster, and unreadable entries are skipped
     with a warning instead of crashing the run).
  2. Each file's size is added to every ancestor directory up to
     the scanned root, so directory totals are exact, not sampled.
  3. Results are sorted biggest first; --top limits the lists,
     --depth limits how deep the directory breakdown goes, and
     --min-size hides files smaller than a threshold.

Hidden files and folders are skipped by default (add --all to
include them), symlinks are never followed, and --exclude drops
paths matching glob patterns such as "*.log" or "node_modules".

Stdlib only, no dependencies.

Usage:
  python3 diskusage.py ~/Downloads
  python3 diskusage.py ~/Projects --top 10 --depth 2
  python3 diskusage.py ~/Photos --min-size 10M --json report.json
  python3 diskusage.py . --exclude "*.log" --exclude "node_modules"
"""

import argparse
import fnmatch
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

BAR_WIDTH = 40


def parse_size(text):
    """Parse a human size like '500', '10K', '2.5M', '1G' into bytes."""
    text = text.strip().upper()
    multipliers = {"B": 1, "K": 1024, "KB": 1024,
                   "M": 1024 ** 2, "MB": 1024 ** 2,
                   "G": 1024 ** 3, "GB": 1024 ** 3,
                   "T": 1024 ** 4, "TB": 1024 ** 4}
    for suffix in ("KB", "MB", "GB", "TB", "K", "M", "G", "T", "B"):
        if text.endswith(suffix):
            number = text[:-len(suffix)]
            try:
                return int(float(number) * multipliers[suffix])
            except ValueError:
                raise argparse.ArgumentTypeError(
                    "invalid size: {!r}".format(text))
    try:
        return int(float(text))
    except ValueError:
        raise argparse.ArgumentTypeError("invalid size: {!r}".format(text))


def format_size(size, raw=False):
    """Format bytes as a human-readable string ('5.9 KB') or raw bytes."""
    if raw:
        return str(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return "{} B".format(int(value))
            return "{:.1f} {}".format(value, unit)
        value /= 1024
    return "{} B".format(size)  # pragma: no cover - unreachable


def is_excluded(path, root, patterns):
    """True if path (relative to root) matches any --exclude pattern."""
    rel = str(path.relative_to(root))
    name = path.name
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p)
               for p in patterns)


def scan(root, include_hidden, patterns):
    """Walk root once and return (dir_sizes, files, counts, errors).

    dir_sizes maps each directory to the total bytes under it,
    files is a list of (size, path), counts holds file/dir totals,
    and errors lists paths that could not be read.
    """
    root = Path(root)
    dir_sizes = defaultdict(int)
    files = []
    counts = {"files": 0, "dirs": 0}
    errors = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        counts["dirs"] += 1
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        dirnames[:] = [d for d in dirnames
                       if not is_excluded(current / d, root, patterns)]
        for name in filenames:
            path = current / name
            if not include_hidden and name.startswith("."):
                continue
            if is_excluded(path, root, patterns):
                continue
            try:
                size = path.stat().st_size if not path.is_symlink() \
                    else os.lstat(path).st_size
            except OSError:
                errors.append(str(path))
                continue
            counts["files"] += 1
            files.append((size, path))
            ancestor = current
            while True:
                dir_sizes[ancestor] += size
                if ancestor == root:
                    break
                ancestor = ancestor.parent
    return dir_sizes, files, counts, errors


def depth_of(path, root):
    """How many levels below root path sits (root itself is 0)."""
    return len(path.relative_to(root).parts)


def report(root, dir_sizes, files, counts, errors, args):
    """Build the result dict and print the human-readable report."""
    total = dir_sizes.get(Path(root), 0)
    big_files = sorted(files, reverse=True)
    if args.min_size:
        big_files = [f for f in big_files if f[0] >= args.min_size]
    big_files = big_files[:args.top]

    dirs = [(size, path) for path, size in dir_sizes.items()
            if path != Path(root)
            and depth_of(path, Path(root)) <= args.depth]
    big_dirs = sorted(dirs, reverse=True)[:args.top]

    result = {
        "root": str(Path(root)),
        "total_bytes": total,
        "files": counts["files"],
        "directories": counts["dirs"],
        "unreadable": errors,
        "largest_files": [{"size_bytes": s, "path": str(p)}
                          for s, p in big_files],
        "largest_directories": [{"size_bytes": s, "path": str(p)}
                                for s, p in big_dirs],
    }

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")

    def bar(size):
        filled = int(BAR_WIDTH * size / total) if total else 0
        return "#" * filled + "-" * (BAR_WIDTH - filled)

    print("Disk usage for {}".format(root))
    print("Total: {} in {} file(s), {} directorie(s)".format(
        format_size(total, args.bytes), counts["files"], counts["dirs"]))
    if errors:
        print("Warning: could not read {} entr(ies), e.g. {}".format(
            len(errors), errors[0]))

    print("\nLargest files:")
    if not big_files:
        print("  (none)")
    for size, path in big_files:
        print("  {:>9}  {}  {}".format(
            format_size(size, args.bytes), bar(size), path))

    print("\nLargest directories (depth <= {}):".format(args.depth))
    if not big_dirs:
        print("  (none)")
    for size, path in big_dirs:
        print("  {:>9}  {}  {}".format(
            format_size(size, args.bytes), bar(size), path))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Show where disk space goes inside a folder.")
    parser.add_argument("path", help="folder to analyze")
    parser.add_argument("--top", type=int, default=10,
                        help="how many entries to list (default 10)")
    parser.add_argument("--depth", type=int, default=1,
                        help="how deep the directory breakdown goes "
                             "(default 1)")
    parser.add_argument("--min-size", type=parse_size, default=0,
                        help="ignore files smaller than this "
                             "(e.g. 10K, 2M, 1G)")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="PATTERN",
                        help="skip paths matching a glob (repeatable)")
    parser.add_argument("--all", action="store_true",
                        help="include hidden files and folders")
    parser.add_argument("--bytes", action="store_true",
                        help="show raw byte counts instead of human sizes")
    parser.add_argument("--json", metavar="FILE",
                        help="also write the full report as JSON")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print("error: not a directory: {}".format(args.path),
              file=sys.stderr)
        return 2
    if args.top < 1 or args.depth < 1:
        print("error: --top and --depth must be at least 1",
              file=sys.stderr)
        return 2

    dir_sizes, files, counts, errors = scan(
        root, args.all, args.exclude)
    report(root, dir_sizes, files, counts, errors, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
