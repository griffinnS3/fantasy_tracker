# Fantasy Football ADP & Mock Draft Tools

A small set of Python scripts for analyzing NFL fantasy football data: comparing
Average Draft Position (ADP) against actual fantasy performance, and running a
simulated 12-team mock draft (with an optional live human drafter) using that data.

## What's in this project

| File | Purpose |
|---|---|
| `adp_vs_fantasy_points.py` | Pulls ADP + fantasy points data and builds the shared dataset. Also produces a labeled scatter/dot plot of ADP vs. fantasy points. |
| `mock_draft_simulator.py` | Simulates a 12-team snake draft using that dataset, with optional live human participation. |
| `.gitignore` | Standard ignores for Python venvs, caches, and generated output files. |

`mock_draft_simulator.py` imports `build_merged_dataset()` from
`adp_vs_fantasy_points.py`, so **both files need to stay in the same directory**.

## Data sources

- **Fantasy points**: [nflreadpy](https://github.com/nflverse/nflreadpy) — the
  official, actively maintained Python package for nflverse data (play-by-play,
  weekly stats, etc.). Free, no API key required.
- **ADP**: [Fantasy Football Calculator's public API](https://fantasyfootballcalculator.com/adp) —
  ADP generated from live mock drafts. Free, no API key required.
- **Rookie projections**: rookies have no prior-NFL stats to pull, so their
  projected points are *estimated* by fitting a simple ADP-to-points curve on
  veteran players and applying it to each rookie's ADP. This is a rough proxy
  based only on draft position, not a real scouting-based projection — treat
  it as a placeholder until/unless you wire in a real projections source
  (e.g. FantasyPros or Fantasy Nerds).

## Setup

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows

pip install nflreadpy pandas matplotlib requests adjustText numpy --break-system-packages
```

> If you're on Python 3.12+ and hit a `pkg_resources` / build error during
> install, make sure `setuptools` is installed in your venv first
> (`pip install setuptools`) — fresh 3.12+ venvs don't include it by default.

## Usage

### 1. ADP vs. fantasy points chart

```bash
python adp_vs_fantasy_points.py
```

Fetches the configured season's fantasy stats and the configured draft year's
ADP, merges them (including rookies via the estimate described above), and
saves a labeled scatter plot to `adp_vs_fantasy_points.png`. Rookies are drawn
as stars (★) to distinguish them from real season data.

**Key config (top of file):**

| Variable | Meaning |
|---|---|
| `SEASON` | Season to pull actual stats for (e.g. `2025`) |
| `ADP_YEAR` | Season the ADP data is drafted for (e.g. `2026`) |
| `SCORING` | Scoring format for ADP: `standard`, `ppr`, `half-ppr`, `2qb`, `dynasty`, `rookie` |
| `TEAMS` | League size used for the ADP calculation |
| `FANTASY_POINTS_COL` | `fantasy_points_ppr` or `fantasy_points` depending on scoring |
| `MAX_PLAYERS_TO_LABEL` | Caps how many players are plotted/labeled, to keep the chart readable |

### 2. Mock draft simulator

```bash
python mock_draft_simulator.py
```

Simulates a 12-team snake draft. AI teams draft using ADP or fantasy points
(configurable) plus some randomness so it doesn't draft in a robotic, perfect order. You can also add human players to teams to draft alongside the AI teams.

**Key config (top of file):**

| Variable | Meaning |
|---|---|
| `NUM_TEAMS` | Number of teams in the draft |
| `AI_DRAFT_STRATEGY` | `"points"` (draft by fantasy points) or `"adp"` (draft by ADP) |
| `NOISE_STD` / `POINTS_NOISE_STD` | How much randomness AI drafters have around their strategy — `0` = perfectly ranked order |
| `HUMAN_TEAMS` | Set of team numbers you control yourself, e.g. `{1}` or `{1, 5, 9}` |
| `NUM_SHOWN_CANDIDATES` | How many top-available players are shown to a human drafter each pick |
| `ROSTER_SLOTS` | Your league's roster settings (QB/RB/WR/TE/FLEX/bench counts) |
| `RANDOM_SEED` | Set an int for a reproducible draft; `None` for a new random draft each run |

When it's your turn, you'll see a ranked list of eligible players and can pick
by number, or type part of a player's name to search the full eligible pool
(not just what's shown). Rookies are tagged `(R)` everywhere they appear so
you always know when a points value is an estimate.

At the end, it prints the full draft board, every team's final roster, and a
ranking of teams by total points, remember that for rookies this is the
ADP-based estimate, and for veterans it's last season's actual production, not
a forecast of the upcoming season.

## Known limitations

- **Name matching** between nflreadpy and the ADP API is done by normalizing
  player names (lowercased, suffixes/punctuation stripped) since the two
  sources don't share a common player ID. This mostly works but can
  occasionally mismatch or miss players with unusual name formatting.
- **Rookie projections are a rough estimate**, not real scouting data 
- **Team grading uses last season's actual points** for veterans, which is a
  backward-looking number, not a forecast for the season the ADP is drafted
  for.

## Possible next steps

- Swap in a real projections API (FantasyPros, Fantasy Nerds, SportsDataIO)
  for both veterans and rookies instead of last season's actuals.
- Add K/DST support if your league starts those positions.
- Export the mock draft results to CSV for easier post-draft analysis.
