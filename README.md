# World Cup 2026 Sweepstake

A single Python file. No third-party packages (`pip install` nothing), no paid
services, no database. It draws 48 teams between 7 players, keeps a running
points table from match results, writes an HTML table, and posts the standings
to Telegram.

## How the allocation works

- 48 teams are split into **7 tiers by FIFA ranking** (April 2026 update).
- Each player gets **one team from each tier**, so 7 teams each.
- 7 players × 7 tiers = 49 slots but there are only 48 teams, so **one
  bottom-tier team is drawn to two players** (it earns points for both). The
  bottom tier therefore has 6 teams; tiers 1–6 have 7 each.
- Everything is drawn at random. Set `DRAW_SEED` to a number if you want the
  draw to be reproducible/auditable.

Scoring: **Win 3, Draw 1, Loss 0**. The table is rebuilt from every finished
match on each run, so re-running never double-counts.

## One-time setup

1. **Edit `wcsweep.py`** — put your 7 names in `PEOPLE` near the top.
2. **Run the draw once:**
   ```
   python3 wcsweep.py draw
   ```
   This creates `allocation.json`. Don't run `draw` again or it re-randomises.
3. **Choose how results come in** (pick one):
   - **Automatic** — get a free token at football-data.org (free account, no
     card). Then set it as an environment variable:
     ```
     export FOOTBALL_DATA_TOKEN=your_token_here
     ```
   - **Manual** — leave the token unset and fill in `results.csv`:
     ```
     date,home,away,home_goals,away_goals,decision
     2026-06-11,Mexico,South Africa,2,1,
     ```
     (`decision` is only for knockout penalty shootouts: `HOME` or `AWAY`.)

4. **Update the table:**
   ```
   python3 wcsweep.py update      # fetch/read results, rebuild table.html, post to Telegram
   python3 wcsweep.py table       # same but no Telegram post
   python3 wcsweep.py show        # print the allocation
   ```

## Telegram (optional)

1. Message **@BotFather** in Telegram, send `/newbot`, follow the prompts, copy
   the bot token.
2. Add the bot to your group (or DM it), send any message in the chat.
3. Get the chat id: open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and read
   the `chat.id` value.
4. Set both:
   ```
   export TELEGRAM_BOT_TOKEN=...
   export TELEGRAM_CHAT_ID=...
   ```
   If these aren't set, the script just skips posting.

## Running it automatically every day

### Option A — GitHub Actions (free, no server)
1. Push this folder to a GitHub repo (including the `allocation.json` produced
   by your draw).
2. Repo **Settings → Secrets and variables → Actions** → add
   `FOOTBALL_DATA_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. The included `.github/workflows/daily.yml` runs once a day at 06:00 UTC,
   refreshes `table.html`, commits it back, and posts to Telegram. You can also
   run it on demand from the **Actions** tab.
4. To put the table online for free, enable **Settings → Pages** (deploy from
   the repo root); your table lives at `https://<user>.github.io/<repo>/table.html`.

### Option B — cron on any machine
```
0 6 * * *  cd /path/to/wcsweep && FOOTBALL_DATA_TOKEN=xxx TELEGRAM_BOT_TOKEN=yyy TELEGRAM_CHAT_ID=zzz /usr/bin/python3 wcsweep.py update
```

## Notes

- **Team names:** the script matches provider names to teams using a built-in
  alias list (handles "Korea Republic", "Türkiye", "Côte d'Ivoire", etc.). If a
  result ever logs a name it can't match, `update` prints a `WARNING` naming it —
  add that spelling to the team's alias list in `TIERS` and re-run.
- **Penalty shootouts:** group-stage games can't be drawn-then-decided, so they
  are exact. For knockout games that go to penalties, the default counts them as
  a draw (1 pt each). Set `PENALTY_WINNER_GETS_WIN = True` to instead award the
  shootout winner a win.
