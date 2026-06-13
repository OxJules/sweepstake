#!/usr/bin/env python3
"""
World Cup 2026 Sweepstake
=========================
Pure Python, standard library only. No third-party packages. No paid services.

Commands
  python3 wcsweep.py draw      One-time random allocation of 48 teams to 7 people.
  python3 wcsweep.py update    Fetch results, recompute the table, write table.html,
                               and post the table to Telegram (if configured).
  python3 wcsweep.py table     Rebuild table.html from current results without posting.
  python3 wcsweep.py show      Print the saved allocation.

How scoring works
  Win = 3, Draw = 1, Loss = 0. The table is recomputed from scratch on every run
  (it reads every finished match), so re-running is always safe and never double-counts.
"""

import csv
import json
import os
import random
import sys
import unicodedata
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ===========================================================================
# CONFIG  --  edit this block, then run `draw`
# ===========================================================================

# The 7 players. Put the real names in before you run the draw.
PEOPLE = ["Julian", "Bawar", "Joseph", "Sophie",
          "Sumit", "Aditya", "Lukasz"]

# Points
WIN_POINTS = 3
DRAW_POINTS = 1
LOSS_POINTS = 0

# Knockout games that finish level and are decided on penalties:
#   False -> counted as a DRAW for both teams (1 pt each)   [default]
#   True  -> the shootout winner gets a WIN, the loser a LOSS
# (Irrelevant during the group stage, which can never end on penalties.)
PENALTY_WINNER_GETS_WIN = False

# Fix the draw for auditability: set an integer so the exact same draw can be
# reproduced and verified by anyone. Leave None for a genuinely random draw.
DRAW_SEED = None

# --- Where results come from -----------------------------------------------
# Option A (automatic): a FREE football-data.org token. Free signup, no card,
#   no subscription. Put it in the FOOTBALL_DATA_TOKEN environment variable
#   (recommended) or paste it between the quotes below.
FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
FD_COMPETITION = "WC"   # World Cup competition code on football-data.org

# Option B (manual, truly zero-dependency): if no token is set, results are read
#   from results.csv with columns:  date,home,away,home_goals,away_goals,decision
#   'decision' is optional and only used for penalty shootouts -> HOME or AWAY.
RESULTS_CSV = "results.csv"

# --- Telegram (optional) ----------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Slack (optional) -------------------------------------------------------
# A Slack "Incoming Webhook" URL. Create one at https://api.slack.com/apps ->
# your app -> Incoming Webhooks -> Add New Webhook to Workspace -> pick a
# channel; it gives you a https://hooks.slack.com/services/... URL. Put it in
# the SLACK_WEBHOOK_URL environment variable. No bot user or token needed.
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

ALLOCATION_FILE = "allocation.json"
TABLE_HTML = "table.html"

# ===========================================================================
# THE 48 TEAMS  --  ordered into 7 tiers by FIFA ranking (April 2026 update)
# Tier sizes: 7,7,7,7,7,7,6  =>  49 slots for 48 teams, so one bottom-tier
# team is shared by two people. Each entry: (canonical name, [provider aliases]).
# ===========================================================================

TIERS = [
    # Tier 1  (FIFA 1-7)
    [("France", []), ("Spain", []), ("Argentina", []), ("England", []),
     ("Portugal", []), ("Brazil", []), ("Netherlands", [])],
    # Tier 2  (FIFA 8-15)
    [("Morocco", []), ("Belgium", []), ("Germany", []), ("Croatia", []),
     ("Colombia", []), ("Senegal", []), ("Mexico", [])],
    # Tier 3  (FIFA 16-24)
    [("United States", ["USA"]), ("Uruguay", []), ("Japan", []),
     ("Switzerland", []),
     ("Iran", ["IR Iran", "Islamic Republic of Iran"]),
     ("Austria", []), ("Ecuador", [])],
    # Tier 4  (FIFA 25-36)
    [("South Korea", ["Korea Republic"]), ("Australia", []), ("Egypt", []),
     ("Canada", []),
     ("Ivory Coast", ["Cote d'Ivoire", "Côte d'Ivoire"]),
     ("Qatar", []), ("Algeria", [])],
    # Tier 5  (FIFA 39-51)
    [("Sweden", []), ("Tunisia", []), ("Czechia", ["Czech Republic"]),
     ("Turkey", ["Türkiye", "Turkiye"]), ("Norway", []), ("Scotland", []),
     ("DR Congo", ["Congo DR", "Congo Democratic Republic"])],
    # Tier 6  (FIFA 52-64)
    [("Bosnia & Herzegovina", ["Bosnia-Herzegovina", "Bosnia and Herzegovina"]),
     ("Panama", []), ("Saudi Arabia", []), ("South Africa", []),
     ("Iraq", []), ("Uzbekistan", []), ("Paraguay", [])],
    # Tier 7  (bottom, FIFA 65-95) -- 6 teams; one is allocated to two people
    [("Ghana", []), ("Jordan", []), ("Cape Verde", ["Cabo Verde"]),
     ("Curacao", ["Curaçao"]), ("Haiti", []), ("New Zealand", [])],
]

# ===========================================================================
# Draw
# ===========================================================================

def do_draw():
    if len(PEOPLE) != 7:
        sys.exit("PEOPLE must contain exactly 7 names (found %d)." % len(PEOPLE))
    for i, tier in enumerate(TIERS[:-1], 1):
        if len(tier) != 7:
            sys.exit("Tier %d must have exactly 7 teams." % i)
    if len(TIERS[-1]) != 6:
        sys.exit("The bottom tier must have exactly 6 teams.")

    rng = random.Random(DRAW_SEED)
    allocation = {p: [] for p in PEOPLE}

    # Tiers 1-6: shuffle the 7 teams and deal one to each person.
    for tier in TIERS[:-1]:
        names = [t[0] for t in tier]
        rng.shuffle(names)
        for person, team in zip(PEOPLE, names):
            allocation[person].append(team)

    # Bottom tier: 6 teams, 7 people. Pick one team to be shared, then deal.
    bottom = [t[0] for t in TIERS[-1]]
    shared = rng.choice(bottom)
    pool = bottom + [shared]          # 7 tickets, one team duplicated
    rng.shuffle(pool)
    for person, team in zip(PEOPLE, pool):
        allocation[person].append(team)

    data = {
        "drawn_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": DRAW_SEED,
        "shared_bottom_team": shared,
        "allocation": allocation,
    }
    with open(ALLOCATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("Draw complete.  Shared bottom-tier team: %s\n" % shared)
    for person in PEOPLE:
        print("%s:" % person)
        for i, team in enumerate(allocation[person], 1):
            extra = "  (shared)" if (i == 7 and team == shared) else ""
            print("   Tier %d:  %s%s" % (i, team, extra))
        print()
    print("Saved to %s" % ALLOCATION_FILE)


def do_show():
    if not os.path.exists(ALLOCATION_FILE):
        sys.exit("No %s yet. Run `python3 wcsweep.py draw` first." % ALLOCATION_FILE)
    with open(ALLOCATION_FILE, encoding="utf-8") as f:
        data = json.load(f)
    print("Drawn at: %s   (seed=%s)" % (data["drawn_at"], data["seed"]))
    print("Shared bottom-tier team: %s\n" % data["shared_bottom_team"])
    for person, teams in data["allocation"].items():
        print("%-12s %s" % (person + ":", ", ".join(teams)))


# ===========================================================================
# Team-name matching (robust to provider spelling/accents)
# ===========================================================================

def norm(name):
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    for ch in "&.-'’/":
        s = s.replace(ch, " ")
    s = s.replace(" and ", " ")
    return " ".join(s.split())


def build_name_index():
    idx = {}
    for tier in TIERS:
        for canonical, aliases in tier:
            idx[norm(canonical)] = canonical
            for a in aliases:
                idx[norm(a)] = canonical
    return idx


NAME_INDEX = build_name_index()


def resolve_team(name):
    return NAME_INDEX.get(norm(name))


# ===========================================================================
# Results
# ===========================================================================

def fetch_results_api():
    url = "https://api.football-data.org/v4/competitions/%s/matches" % FD_COMPETITION
    req = urllib.request.Request(url, headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for m in data.get("matches", []):
        if m.get("status") != "FINISHED":
            continue
        ft = (m.get("score") or {}).get("fullTime") or {}
        hg, ag = ft.get("home"), ft.get("away")
        if hg is None or ag is None:
            continue
        out.append({
            "home": (m.get("homeTeam") or {}).get("name"),
            "away": (m.get("awayTeam") or {}).get("name"),
            "hg": int(hg), "ag": int(ag),
            "winner": (m.get("score") or {}).get("winner"),  # HOME_TEAM/AWAY_TEAM/DRAW
            "decision": "",
            "date": (m.get("utcDate") or "")[:10],
        })
    return out


def fetch_results_csv():
    out = []
    if not os.path.exists(RESULTS_CSV):
        return out
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("home") and row.get("away")):
                continue
            if row.get("home_goals") in (None, "") or row.get("away_goals") in (None, ""):
                continue
            out.append({
                "home": row["home"].strip(), "away": row["away"].strip(),
                "hg": int(row["home_goals"]), "ag": int(row["away_goals"]),
                "winner": None,
                "decision": (row.get("decision") or "").strip().upper(),
                "date": (row.get("date") or "").strip(),
            })
    return out


def get_results():
    if FOOTBALL_DATA_TOKEN:
        return fetch_results_api(), "football-data.org"
    return fetch_results_csv(), RESULTS_CSV


def points_for_match(m):
    hg, ag = m["hg"], m["ag"]
    if hg > ag:
        return WIN_POINTS, LOSS_POINTS
    if ag > hg:
        return LOSS_POINTS, WIN_POINTS
    if PENALTY_WINNER_GETS_WIN:
        dec, winner = m.get("decision") or "", m.get("winner")
        if dec == "HOME" or winner == "HOME_TEAM":
            return WIN_POINTS, LOSS_POINTS
        if dec == "AWAY" or winner == "AWAY_TEAM":
            return LOSS_POINTS, WIN_POINTS
    return DRAW_POINTS, DRAW_POINTS


def compute_team_points(matches):
    pts, stats, unmatched = {}, {}, set()
    for m in matches:
        home, away = resolve_team(m["home"]), resolve_team(m["away"])
        if not home:
            unmatched.add(m["home"])
        if not away:
            unmatched.add(m["away"])
        hp, ap = points_for_match(m)
        for team, gf, ga, p in [(home, m["hg"], m["ag"], hp),
                                (away, m["ag"], m["hg"], ap)]:
            if not team:
                continue
            s = stats.setdefault(team, {"P": 0, "W": 0, "D": 0, "L": 0,
                                        "GF": 0, "GA": 0, "Pts": 0})
            s["P"] += 1; s["GF"] += gf; s["GA"] += ga; s["Pts"] += p
            if gf > ga: s["W"] += 1
            elif gf < ga: s["L"] += 1
            else: s["D"] += 1
            pts[team] = pts.get(team, 0) + p
    return pts, stats, unmatched


def build_standings(alloc, team_pts):
    rows = []
    for person, teams in alloc.items():
        breakdown = [(t, team_pts.get(t, 0)) for t in teams]
        rows.append({
            "person": person,
            "total": sum(p for _, p in breakdown),
            "teams": breakdown,
        })
    rows.sort(key=lambda r: (-r["total"], r["person"]))
    return rows


# ===========================================================================
# Output: Telegram text + HTML table
# ===========================================================================

def standings_text(rows, updated):
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 World Cup Sweepstake", "Updated %s UTC" % updated, ""]
    for i, r in enumerate(rows, 1):
        tag = medals.get(i, "%d." % i)
        lines.append("%s %s — %d pts" % (tag, r["person"], r["total"]))
    return "\n".join(lines)


def send_telegram(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("Telegram not configured; skipping post.")
        return
    url = "https://api.telegram.org/bot%s/sendMessage" % TELEGRAM_BOT_TOKEN
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=payload), timeout=30) as r:
            r.read()
        print("Posted table to Telegram.")
    except urllib.error.URLError as e:
        print("Telegram post failed: %s" % e)


def send_slack(text):
    if not SLACK_WEBHOOK_URL:
        return
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL, data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print("Posted table to Slack.")
    except urllib.error.URLError as e:
        print("Slack post failed: %s" % e)


def build_html(rows, updated, source, shared, total_matches):
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    main_rows = []
    for i, r in enumerate(rows, 1):
        rank = medals.get(i, str(i))
        main_rows.append(
            "<tr><td class='rank'>%s</td><td class='who'>%s</td>"
            "<td class='pts'>%d</td></tr>" % (rank, esc(r["person"]), r["total"]))

    cards = []
    for i, r in enumerate(rows, 1):
        chips = []
        for team, p in r["teams"]:
            cls = "chip shared" if team == shared else "chip"
            tag = " ★" if team == shared else ""
            chips.append("<span class='%s'>%s%s<b>%d</b></span>"
                         % (cls, esc(team), tag, p))
        cards.append(
            "<div class='card'><div class='card-h'><span class='cn'>%d</span>"
            "<span class='cp'>%s</span><span class='ct'>%d pts</span></div>"
            "<div class='chips'>%s</div></div>"
            % (i, esc(r["person"]), r["total"], "".join(chips)))

    return """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>World Cup Sweepstake</title>
<style>
  :root{ --bg:#0c1424; --card:#13203a; --line:#22324f; --ink:#eaf0fb;
         --mut:#8aa0c4; --acc:#37d3a6; --gold:#f4c84a; }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
    font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
    padding:28px 16px;}
  .wrap{max-width:760px;margin:0 auto}
  h1{font-size:24px;margin:0 0 2px;letter-spacing:.2px}
  .sub{color:var(--mut);font-size:13px;margin-bottom:22px}
  table{width:100%%;border-collapse:collapse;background:var(--card);
    border:1px solid var(--line);border-radius:14px;overflow:hidden}
  th,td{padding:13px 16px;text-align:left}
  th{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);
    border-bottom:1px solid var(--line)}
  tbody tr+tr td{border-top:1px solid var(--line)}
  td.rank{width:54px;font-size:18px;font-weight:700;color:var(--gold)}
  td.who{font-weight:600}
  td.pts{text-align:right;font-weight:800;font-size:18px;color:var(--acc)}
  th.r{text-align:right}
  h2{font-size:14px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);
    margin:30px 0 12px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:14px 16px;margin-bottom:12px}
  .card-h{display:flex;align-items:center;gap:10px;margin-bottom:10px}
  .cn{width:24px;height:24px;border-radius:50%%;background:#1d2c4a;color:var(--mut);
    display:grid;place-items:center;font-size:12px;font-weight:700}
  .cp{font-weight:700;flex:1}
  .ct{color:var(--acc);font-weight:800}
  .chips{display:flex;flex-wrap:wrap;gap:7px}
  .chip{background:#0f1b30;border:1px solid var(--line);border-radius:9px;
    padding:4px 9px;font-size:13px;color:var(--mut)}
  .chip b{color:var(--ink);margin-left:7px}
  .chip.shared{border-color:var(--gold);color:var(--gold)}
  .foot{color:var(--mut);font-size:12px;margin-top:24px}
  .foot b{color:var(--ink)}
</style></head>
<body><div class="wrap">
  <h1>🏆 World Cup Sweepstake</h1>
  <div class="sub">Updated %(updated)s UTC &middot; %(matches)d matches counted &middot; source: %(source)s</div>
  <table>
    <thead><tr><th>#</th><th>Player</th><th class="r">Points</th></tr></thead>
    <tbody>%(rows)s</tbody>
  </table>
  <h2>Breakdown by player</h2>
  %(cards)s
  <div class="foot">Win 3 &middot; Draw 1 &middot; Loss 0. ★ marks the shared bottom-tier
  team (<b>%(shared)s</b>), held by two players. Page refreshes every 10 minutes.</div>
</div></body></html>""" % {
        "updated": esc(updated), "matches": total_matches, "source": esc(source),
        "rows": "".join(main_rows), "cards": "".join(cards), "shared": esc(shared),
    }


# ===========================================================================
# Update
# ===========================================================================

def do_update(post=True):
    if not os.path.exists(ALLOCATION_FILE):
        sys.exit("No %s yet. Run `python3 wcsweep.py draw` first." % ALLOCATION_FILE)
    with open(ALLOCATION_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    alloc = saved["allocation"]
    shared = saved.get("shared_bottom_team", "")

    matches, source = get_results()
    team_pts, _stats, unmatched = compute_team_points(matches)
    if unmatched:
        print("WARNING: these result names did not match any team (add them as "
              "aliases in TIERS): %s" % ", ".join(sorted(unmatched)))

    rows = build_standings(alloc, team_pts)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    html = build_html(rows, updated, source, shared, len(matches))
    with open(TABLE_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote %s" % TABLE_HTML)

    text = standings_text(rows, updated)
    print("\n" + text + "\n")
    if post:
        send_telegram(text)
        send_slack(text)


# ===========================================================================
# CLI
# ===========================================================================

def main():
    # Windows consoles default to cp1252, which can't encode the emoji used in
    # the standings text; force UTF-8 so `update`/`table` don't crash on print.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "draw":
        do_draw()
    elif cmd == "update":
        do_update(post=True)
    elif cmd == "table":
        do_update(post=False)
    elif cmd == "show":
        do_show()
    else:
        print(__doc__)
        sys.exit(0 if cmd in ("", "-h", "--help", "help") else 2)


if __name__ == "__main__":
    main()
