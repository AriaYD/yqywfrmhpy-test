#!/usr/bin/env python3
"""Report sources at review date; never edits rules or merges policy changes."""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
from urllib.request import Request, urlopen
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from campuspath_context import PackLoader, _iso_today  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None, help="ISO date used for deterministic checks")
    parser.add_argument("--http", action="store_true", help="Check HTTP status, redirect target, and content hash")
    args = parser.parse_args()
    today = _iso_today(args.as_of)
    loader = PackLoader()
    due = [s for s in loader.sources.values() if today >= _iso_today(s["next_review_at"]) or s["status"] != "active"]
    print(f"Source freshness report as of {today.isoformat()}: {len(due)} due or non-active of {len(loader.sources)}")
    for source in sorted(due, key=lambda item: item["source_id"]):
        print(f"{source['source_id']}\tstatus={source['status']}\tnext_review_at={source['next_review_at']}\turl={source['url']}")
    if args.http:
        print("HTTP checks (report only; this script never edits policy files):")
        for source in sorted(loader.sources.values(), key=lambda item: item["source_id"]):
            try:
                request = Request(source["url"], headers={"User-Agent": "CampusPath-context-pack-freshness/0.1"})
                with urlopen(request, timeout=15) as response:
                    body = response.read()
                    print(f"{source['source_id']}\thttp_status={response.status}\tfinal_url={response.geturl()}\tsha256={hashlib.sha256(body).hexdigest()}")
            except Exception as exc:
                print(f"{source['source_id']}\thttp_error={exc}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
