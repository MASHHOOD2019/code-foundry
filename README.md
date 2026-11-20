# code-foundry

The daily coding streak continues here. One small, real program
every day, picking up at Day 14 (Days 1-13 live in cpp-foundry and
py-foundry). No filler commits, no empty files.

## Day 14 - Smart File Organizer (Python)

`day-14-file-organizer/organizer.py`

Sorts the loose files in a folder into category subfolders by
extension: Images, Documents, Audio, Video, Archives, Code, and
Other for anything unrecognized. It never overwrites: a name that
is already taken gets `_1`, `_2`, and so on appended. Every move is
recorded in a JSON undo log (`.organizer_undo.json`), so a run can
be fully reversed with `--undo`. Preview everything first with
`--dry-run`, and add `--recursive` to also sort files inside
subfolders. Stdlib only, no dependencies.

How to run:

```
python3 organizer.py ~/Downloads
python3 organizer.py ~/Downloads --dry-run
python3 organizer.py ~/Downloads --recursive
python3 organizer.py ~/Downloads --undo
```

Example:

```
moved: backup.zip -> Archives/backup.zip
moved: notes.txt -> Documents/notes.txt
moved: photo.jpg -> Images/photo.jpg
moved: song.mp3 -> Audio/song.mp3

Organized 4 file(s):
  Archives: 1
  Audio: 1
  Documents: 1
  Images: 1
```

## Day 15 - LRU Cache (C++)

`day-15-lru-cache/lru_cache.hpp` and `main.cpp`

A templated least-recently-used cache with O(1) average `get()` and
`put()`: a doubly linked list keeps entries ordered by recency (front
is most recently used, back is least recently used) and an unordered
map from key to list node makes every lookup constant time. A full
cache evicts the back entry in O(1). Updating an existing key
refreshes its value and its recency, misses return `std::nullopt`,
and capacity 0 is rejected at construction. No thread safety by
design; wrap calls in a mutex if shared across threads. The demo in
`main.cpp` verifies eviction order, updates, misses, and the
capacity guard with assertions.

How to run:

```
g++ -std=c++17 -Wall -Wextra -O2 main.cpp -o lru_demo
./lru_demo
```

Example:

```
All LRU cache checks passed (capacity 3, eviction + update + miss behaviour verified).
```

## Day 16 - Duplicate File Finder (Python)

`day-16-duplicate-finder/dupfind.py`

Scans a directory tree and reports files with identical content, so
wasted disk space can be reclaimed safely. It is fast on big trees:
files are grouped by size first (a unique size cannot be a
duplicate), then a small first-chunk hash filters the rest, and only
the survivors get a full SHA-256 hash. `--delete` moves duplicates
to a trash folder instead of deleting them outright, keeping the
newest copy in each group, and `--restore` puts them back from the
manifest. `--dry-run` previews everything, `--min-size` skips small
files, and `--json` writes a machine-readable report. Stdlib only,
no dependencies.

How to run:

```
python3 dupfind.py ~/Downloads
python3 dupfind.py ~/Photos --min-size 1M --json report.json
python3 dupfind.py ~/Downloads --dry-run --delete
python3 dupfind.py ~/Downloads --delete --yes
python3 dupfind.py ~/Downloads --restore
```

Example:

```
Scanned 6 file(s) in /tmp/duptest

Group 1 (3 copies, 5.9 KB each):
  keep: /tmp/duptest/c.txt
  dup:  /tmp/duptest/sub/b.txt
  dup:  /tmp/duptest/a.txt

2 duplicate group(s), 3 extra file(s), 11.7 KB reclaimable.
```

## Day 17 - Token Bucket Rate Limiter (C++)

`day-17-rate-limiter/rate_limiter.hpp` and `main.cpp`

A thread-safe token bucket rate limiter: the bucket holds up to
`capacity` tokens and refills continuously at `rate_per_second`
tokens per second. Each request spends one token (or more); when the
bucket is empty the request is rejected immediately instead of
queueing, so a burst can never overwhelm the downstream service.
Every acquire is O(1) time and O(1) memory, and a single mutex
guards all state, so the limiter is safe to share across threads.
Oversized, zero, and negative requests are rejected without spending
tokens, and fractional rates are supported.

How to run:

```
g++ -std=c++17 -Wall -Wextra -O2 main.cpp -o rate_limiter_demo -pthread
./rate_limiter_demo
```

Example:

```
Burst check passed: 5 allowed, 6th rejected.
Refill check passed: 2 tokens back after ~200 ms.
Validation check passed: bad requests rejected.
Concurrency check passed: exactly 10 of 400 requests granted across 8 threads.
Sustained-rate check passed: 19 requests in 1 s at 20 tokens/sec.
All rate limiter checks passed.
```
