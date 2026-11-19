#!/usr/bin/env python3
"""Duplicate File Finder.

Scans a directory tree and reports files with identical content, so
wasted disk space can be reclaimed safely.

How it works:
  1. Group files by size; files with a unique size cannot be duplicates.
  2. For size groups with more than one file, hash a small first chunk
     (fast pre-filter that skips reading whole files).
  3. For files that match on the first chunk, hash the full content
     with SHA-256 and group by digest.

  --delete moves duplicates to the trash folder instead of deleting
  them outright, keeping the newest copy in each group. The trash
  folder can be restored with --restore. --delete never runs without
  --yes, and --dry-run previews everything first.

Stdlib only, no dependencies.

Usage:
  python3 dupfind.py ~/Downloads
  python3 dupfind.py ~/Photos --min-size 1M --json report.json
  python3 dupfind.py ~/Downloads --dry-run --delete
  python3 dupfind.py ~/Downloads --delete --yes
  python3 dupfind.py ~/Downloads --restore
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CHUNK_SIZE = 64 * 1024        # bytes read per hashing chunk
FIRST_CHUNK_SIZE = 4 * 1024   # bytes hashed in the fast pre-filter
TRASH_DIRNAME = ".dupfind_trash"
MANIFEST_NAME = "manifest.json"

SIZE_SUFFIXES = {"B": 1, "K": 1024, "KB": 1024,
                 "M": 1024 ** 2, "MB": 1024 ** 2,
                 "G": 1024 ** 3, "GB": 1024 ** 3}


# Author: Mashhood Ali

def parse_size(text):
    """Parse a human size like '1M', '512K' or '1024' into bytes."""
    text = text.strip().upper()
    for suffix in sorted(SIZE_SUFFIXES, key=len, reverse=True):
        if text.endswith(suffix):
            number = text[: -len(suffix)]
            try:
                return int(float(number) * SIZE_SUFFIXES[suffix])
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"invalid size: {text!r}")
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid size: {text!r}")


def format_size(num_bytes):
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024
    return f"{num_bytes} B"


def iter_files(root, follow_symlinks=False):
    """Yield every regular file under root, skipping the trash folder."""
    for dirpath, dirnames, filenames in os.walk(root,
                                                followlinks=follow_symlinks):
        dirnames[:] = [d for d in dirnames if d != TRASH_DIRNAME]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_file() and not path.is_symlink():
                    yield path
            except OSError:
                continue


def hash_prefix(path):
    """SHA-256 of the first few kilobytes of a file (fast pre-filter)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read(FIRST_CHUNK_SIZE))
    return digest.hexdigest()


def hash_file(path):
    """SHA-256 of a file's full content, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(root, min_size=1, follow_symlinks=False):
    """Return a list of duplicate groups.

    Each group is a list of Path objects with identical content,
    sorted newest first (so index 0 is the copy to keep).
    """
    by_size = defaultdict(list)
    scanned = 0
    for path in iter_files(root, follow_symlinks):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        scanned += 1
        if size >= min_size:
            by_size[size].append(path)

    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        by_prefix = defaultdict(list)
        for path in paths:
            try:
                by_prefix[hash_prefix(path)].append(path)
            except OSError:
                continue
        for candidates in by_prefix.values():
            if len(candidates) < 2:
                continue
            by_digest = defaultdict(list)
            for path in candidates:
                try:
                    by_digest[hash_file(path)].append(path)
                except OSError:
                    continue
            for copies in by_digest.values():
                if len(copies) > 1:
                    copies.sort(key=lambda p: p.stat().st_mtime,
                                reverse=True)
                    groups.append(copies)
    return groups, scanned


def move_to_trash(groups, root, dry_run):
    """Move every duplicate except the newest copy into the trash folder.

    Returns a manifest list of {kept, removed, trash_path} records.
    """
    trash_dir = Path(root) / TRASH_DIRNAME
    manifest = []
    for copies in groups:
        kept, *extras = copies
        for index, path in enumerate(extras, start=1):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            trash_name = f"{stamp}_{index}_{path.name}"
            trash_path = trash_dir / trash_name
            if not dry_run:
                trash_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(trash_path))
            manifest.append({
                "kept": str(kept),
                "removed": str(path),
                "trash_path": str(trash_path),
            })
    return manifest


def restore_trash(root):
    """Move every file in the trash folder back to its recorded location."""
    trash_dir = Path(root) / TRASH_DIRNAME
    manifest_path = trash_dir / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"No manifest found in {trash_dir}; nothing to restore.")
        return 0
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    restored = 0
    for record in manifest:
        trash_path = Path(record["trash_path"])
        original = Path(record["removed"])
        if not trash_path.exists():
            print(f"missing in trash, skipped: {original}")
            continue
        if original.exists():
            print(f"already exists, skipped: {original}")
            continue
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(trash_path), str(original))
        restored += 1
    if restored:
        manifest_path.unlink(missing_ok=True)
        try:
            trash_dir.rmdir()
        except OSError:
            pass
    print(f"Restored {restored} file(s).")
    return restored


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find duplicate files by content and reclaim disk space.")
    parser.add_argument("directory", type=Path,
                        help="directory tree to scan")
    parser.add_argument("--min-size", type=parse_size, default="1",
                        metavar="SIZE",
                        help="ignore files smaller than SIZE "
                             "(e.g. 1K, 512, 2M; default: 1 byte)")
    parser.add_argument("--follow-symlinks", action="store_true",
                        help="follow symlinked directories while scanning")
    parser.add_argument("--delete", action="store_true",
                        help="move duplicates (all but newest) to trash")
    parser.add_argument("--yes", action="store_true",
                        help="confirm --delete without prompting")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what --delete would do, change nothing")
    parser.add_argument("--json", type=Path, metavar="FILE",
                        help="write the duplicate report as JSON to FILE")
    parser.add_argument("--restore", action="store_true",
                        help="restore files previously moved to trash")
    args = parser.parse_args(argv)

    root = args.directory
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    if args.restore:
        return 0 if restore_trash(root) >= 0 else 1

    if args.delete and not args.yes and not args.dry_run:
        answer = input("Move duplicates to trash? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 0

    groups, scanned = find_duplicates(root, args.min_size,
                                      args.follow_symlinks)
    wasted = sum(p.stat().st_size for copies in groups for p in copies[1:])
    print(f"Scanned {scanned} file(s) in {root}")

    if not groups:
        print("No duplicates found.")
        return 0

    groups.sort(key=lambda g: sum(p.stat().st_size for p in g[1:]),
                reverse=True)
    for index, copies in enumerate(groups, start=1):
        size = copies[0].stat().st_size
        print(f"\nGroup {index} ({len(copies)} copies, "
              f"{format_size(size)} each):")
        print(f"  keep: {copies[0]}")
        for extra in copies[1:]:
            print(f"  dup:  {extra}")
    print(f"\n{len(groups)} duplicate group(s), "
          f"{sum(len(g) - 1 for g in groups)} extra file(s), "
          f"{format_size(wasted)} reclaimable.")

    if args.json:
        report = {
            "root": str(root),
            "scanned": scanned,
            "groups": [[str(p) for p in copies] for copies in groups],
            "reclaimable_bytes": wasted,
        }
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(f"Report written to {args.json}")

    if args.delete:
        manifest = move_to_trash(groups, root, args.dry_run)
        if args.dry_run:
            print(f"\nDry run: would move {len(manifest)} file(s) to trash.")
        else:
            trash_dir = root / TRASH_DIRNAME
            manifest_path = trash_dir / MANIFEST_NAME
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            print(f"\nMoved {len(manifest)} file(s) to {trash_dir}")
            print("Restore anytime with: "
                  f"python3 dupfind.py {root} --restore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
