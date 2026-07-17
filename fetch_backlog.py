#!/usr/bin/env python3
"""Fetch detailed backlog data from Jira board 49 (fundii/FUN) and save as JSON + CSV."""
import base64
import csv
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
env_path = next((p for p in (ROOT / ".env", ROOT.parent / ".env") if p.exists()), None)
if env_path is None:
    raise SystemExit("ไม่พบไฟล์ .env — คัดลอก .env.example เป็น .env แล้วใส่ Jira email/token ของคุณก่อน")
env = {}
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

BASE = env["JIRA_BASE_URL"]
auth = base64.b64encode(f"{env['JIRA_EMAIL']}:{env['JIRA_API_TOKEN']}".encode()).decode()

FIELDS = ",".join([
    "summary", "issuetype", "status", "priority", "assignee", "reporter",
    "created", "updated", "duedate", "labels", "components", "fixVersions",
    "parent", "description",
    "customfield_10016",  # Story point estimate
    "customfield_10023",  # Story Points
    "customfield_10508",  # Story point
    "customfield_10014",  # Epic Link
])


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def adf_to_text(node):
    """Flatten Atlassian Document Format to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    out = []
    if isinstance(node, dict):
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        for child in node.get("content", []) or []:
            out.append(adf_to_text(child))
        if node.get("type") in ("paragraph", "heading", "listItem"):
            out.append("\n")
    elif isinstance(node, list):
        for child in node:
            out.append(adf_to_text(child))
    return "".join(out)


issues = []
start = 0
while True:
    data = get(f"{BASE}/rest/agile/1.0/board/49/backlog?startAt={start}&maxResults=100&fields={FIELDS}")
    issues.extend(data["issues"])
    start += len(data["issues"])
    if start >= data["total"] or not data["issues"]:
        break
print(f"fetched {len(issues)} backlog issues")

(ROOT / "backlog_raw.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))

rows = []
for it in issues:
    f = it["fields"]
    sp = f.get("customfield_10016") or f.get("customfield_10023") or f.get("customfield_10508")
    rows.append({
        "key": it["key"],
        "type": (f.get("issuetype") or {}).get("name", ""),
        "summary": f.get("summary", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "priority": (f.get("priority") or {}).get("name", ""),
        "assignee": (f.get("assignee") or {}).get("displayName", ""),
        "reporter": (f.get("reporter") or {}).get("displayName", ""),
        "story_points": sp if sp is not None else "",
        "epic": (f.get("parent") or {}).get("fields", {}).get("summary", ""),
        "epic_key": (f.get("parent") or {}).get("key", ""),
        "labels": ";".join(f.get("labels") or []),
        "components": ";".join(c["name"] for c in f.get("components") or []),
        "fix_versions": ";".join(v["name"] for v in f.get("fixVersions") or []),
        "created": (f.get("created") or "")[:10],
        "updated": (f.get("updated") or "")[:10],
        "due_date": f.get("duedate") or "",
        "description": adf_to_text(f.get("description")).strip()[:2000],
    })

with open(ROOT / "backlog.csv", "w", newline="") as fp:
    w = csv.DictWriter(fp, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
print(f"wrote backlog.csv with {len(rows)} rows")
