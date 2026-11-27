#!/usr/bin/env python3
"""Access Log Analyzer.

Reads an Apache or Nginx access log in combined log format and
answers the questions every site owner asks first: who is hitting
the site, what is failing, and what is slow or suspicious.

    203.0.113.10 - - [27/Nov/2026:09:12:04 +0500] "GET /pricing HTTP/1.1"
    200 4821 "-" "Mozilla/5.0 ..."

What it reports:
  * total requests, unique visitors, total bytes served
  * status-code breakdown by class (2xx / 3xx / 4xx / 5xx) and
    the most common individual codes
  * top client IPs and the busiest hour of the day
  * most-requested endpoints (query strings stripped, so
    /search?q=a and /search?q=b count as one endpoint)
  * the most-requested missing pages (404s), which usually
    point at broken links or probing
  * known bots, separated from real browsers by user agent
  * the error rate, and the exact lines behind the errors
    when --errors is given

Lines that do not match the combined format are counted and
reported instead of crashing the run, so a log with a few
corrupt lines still yields a report. Stdlib only.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime

# Combined log format:
#   host ident user [day/month/year:hour:min:sec zone] "METHOD path proto"
#   status bytes "referer" "user-agent"
LOG_PATTERN = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>\S+) (?P<proto>[^"]*)" '
    r'(?P<status>\d{3}) (?P<bytes>\S+) "(?P<referer>[^"]*)" "(?P<agent>[^"]*)"'
)

# Substrings that mark a user agent as an automated crawler.
BOT_MARKERS = (
    "bot", "spider", "crawler", "slurp", "curl", "wget",
    "python-requests", "httpclient", "googlebot", "bingbot",
    "semrush", "ahrefs", "mj12bot", "dotbot", "petalbot",
)

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_time(raw):
    """Parse '27/Nov/2026:09:12:04 +0500' into a naive datetime."""
    try:
        day, rest = raw.split("/", 1)
        month_name, rest = rest.split("/", 1)
        year, clock = rest.split(":", 1)
        hour, minute, second = clock.split(" ", 1)[0].split(":")
        return datetime(
            int(year), MONTHS[month_name], int(day),
            int(hour), int(minute), int(second),
        )
    except (KeyError, ValueError, IndexError):
        return None


def parse_line(line):
    """Parse one log line; return a dict, or None if it is malformed."""
    match = LOG_PATTERN.match(line)
    if not match:
        return None
    fields = match.groupdict()
    try:
        status = int(fields["status"])
    except ValueError:
        return None
    try:
        size = 0 if fields["bytes"] == "-" else int(fields["bytes"])
    except ValueError:
        return None
    # Strip the query string so /search?q=a and /search?q=b
    # count as the same endpoint.
    path = fields["path"].split("?", 1)[0]
    agent = fields["agent"].lower()
    return {
        "ip": fields["ip"],
        "time": parse_time(fields["time"]),
        "method": fields["method"],
        "path": path,
        "status": status,
        "size": size,
        "agent": fields["agent"],
        "is_bot": any(marker in agent for marker in BOT_MARKERS),
        "raw": line.rstrip("\n"),
    }


def analyze(path, only_ip=None, since=None, until=None):
    """Walk the log once and collect every counter the report needs."""
    stats = {
        "total": 0,
        "malformed": 0,
        "unique_ips": set(),
        "bytes": 0,
        "statuses": Counter(),
        "status_classes": Counter(),
        "ips": Counter(),
        "endpoints": Counter(),
        "methods": Counter(),
        "hours": Counter(),
        "agents": Counter(),
        "not_found": Counter(),
        "bots": 0,
        "errors": 0,
        "error_lines": [],
    }
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = parse_line(line)
            if entry is None:
                stats["malformed"] += 1
                continue
            if only_ip and entry["ip"] != only_ip:
                continue
            if since and entry["time"] and entry["time"] < since:
                continue
            if until and entry["time"] and entry["time"] > until:
                continue
            stats["total"] += 1
            stats["unique_ips"].add(entry["ip"])
            stats["bytes"] += entry["size"]
            stats["statuses"][entry["status"]] += 1
            stats["status_classes"][f"{entry['status'] // 100}xx"] += 1
            stats["ips"][entry["ip"]] += 1
            stats["endpoints"][entry["path"]] += 1
            stats["methods"][entry["method"]] += 1
            if entry["time"] is not None:
                stats["hours"][entry["time"].hour] += 1
            stats["agents"][entry["agent"]] += 1
            if entry["is_bot"]:
                stats["bots"] += 1
            if entry["status"] == 404:
                stats["not_found"][entry["path"]] += 1
            if entry["status"] >= 400:
                stats["errors"] += 1
                if len(stats["error_lines"]) < 50:
                    stats["error_lines"].append(entry["raw"])
    stats["unique_ip_count"] = len(stats["unique_ips"])
    del stats["unique_ips"]
    return stats


def human_size(size):
    """Format a byte count the way a person reads it."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def print_report(stats, top, show_errors, filtered=False):
    """Print the human-readable summary."""
    total = stats["total"]
    print(f"Requests: {total} from {stats['unique_ip_count']} unique IP(s)")
    print(f"Data served: {human_size(stats['bytes'])}")
    if stats["malformed"] and not filtered:
        print(f"Malformed lines skipped: {stats['malformed']}")
    if total == 0:
        print("No matching requests in this log.")
        return

    print("\nStatus codes:")
    for code in sorted(stats["statuses"]):
        count = stats["statuses"][code]
        print(f"  {code}: {count} ({count / total * 100:.1f}%)")
    print("By class:", ", ".join(
        f"{cls} {stats['status_classes'][cls]}"
        for cls in sorted(stats["status_classes"])
    ))
    error_rate = stats["errors"] / total * 100
    print(f"Error rate: {error_rate:.1f}% ({stats['errors']} of {total})")

    if stats["hours"]:
        busiest = stats["hours"].most_common(1)[0]
        print(f"Busiest hour: {busiest[0]:02d}:00 with {busiest[1]} requests")

    print(f"\nTop {top} IPs:")
    for ip, count in stats["ips"].most_common(top):
        print(f"  {count:>6}  {ip}")

    print(f"\nTop {top} endpoints:")
    for endpoint, count in stats["endpoints"].most_common(top):
        print(f"  {count:>6}  {endpoint}")

    if stats["not_found"]:
        print(f"\nTop {top} missing pages (404):")
        for endpoint, count in stats["not_found"].most_common(top):
            print(f"  {count:>6}  {endpoint}")

    bot_share = stats["bots"] / total * 100
    print(f"\nBot traffic: {stats['bots']} requests ({bot_share:.1f}%)")
    print(f"Top {top} user agents:")
    for agent, count in stats["agents"].most_common(top):
        print(f"  {count:>6}  {agent[:90]}")

    if show_errors and stats["error_lines"]:
        print(f"\nError lines (showing {len(stats['error_lines'])}):")
        for line in stats["error_lines"]:
            print(f"  {line}")


def build_json(stats):
    """Convert the counters into a JSON-serialisable report."""
    report = dict(stats)
    report["statuses"] = dict(stats["statuses"])
    report["status_classes"] = dict(stats["status_classes"])
    report["ips"] = dict(stats["ips"].most_common(10))
    report["endpoints"] = dict(stats["endpoints"].most_common(10))
    report["methods"] = dict(stats["methods"])
    report["hours"] = {str(h): c for h, c in sorted(stats["hours"].items())}
    report["agents"] = dict(stats["agents"].most_common(10))
    report["not_found"] = dict(stats["not_found"].most_common(10))
    report["error_rate"] = (
        stats["errors"] / stats["total"] if stats["total"] else 0.0
    )
    return report


def parse_date(raw):
    """Parse a YYYY-MM-DD date for --since / --until."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"bad date {raw!r}, expected YYYY-MM-DD"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze an Apache/Nginx access log (combined format)."
    )
    parser.add_argument("logfile", help="path to the access log")
    parser.add_argument("--top", type=int, default=10,
                        help="entries shown per list (default: 10)")
    parser.add_argument("--ip", help="only count requests from this IP")
    parser.add_argument("--since", type=parse_date,
                        help="only count requests on/after YYYY-MM-DD")
    parser.add_argument("--until", type=parse_date,
                        help="only count requests up to YYYY-MM-DD")
    parser.add_argument("--errors", action="store_true",
                        help="also print the raw error lines")
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON instead of text")
    args = parser.parse_args(argv)

    if args.top < 1:
        parser.error("--top must be at least 1")
    try:
        stats = analyze(args.logfile, args.ip, args.since, args.until)
    except FileNotFoundError:
        print(f"error: no such file: {args.logfile}", file=sys.stderr)
        return 2
    except PermissionError:
        print(f"error: cannot read: {args.logfile}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(build_json(stats), indent=2))
    else:
        filtered = bool(args.ip or args.since or args.until)
        print_report(stats, args.top, args.errors, filtered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
