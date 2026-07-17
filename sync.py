#!/usr/bin/env python3
"""Sync Jira issues + changelogs (since config.since) from all configured projects into jira.db (SQLite)."""
import base64
import json
import sqlite3
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text())

env_path = next((p for p in (ROOT / ".env", ROOT.parent / ".env") if p.exists()), None)
if env_path is None:
    raise SystemExit("ไม่พบไฟล์ .env — คัดลอก .env.example เป็น .env แล้วใส่ Jira email/token ของคุณก่อน")
env = {}
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
BASE = env["JIRA_BASE_URL"]
AUTH = base64.b64encode(f"{env['JIRA_EMAIL']}:{env['JIRA_API_TOKEN']}".encode()).decode()

FC = CFG["field_candidates"]
ALL_FIELDS = (["summary", "issuetype", "status", "assignee", "created", "resolutiondate",
               "priority", "labels", "parent", FC["sprint"]]
              + FC["dev_points"] + FC["test_points"] + FC["tester"])


def api(path, body=None, retries=4):
    url = path if path.startswith("http") else BASE + path
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=json.dumps(body).encode() if body else None,
            headers={"Authorization": f"Basic {AUTH}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(int(e.headers.get("Retry-After", 5)))
                continue
            raise


def coalesce(fields, candidates):
    for c in candidates:
        v = fields.get(c)
        if v is not None:
            return v
    return None


def as_names(v):
    """User field value (dict, list of dicts, or string) -> ';'-joined display names."""
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get("displayName")
    if isinstance(v, list):
        return ";".join(x.get("displayName", str(x)) if isinstance(x, dict) else str(x) for x in v)
    return str(v)


def as_num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def fetch_project_issues(key):
    issues, token = [], None
    jql = f'project="{key}" AND updated >= "{CFG["since"]}" ORDER BY key'
    while True:
        body = {"jql": jql, "maxResults": 100, "fields": ALL_FIELDS}
        if token:
            body["nextPageToken"] = token
        d = api("/rest/api/3/search/jql", body)
        issues.extend(d.get("issues", []))
        token = d.get("nextPageToken")
        if not token:
            return issues


def fetch_changelog(key):
    out, start = [], 0
    while True:
        d = api(f"/rest/api/3/issue/{key}/changelog?startAt={start}&maxResults=100")
        for h in d.get("values", []):
            for item in h.get("items", []):
                if item.get("field") == "status":
                    out.append((key, h["created"],
                                (h.get("author") or {}).get("displayName", ""),
                                item.get("fromString", ""), item.get("toString", "")))
        start += len(d.get("values", []))
        if start >= d.get("total", 0) or not d.get("values"):
            return out


db = sqlite3.connect(ROOT / "jira.db")
db.executescript("""
DROP TABLE IF EXISTS issues; DROP TABLE IF EXISTS transitions;
DROP TABLE IF EXISTS sprints; DROP TABLE IF EXISTS issue_sprints;
CREATE TABLE issues(key TEXT PRIMARY KEY, project TEXT, type TEXT, summary TEXT,
  status TEXT, assignee TEXT, tester TEXT, dev_points REAL, test_points REAL,
  priority TEXT, labels TEXT, parent_key TEXT, parent_summary TEXT,
  created TEXT, resolved TEXT);
CREATE TABLE transitions(issue_key TEXT, ts TEXT, author TEXT, from_status TEXT, to_status TEXT);
CREATE TABLE sprints(id INTEGER PRIMARY KEY, name TEXT, state TEXT,
  start_date TEXT, end_date TEXT, complete_date TEXT);
CREATE TABLE issue_sprints(issue_key TEXT, sprint_id INTEGER);
""")

all_keys = []
sprint_rows = {}
for proj in CFG["projects"]:
    issues = fetch_project_issues(proj)
    print(f"{proj}: {len(issues)} issues")
    for it in issues:
        f = it["fields"]
        key = it["key"]
        all_keys.append(key)
        tester = coalesce(f, FC["tester"])
        parent = f.get("parent") or {}
        db.execute("INSERT OR REPLACE INTO issues VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            key, proj, (f.get("issuetype") or {}).get("name", ""), f.get("summary", ""),
            (f.get("status") or {}).get("name", ""),
            (f.get("assignee") or {}).get("displayName"),
            as_names(tester),
            as_num(coalesce(f, FC["dev_points"])), as_num(coalesce(f, FC["test_points"])),
            (f.get("priority") or {}).get("name", ""),
            ";".join(f.get("labels") or []),
            parent.get("key"), (parent.get("fields") or {}).get("summary"),
            f.get("created"), f.get("resolutiondate")))
        for s in f.get(FC["sprint"]) or []:
            db.execute("INSERT INTO issue_sprints VALUES(?,?)", (key, s["id"]))
            sprint_rows[s["id"]] = (s["id"], s.get("name"), s.get("state"),
                                    s.get("startDate"), s.get("endDate"), s.get("completeDate"))

db.executemany("INSERT OR REPLACE INTO sprints VALUES(?,?,?,?,?,?)", sprint_rows.values())
db.commit()
print(f"total issues: {len(all_keys)}, sprints: {len(sprint_rows)}")

print("fetching changelogs...")
done = 0
with ThreadPoolExecutor(max_workers=10) as ex:
    futures = {ex.submit(fetch_changelog, k): k for k in all_keys}
    for fut in as_completed(futures):
        rows = fut.result()
        db.executemany("INSERT INTO transitions VALUES(?,?,?,?,?)", rows)
        done += 1
        if done % 250 == 0:
            print(f"  {done}/{len(all_keys)}")
            db.commit()
db.commit()
n = db.execute("SELECT COUNT(*) FROM transitions").fetchone()[0]
print(f"done. transitions: {n}")
