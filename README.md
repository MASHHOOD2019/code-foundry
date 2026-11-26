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

## Day 18 - Disk Usage Analyzer (Python)

`day-18-disk-usage/diskusage.py`

Answers "where did my disk space go?" for any folder: one walk of
the tree totals the size of every directory and reports the largest
files and the largest subdirectories, with a bar chart so the hogs
are obvious at a glance. Directory totals are exact, each file's
size is added to every ancestor up to the scanned root. Hidden
files are skipped by default (`--all` includes them), symlinks are
never followed, and unreadable entries are reported as warnings
instead of crashing the run. `--top` limits the lists, `--depth`
limits how deep the directory breakdown goes, `--min-size` (e.g.
10K, 2M, 1G) hides small files, `--exclude` drops paths matching
glob patterns, `--bytes` shows raw byte counts, and `--json`
writes the full report as JSON. Stdlib only, no dependencies.

How to run:

```
python3 diskusage.py ~/Downloads
python3 diskusage.py ~/Projects --top 10 --depth 2
python3 diskusage.py ~/Photos --min-size 10M --json report.json
python3 diskusage.py . --exclude "*.log" --exclude "node_modules"
```

Example:

```
Disk usage for /tmp/dutest
Total: 26.4 KB in 5 file(s), 4 directorie(s)

Largest files:
     8.8 KB  #############---------------------------  /tmp/dutest/logs/e.log
     7.8 KB  ###########-----------------------------  /tmp/dutest/sub/c.bin

Largest directories (depth <= 1):
     9.8 KB  ##############--------------------------  /tmp/dutest/sub
     8.8 KB  #############---------------------------  /tmp/dutest/logs
```

## Day 19 - Thread Pool (C++)

`day-19-thread-pool/thread_pool.hpp` and `main.cpp`

A fixed-size thread pool: submit work with `enqueue()` and get a
`std::future` for the result. One mutex and condition variable guard
the task queue; workers sleep while it is empty and wake on notify.
`enqueue` is O(1) amortised, and exceptions thrown by a task travel
through its future instead of killing the worker. Shutdown is
graceful: the destructor stops accepting new work, lets already-queued
tasks finish, then joins every worker, so no submitted task is ever
dropped. Reuse the same pool for many short jobs instead of paying a
thread-spawn cost per job.

How to run:

```
g++ -std=c++17 -Wall -Wextra -O2 main.cpp -o thread_pool_demo -pthread
./thread_pool_demo
```

Example:

```
Parallel sum check passed: 1..1000 = 500500.
Exception check passed: error reached the caller, pool kept working.
Shutdown check passed: all 20 queued tasks ran before join.
Arguments check passed: enqueue(a, b) returned 42, void task ran.
All thread pool checks passed.
```

## Day 20 - Incremental Backup (Python)

`day-20-incremental-backup/backup.py`

Copies a folder to a backup destination, but only copies files that
are new or changed since the last run. Change detection is
content-based: size and mtime are checked first, and only files
whose size or mtime moved get a SHA-256 hash, so a second run over
an unchanged tree copies nothing and finishes fast. A JSON manifest
(`.backup_manifest.json`) in the destination records every backed-up
file's size, mtime, and hash, so later runs know what changed.
`--verify` re-hashes the backup and reports mismatches or missing
files, `--delete` prunes backup files whose source file is gone,
`--exclude` skips paths matching a glob, and `--dry-run` previews
everything first. Symlinks are never followed and unreadable files
are reported as warnings instead of aborting the run. Stdlib only,
no dependencies.

How to run:

```
python3 backup.py ~/Projects ~/Backups/projects
python3 backup.py ~/Projects ~/Backups/projects --dry-run
python3 backup.py ~/Projects ~/Backups/projects --delete
python3 backup.py ~/Projects ~/Backups/projects --verify
python3 backup.py ~/Projects ~/Backups/projects --exclude "*.log" --exclude "__pycache__"
```

Example:

```
copy: a.txt (12 B)
copy: big.bin (4.9 KB)
copy: sub/b.txt (9 B)

Copied 3 file(s) (4.9 KB), skipped 0 unchanged file(s).

Copied 0 file(s) (0 B), skipped 3 unchanged file(s).
Verified 3 file(s): 0 mismatched, 0 missing.
```

## Day 21 - Memory Pool (C++)

`day-21-memory-pool/memory_pool.hpp` and `main.cpp`

A fixed-size block allocator for one object type: it pre-allocates
large chunks, carves them into equal-size blocks and hands them out
from an intrusive free list, so `allocate()` and `deallocate()` are
O(1) pointer operations with no system call on the hot path. Each
block is sized to hold a `T` or the free-list pointer, whichever is
larger, and rounded up to `alignof(T)` so every block start stays
properly aligned for placement-new. `create()` / `destroy()` wrap
construction and destruction, so the pool owns both memory and
lifetime, and freeing a block returns it to the head of the list so
it is reused by the next allocation. A new chunk is grown only when
the free list is empty; the destructor releases all chunks. Not
thread-safe by design, no lock on the hot path: give each thread its
own pool or guard it with a mutex. The demo verifies values,
alignment, address reuse of a freed block, growth across 3 chunks
for 40 allocations, and that `destroy()` runs the destructor.

How to run:

```
g++ -std=c++17 -Wall -Wextra -O2 main.cpp -o memory_pool_demo
./memory_pool_demo
```

Example:

```
Allocate + values + alignment check passed.
Free-block reuse check passed: freed address handed out again.
Chunk growth check passed: 40 allocations over 3 chunks, all values intact, all blocks returned.
Destructor check passed: destroy() runs the destructor.
All memory pool checks passed.
```

## Day 22 - Secret Scanner (Python)

`day-22-secret-scanner/secretscan.py`

Scans a directory tree for secrets that should never be committed:
AWS keys, GitHub and Slack tokens, Stripe keys, Google API keys,
JWTs, private key headers, and password-like assignments with
suspicious values. A Shannon-entropy check catches long
random-looking values assigned to a secret-like name even when no
fixed pattern matches. Findings never print the secret itself: only
the first 3 and last 2 characters are shown, so the report is safe
to paste into a ticket or a build log. Placeholders such as
`changeme` and `your_api_key` are ignored; `.git`,
`__pycache__`, `node_modules`, binary files, and files over 1 MiB
are skipped; `.secretscanignore` globs and `--allowlist` regexes
cover known fixtures; and a line ending in `# secretscan:ignore`
is suppressed. It exits 1 when it finds anything, so it works as a
pre-commit check or a CI gate, and `--json` prints machine-readable
output. Stdlib only, no dependencies.

How to run:

```
python3 secretscan.py ~/Projects/my-app
python3 secretscan.py ~/Projects/my-app --json
python3 secretscan.py ~/Projects/my-app --exclude "*.min.js" --allowlist allowlist.txt
```

Example:

```
config.py:1 [high] aws-access-key: AKI***************LE
config.py:3 [high] github-token: ghp***************************GH
sub/keys.txt:5 [medium] generic-secret-assignment: X9$***************1p

Scanned 5 file(s), skipped 0.
Found 7 potential secret(s). Rotate any real credentials before committing.
```

## Day 23 - Thread-Safe Blocking Queue (C++)

`day-23-thread-safe-queue/blocking_queue.hpp` and `main.cpp`

A bounded, thread-safe producer/consumer queue: the workhorse behind
thread-pool task queues, log pipelines, and message brokers' in-memory
buffers. A `std::deque<T>` holds the items under one mutex, with two
condition variables separating the wait conditions (`not_full_` for
producers, `not_empty_` for consumers), so a push only wakes
consumers and a pop only wakes producers. The bounded capacity gives
backpressure instead of letting an unbounded queue grow until the
process runs out of memory; `push()` blocks when full and `pop()`
blocks when empty. `close()` wakes every waiter, refuses further
pushes, and lets `pop()` drain the remaining items before returning
`false`, so consumers loop on "pop until false" and no thread is ever
left parked on a dead queue. `try_push`/`try_pop` take a timeout for
callers that need to poll or give up, and perfect-forwarding
`emplace`/`push` keep move-only types such as `unique_ptr` working.
All operations are O(1) amortized plus one mutex acquisition. The demo
in `main.cpp` verifies FIFO order, timeout behaviour on full/empty
queues, close/drain shutdown, move-only items, and a 4-producer /
4-consumer run in which all 10,000 items arrive exactly once.

How to run:

```
g++ -std=c++17 -Wall -Wextra -O2 -pthread main.cpp -o queue_demo
./queue_demo
```

Example:

```
FIFO order check passed.
Timeout check passed: try_push waited 50ms on a full queue, try_pop timed out on an empty one.
Close check passed: blocked waiter woke, queued items drained, later pushes refused.
Move-only check passed: unique_ptr<int> round-tripped.
Producer/consumer check passed: 4 consumers took all 10000 items from 4 producers exactly once (sum 49995000 matches 0..9999).
All blocking queue checks passed.
```
