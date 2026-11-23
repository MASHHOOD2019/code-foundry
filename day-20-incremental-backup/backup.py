#!/usr/bin/env python3
"""Incremental Backup.

Copies a source folder to a backup destination, but only copies
files that are new or changed since the last run. Change detection
is content-based: each file's size and mtime are checked first, and
only files whose size or mtime moved get a SHA-256 hash, so a second
run over an unchanged tree is fast.

Features:
  --dry-run   preview what would be copied, deleted, or skipped
  --delete    remove backup files whose source file is gone
  --verify    re-hash the backup and check it against the manifest
  --exclude   skip paths matching a glob (repeatable, e.g. "*.log")
  manifest: a JSON record of every backed-up file (relative path,
  size, mtime, SHA-256) stored as .backup_manifest.json in the
  destination, so later runs know what changed
  safe by default: never follows symlinks, never overwrites a
  changed file without hashing it first, unreadable files are
  reported as warnings instead of aborting the run

Stdlib only, no dependencies.

Usage:
  python3 backup.py ~/Projects ~/Backups/projects
  python3 backup.py ~/Projects ~/Backups/projects --dry-run
  python3 backup.py ~/Projects ~/Backups/projects --delete
  python3 backup.py ~/Projects ~/Backups/projects --verify
  python3 backup.py ~/Projects ~/Backups/projects --exclude "*.log" --exclude "__pycache__"
"""

import argparse
import fnmatch
import hashlib
import json
import shutil
import sys
from pathlib import Path

MANIFEST_NAME = ".backup_manifest.json"
CHUNK_SIZE = 1024 * 1024  # 1 MiB


def human_size(nbytes):
    """Format a byte count as a short human-readable string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(nbytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{nbytes} B"


def sha256_of(path):
    """Return the hex SHA-256 digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def is_excluded(relative_path, patterns):
    """True when a relative path matches any --exclude glob."""
    text = relative_path.as_posix()
    return any(fnmatch.fnmatch(text, p) or fnmatch.fnmatch(relative_path.name, p)
               for p in patterns)


def load_manifest(destination):
    """Read the manifest from a previous run, or return {}."""
    manifest_path = destination / MANIFEST_NAME
    if not manifest_path.is_file():
        return {}
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        print(f"warning: could not read manifest ({exc}); treating backup as fresh",
              file=sys.stderr)
        return {}


def save_manifest(destination, manifest):
    """Write the manifest atomically (temp file + rename)."""
    manifest_path = destination / MANIFEST_NAME
    tmp_path = destination / (MANIFEST_NAME + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(manifest_path)


def scan_source(source, exclude):
    """Walk the source tree; return {rel_path: Path} for regular files.

    Symlinks are never followed and hidden files are included, since
    a backup that silently drops dotfiles is a broken backup.
    """
    files = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(source)
        if is_excluded(rel, exclude):
            continue
        files[rel.as_posix()] = path
    return files


def run_backup(source, destination, exclude, dry_run, delete):
    """Copy new/changed files; return (copied, skipped, removed, bytes)."""
    old_manifest = load_manifest(destination)
    files = scan_source(source, exclude)
    new_manifest = {}
    copied = skipped = 0
    copied_bytes = 0
    warnings = []

    for rel, path in files.items():
        try:
            stat = path.stat()
        except OSError as exc:
            warnings.append(f"{rel}: cannot stat ({exc})")
            continue
        entry = old_manifest.get(rel)
        # Fast path: same size and mtime means unchanged, no hash needed.
        if (entry and entry.get("size") == stat.st_size
                and entry.get("mtime") == stat.st_mtime):
            new_manifest[rel] = entry
            skipped += 1
            continue
        try:
            digest = sha256_of(path)
        except OSError as exc:
            warnings.append(f"{rel}: cannot read ({exc})")
            continue
        # Hash matches the manifest even though mtime moved: content
        # is identical, so keep the recorded entry and skip the copy.
        if entry and entry.get("sha256") == digest:
            new_manifest[rel] = {"size": stat.st_size,
                                 "mtime": stat.st_mtime, "sha256": digest}
            skipped += 1
            continue
        target = destination / rel
        print(f"copy: {rel} ({human_size(stat.st_size)})")
        if not dry_run:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            except OSError as exc:
                warnings.append(f"{rel}: cannot copy ({exc})")
                continue
        new_manifest[rel] = {"size": stat.st_size,
                             "mtime": stat.st_mtime, "sha256": digest}
        copied += 1
        copied_bytes += stat.st_size

    removed = 0
    if delete:
        for rel in sorted(old_manifest):
            if rel not in files and rel != MANIFEST_NAME:
                target = destination / rel
                print(f"remove: {rel} (no longer in source)")
                if not dry_run and target.is_file():
                    try:
                        target.unlink()
                    except OSError as exc:
                        warnings.append(f"{rel}: cannot remove ({exc})")
                        continue
                removed += 1
    else:
        stale = [rel for rel in old_manifest if rel not in files]
        if stale:
            print(f"note: {len(stale)} backup file(s) no longer in source; "
                  "use --delete to remove them", file=sys.stderr)

    if not dry_run:
        save_manifest(destination, new_manifest)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return copied, skipped, removed, copied_bytes, len(warnings)


def run_verify(destination, exclude):
    """Re-hash every file in the manifest; return (ok, bad, missing)."""
    manifest = load_manifest(destination)
    if not manifest:
        print("no manifest found; nothing to verify", file=sys.stderr)
        return 0, 0, 0
    ok = bad = missing = 0
    for rel in sorted(manifest):
        if is_excluded(Path(rel), exclude):
            continue
        target = destination / rel
        if not target.is_file():
            print(f"missing: {rel}")
            missing += 1
            continue
        try:
            digest = sha256_of(target)
        except OSError as exc:
            print(f"unreadable: {rel} ({exc})")
            bad += 1
            continue
        if digest == manifest[rel].get("sha256"):
            ok += 1
        else:
            print(f"mismatch: {rel}")
            bad += 1
    return ok, bad, missing


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Incremental backup: copy only new or changed files.")
    parser.add_argument("source", type=Path, help="folder to back up")
    parser.add_argument("destination", type=Path, help="backup folder")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview only; copy, delete, and write nothing")
    parser.add_argument("--delete", action="store_true",
                        help="remove backup files whose source file is gone")
    parser.add_argument("--verify", action="store_true",
                        help="check the backup against its manifest instead "
                             "of copying")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="GLOB",
                        help="skip paths matching this glob (repeatable)")
    args = parser.parse_args(argv)

    if not args.source.is_dir():
        print(f"error: source is not a directory: {args.source}", file=sys.stderr)
        return 2
    if args.source.resolve() == args.destination.resolve():
        print("error: source and destination must be different folders",
              file=sys.stderr)
        return 2
    if args.destination.is_file():
        print(f"error: destination exists and is a file: {args.destination}",
              file=sys.stderr)
        return 2

    if args.verify:
        ok, bad, missing = run_verify(args.destination, args.exclude)
        print(f"Verified {ok} file(s): {bad} mismatched, {missing} missing.")
        return 1 if (bad or missing) else 0

    if not args.dry_run:
        args.destination.mkdir(parents=True, exist_ok=True)

    copied, skipped, removed, copied_bytes, warnings = run_backup(
        args.source, args.destination, args.exclude, args.dry_run, args.delete)

    action = "Would copy" if args.dry_run else "Copied"
    print(f"\n{action} {copied} file(s) ({human_size(copied_bytes)}), "
          f"skipped {skipped} unchanged file(s)"
          + (f", removed {removed} stale file(s)" if args.delete else "")
          + (f". {warnings} warning(s)." if warnings else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
