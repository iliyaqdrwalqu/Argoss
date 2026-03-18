#!/usr/bin/env python3
"""publish_report_to_gist.py

Read reports/argos_ci_report.md and update the file `argos_report.md` inside
the GitHub Gist identified by the GIST_ID environment variable.

Required environment variables:
  GIST_TOKEN  – GitHub PAT with `gist` scope (store as Actions secret)
  GIST_ID     – ID of the target Gist
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPORT_FILE = REPO_ROOT / "reports" / "argos_ci_report.md"
GIST_FILENAME = "argos_report.md"
GITHUB_API = "https://api.github.com"


def main() -> int:
    token = os.environ.get("GIST_TOKEN", "").strip()
    gist_id = os.environ.get("GIST_ID", "").strip()

    if not token:
        print("ERROR: GIST_TOKEN environment variable is not set.")
        return 1
    if not gist_id:
        print("ERROR: GIST_ID environment variable is not set.")
        return 1

    if not REPORT_FILE.exists():
        print(f"ERROR: Report file not found: {REPORT_FILE}")
        return 1

    content = REPORT_FILE.read_text(encoding="utf-8")
    print(f"Report file size: {len(content)} characters")

    payload = json.dumps(
        {"files": {GIST_FILENAME: {"content": content}}}
    ).encode("utf-8")

    url = f"{GITHUB_API}/gists/{gist_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")

    print(f"Updating Gist {gist_id} …")
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            html_url = body.get("html_url", "<unknown>")
            print(f"✅ Gist updated successfully: {html_url}")
            return 0
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: GitHub API returned HTTP {exc.code}: {exc.reason}")
        print(f"Response body: {error_body}")
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: Network error while calling GitHub API: {exc.reason}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
