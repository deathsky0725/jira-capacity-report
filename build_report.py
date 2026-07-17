#!/usr/bin/env python3
"""Compute capacity/velocity metrics from jira.db and generate report.html.

Rules (agreed with user):
- Scope: issues resolved since config.since (2026-01-01).
- Dev points come from the primary assignee; tester points from the Tester field.
- Working days = Mon-Fri only.
- Dev actual = first entry into a dev_start status -> LAST entry into a handoff
  status (the successful handoff to QA, per user's rule "ส่งถึงมือเทสแล้วไม่เกิด defect").
- Tester actual = first entry into a handoff status (received work) -> done.
- Sprint attribution = sprint of the same project whose date window contains the
  resolution date (issue-sprint links are unreliable on FUN, where nearly the
  whole board is linked to every sprint).
- Fallback for issues with an estimate but NO testing point (old projects):
  the handoff step in the changelog splits the work, and the original estimate
  is divided 50/50 between the dev side and the test side. Owners are inferred:
  dev side = assignee with dev role, else the dev-role author of dev transitions;
  test side = Tester field, else the tester-role author of testing/done
  transitions, else a tester-role assignee. If no test side exists at all
  (no handoff), the dev keeps the full estimate.
"""
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text())

# Jira base URL comes from the runner's .env (kept out of git) — used for links in the report
_env_path = next((p for p in (ROOT / ".env", ROOT.parent / ".env") if p.exists()), None)
JIRA_BASE = ""
if _env_path:
    for _line in _env_path.read_text().splitlines():
        if _line.startswith("JIRA_BASE_URL="):
            JIRA_BASE = _line.split("=", 1)[1].strip().rstrip("/")
SINCE = CFG["since"]
db = sqlite3.connect(ROOT / "jira.db")
db.row_factory = sqlite3.Row


HOLIDAYS = {date.fromisoformat(h) for h in CFG.get("holidays", [])}


def is_workday(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def workdays(a, b):
    """Inclusive Mon-Fri day count (Thai public holidays excluded); 0 if b < a."""
    d0, d1 = date.fromisoformat(a[:10]), date.fromisoformat(b[:10])
    if d1 < d0:
        return 0
    days, d = 0, d0
    while d <= d1:
        if is_workday(d):
            days += 1
        d += timedelta(days=1)
    return days


# --- sprints: map to a project by majority of linked issues, keep dated ones ---
sprints = {}
for r in db.execute("""
    SELECT s.id, s.name, s.state, s.start_date, s.end_date, s.complete_date,
           (SELECT i.project FROM issue_sprints js JOIN issues i ON i.key=js.issue_key
            WHERE js.sprint_id=s.id GROUP BY i.project ORDER BY COUNT(*) DESC LIMIT 1) proj
    FROM sprints s WHERE s.start_date IS NOT NULL"""):
    sprints[r["id"]] = {
        "id": r["id"], "name": r["name"], "state": r["state"], "project": r["proj"],
        "start": r["start_date"][:10],
        "end": (r["complete_date"] or r["end_date"])[:10],
    }
by_proj_sprints = {}
for s in sprints.values():
    by_proj_sprints.setdefault(s["project"], []).append(s)
for lst in by_proj_sprints.values():
    lst.sort(key=lambda s: s["start"])


def attribute_sprint(project, resolved):
    d = resolved[:10]
    best = None
    for s in by_proj_sprints.get(project, []):
        end_grace = (date.fromisoformat(s["end"]) + timedelta(days=3)).isoformat()
        if s["start"] <= d <= end_grace:
            best = s  # keep latest-starting window that contains d
    return best["id"] if best else None


# --- transitions per issue (with author, for owner inference) ---
trans = {}
for r in db.execute("SELECT issue_key, ts, author, to_status FROM transitions ORDER BY ts"):
    trans.setdefault(r["issue_key"], []).append((r["ts"], r["author"], r["to_status"]))

# --- roles: infer from field usage, then apply roles.json overrides ---
counts = {}
for r in db.execute(f"SELECT assignee, tester FROM issues WHERE resolved >= '{SINCE}' AND type != 'Epic'"):
    if r["assignee"]:
        counts.setdefault(r["assignee"], [0, 0])[0] += 1
    for t in (r["tester"] or "").split(";"):
        if t:
            counts.setdefault(t, [0, 0])[1] += 1
roles_file = ROOT / "roles.json"
overrides = json.loads(roles_file.read_text()) if roles_file.exists() else {}
people = {}
for name, (n_dev, n_test) in sorted(counts.items()):
    inferred = "tester" if n_test > n_dev else "dev"
    ov = overrides.get(name, inferred)
    # roles.json entry is either "dev"/"tester" or
    # {"role": "dev", "label": "PE", "capacity": 0.5} for partial-capacity roles
    if isinstance(ov, dict):
        role, label, capacity = ov.get("role", inferred), ov.get("label"), ov.get("capacity", 1.0)
    else:
        role, label, capacity = ov, None, 1.0
    people[name] = {"role": role, "label": label, "capacity": capacity,
                    "nAssignee": n_dev, "nTester": n_test,
                    "overridden": role != inferred or capacity != 1.0,
                    "hasLeaves": False}  # set after leaves.json is loaded below
if not roles_file.exists():
    roles_file.write_text(json.dumps(
        {n: p["role"] for n, p in people.items()}, ensure_ascii=False, indent=1))
    print("wrote roles.json (edit roles there, then rerun)")
role_of = lambda n: people.get(n, {}).get("role")

# --- personal leave days (Phase 10): fill leaves.json when leave data exists ---
leaves_file = ROOT / "leaves.json"
if not leaves_file.exists():
    leaves_file.write_text(json.dumps({n: [] for n in sorted(people)}, ensure_ascii=False, indent=1))
    print("wrote leaves.json template (add leave dates per person, then rerun)")
LEAVES = {n: {date.fromisoformat(d) for d in ds}
          for n, ds in json.loads(leaves_file.read_text()).items()}
for n, ds in LEAVES.items():
    if ds and n in people:
        people[n]["hasLeaves"] = True


def workdays_p(person, a, b):
    """workdays() minus the person's leave days inside the range."""
    days = workdays(a, b)
    for d in LEAVES.get(person or "", ()):
        if date.fromisoformat(a[:10]) <= d <= date.fromisoformat(b[:10]) and is_workday(d):
            days -= 1
    return max(days, 0)


# Availability factor: everyone gets annual_leave_days vacation and is assumed to
# use all of it, so on average (workdays - leave) / workdays of a person's time is
# available. Applied to expected durations for people WITHOUT explicit dates in
# leaves.json (explicit dates already reduce their actual days — no double count).
YEAR = int(SINCE[:4])
year_workdays = workdays(f"{YEAR}-01-01", f"{YEAR}-12-31")
AVAILABILITY = round((year_workdays - CFG.get("annual_leave_days", 0)) / year_workdays, 4)

# --- per-issue metrics ---
issues_out = []
n_split = 0
for r in db.execute(f"""
    SELECT * FROM issues
    WHERE resolved >= '{SINCE}' AND type != 'Epic'"""):
    proj = r["project"]
    sm = CFG["status_map"][proj]
    if r["status"] in sm["excluded"]:
        continue
    tlist = trans.get(r["key"], [])
    dev_start = next((ts for ts, a, st in tlist if st in sm["dev_start"]), None)
    handoffs = [ts for ts, a, st in tlist if st in sm["handoff"]]
    done_ts = next((ts for ts, a, st in reversed(tlist) if st in sm["done"]), None) or r["resolved"]
    defect_events = [(ts[:10], a) for ts, a, st in tlist if st in sm["defect"]]
    defects = len(defect_events)

    testers = [t for t in (r["tester"] or "").split(";") if t]
    assignee = r["assignee"]

    # --- owner inference (before day math so leave days can be person-aware) ---
    dev_owner = assignee if (assignee and role_of(assignee) == "dev") else None
    if not dev_owner:
        dev_owner = next((a for ts, a, st in tlist
                          if st in sm["dev_start"] + sm["handoff"] and role_of(a) == "dev"), None)
    test_owners = [t for t in testers]
    if not test_owners:
        inferred_t = next((a for ts, a, st in tlist
                           if st in (sm["handoff"] + sm["defect"] + sm["done"])
                           and role_of(a) == "tester"), None)
        if inferred_t:
            test_owners = [inferred_t]
        elif assignee and role_of(assignee) == "tester":
            test_owners = [assignee]

    dev_days = test_days = queue_days = None
    dev_end = handoffs[-1] if handoffs else done_ts
    if dev_start:
        dev_days = workdays_p(dev_owner, dev_start, dev_end)
    # tester clock starts when testing actually begins, not when the card
    # lands in the Ready-to-test queue; the wait in between is queue time
    test_start = next((ts for ts, a, st in tlist if st in sm.get("test_active", [])), None)
    if handoffs and not test_start:
        test_start = handoffs[0]
    if test_start:
        test_days = workdays_p(test_owners[0] if test_owners else None, test_start, done_ts)
        if handoffs:
            queue_days = max(workdays(handoffs[0], test_start) - 1, 0)

    # --- point allocation (50/50 fallback when no testing point field) ---
    dev_pts_eff, test_pts_eff, split = r["dev_points"], r["test_points"], False
    if r["test_points"] is None and r["dev_points"] is not None:
        has_test_side = bool(handoffs or test_owners)
        if has_test_side:
            split = True
            n_split += 1
            dev_pts_eff = r["dev_points"] / 2
            test_pts_eff = r["dev_points"] / 2

    issues_out.append({
        "key": r["key"], "project": proj, "type": r["type"],
        "summary": r["summary"], "status": r["status"],
        "assignee": assignee, "devOwner": dev_owner, "testOwners": test_owners,
        "devPts": dev_pts_eff, "testPts": test_pts_eff, "split": split,
        "rawPts": r["dev_points"],
        "resolved": r["resolved"][:10],
        "sprint": (sid := attribute_sprint(proj, r["resolved"])),
        # carried over = dev started before the closing sprint's window opened
        "carried": bool(dev_start and sid and dev_start[:10] < sprints[sid]["start"]),
        "devStart": dev_start and dev_start[:10],
        "handoff": handoffs and handoffs[-1][:10] or None,
        "received": handoffs and handoffs[0][:10] or None,
        "testStart": test_start and test_start[:10],
        "doneTs": done_ts[:10],
        "devDays": dev_days, "testDays": test_days, "queueDays": queue_days,
        "defects": defects, "defectBy": [a for _, a in defect_events],
        "hasDefectFlow": bool(sm["defect"]),  # project has a fail status to detect at all
        # first-pass = reached QA and never bounced back (null if never reached QA)
        "firstPass": (defects == 0) if handoffs else None,
    })

# --- Phase 2: average parallel WIP per person (cards held at once, workdays only) ---


def avg_wip(intervals):
    load = defaultdict(int)
    for s, e in intervals:
        d, end = date.fromisoformat(s), date.fromisoformat(e)
        while d <= end:
            if is_workday(d):
                load[d] += 1
            d += timedelta(days=1)
    return round(sum(load.values()) / len(load), 2) if load else None


dev_iv, test_iv = defaultdict(list), defaultdict(list)
for it in issues_out:
    if it["devOwner"] and it["devStart"]:
        end = it["handoff"] or it["doneTs"]
        if end >= it["devStart"]:
            dev_iv[it["devOwner"]].append((it["devStart"], end))
    t_start = it["testStart"] or it["received"]
    if t_start and it["doneTs"] >= t_start:
        for t in it["testOwners"]:
            test_iv[t].append((t_start, it["doneTs"]))
for name, p in people.items():
    p["wipDev"] = avg_wip(dev_iv.get(name, []))
    p["wipTest"] = avg_wip(test_iv.get(name, []))

# --- Phase 3: imputed points for unpointed issues, from the team's median pace ---
IMP_CAP = 10  # cap per issue so a forgotten card doesn't mint absurd points
dev_rates = [it["devDays"] / it["devPts"] for it in issues_out
             if it["devPts"] and it["devDays"]]
test_rates = [it["testDays"] / it["testPts"] for it in issues_out
              if it["testPts"] and it["testDays"]]
rate_dev = round(statistics.median(dev_rates), 2) if dev_rates else None
rate_test = round(statistics.median(test_rates), 2) if test_rates else None
n_imputed = 0
for it in issues_out:
    it["devPtsImp"] = it["testPtsImp"] = None
    if it["devPts"] is None and it["devDays"] and rate_dev:
        it["devPtsImp"] = round(min(it["devDays"] / rate_dev, IMP_CAP), 1)
    if it["testPts"] is None and it["testDays"] and rate_test:
        it["testPtsImp"] = round(min(it["testDays"] / rate_test, IMP_CAP), 1)
    if it["devPtsImp"] or it["testPtsImp"]:
        n_imputed += 1

used_sprints = sorted(
    {it["sprint"] for it in issues_out if it["sprint"]},
    key=lambda sid: sprints[sid]["start"])
DATA = {
    "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "since": SINCE,
    "projects": sorted({it["project"] for it in issues_out}),
    "sprints": [sprints[sid] for sid in used_sprints],
    "people": people,
    "issues": issues_out,
    "nSplit": n_split,
    "nImputed": n_imputed,
    "rateDev": rate_dev, "rateTest": rate_test,
    "jiraBase": JIRA_BASE,
    "availability": AVAILABILITY,
    "annualLeaveDays": CFG.get("annual_leave_days", 0),
    "yearWorkdays": year_workdays,
}

html = (ROOT / "report_template.html").read_text()
out = html.replace("/*__DATA__*/", "const DATA = " + json.dumps(DATA, ensure_ascii=False) + ";")
(ROOT / "report.html").write_text(out)
print(f"report.html: {len(issues_out)} issues ({n_split} split 50/50), "
      f"{len(used_sprints)} sprints, {len(people)} people")
