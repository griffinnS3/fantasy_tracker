# Fantasy Football ADP & Mock Draft Tools

A small set of Python scripts for analyzing NFL fantasy football data: comparing
Average Draft Position (ADP) against actual fantasy performance, and running a
simulated 12-team mock draft (with an optional live human drafter) using that data.

## What's in this project

| File | Purpose |
|---|---|
| `adp_vs_fantasy_points.py` | Pulls ADP + fantasy points data and builds the shared dataset. Also produces a labeled scatter/dot plot of ADP vs. fantasy points. |
| `mock_draft_simulator.py` | Simulates a 12-team snake draft using that dataset, with optional live human participation. |
| `batch_draft_analysis.py` | Runs many simulated drafts back to back and reports which players tend to be the best/worst "value" picks. |
| `.gitignore` | Standard ignores for Python venvs, caches, and generated output files. |

`mock_draft_simulator.py` imports `build_merged_dataset()` from
`adp_vs_fantasy_points.py`, and `batch_draft_analysis.py` imports from both of
those files, so **all three `.py` files need to stay in the same directory**.

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
(configurable) plus some randomness so it doesn't draft in a robotic, perfectly
ranked order. You can also take control of one or more teams yourself.

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
ranking of teams by total points — remember that for rookies this is the
ADP-based estimate, and for veterans it's last season's actual production, not
a forecast of the upcoming season.

### 3. Batch draft analysis (player value over many drafts)

```bash
python batch_draft_analysis.py
```

Runs many fully-automated drafts back to back (no human input, so it can run
unattended) and reports which players tend to be the best/worst "value"
picks. This exists because the AI drafters have randomness built in, so a
given player doesn't go at the same pick every draft — running many drafts
and looking at where a player *typically* gets taken, versus what they
typically produce, surfaces a real going-rate instead of one noisy draft's
results.

**How "value" is calculated:** for every position, it fits an
expected-points-by-draft-slot curve (`points ≈ a × pick^b`) across all the
picks at that position from all the drafts, then for every pick computes
`value = actual points − expected points for a player at that position taken
at that pick`. Fitting a **separate curve per position** matters — a single
curve pooled across all positions would make QBs look like automatic "great
value," since QBs bank more raw points per roster spot than RB/WR/TE (only
one QB starts per team), which has nothing to do with how good an individual
pick actually was.

**Key config (top of file):**

| Variable | Meaning |
|---|---|
| `NUM_DRAFTS` | How many drafts to simulate and aggregate over |
| `BASE_SEED` | Each draft uses `BASE_SEED + draft_num` for reproducibility; `None` for fully random drafts each run |
| `TOP_N` | How many best/worst value players to print |
| `MIN_TIMES_DRAFTED` | Ignores players who appeared in fewer than this many drafts (too little signal to trust their average) |

**How many drafts is enough?** More drafts = a tighter, more trustworthy
average for each player, since `avg_pick`/`avg_value` are means over however
many drafts a player showed up in — the estimate's precision improves with
`1/√n`. As a rough guide:
- **10 drafts** (the default): fine for a quick look, but don't trust small
  differences between two players' value scores at this sample size.
- **50–100 drafts**: a solid middle ground — rankings stabilize meaningfully
  and fringe/bench players get enough appearances to clear
  `MIN_TIMES_DRAFTED` reliably, while still running quickly since there's no
  network call inside the draft loop.
- **200+ drafts**: diminishing returns — mostly polishing decimal points
  rather than changing who looks good/bad.

This also depends directly on `NOISE_STD` / `POINTS_NOISE_STD` in
`mock_draft_simulator.py` — that setting *is* the variance you're averaging
out, so a higher noise value needs more drafts to reach the same precision.

## Known limitations

- **Name matching** between nflreadpy and the ADP API is done by normalizing
  player names (lowercased, suffixes/punctuation stripped) since the two
  sources don't share a common player ID. This mostly works but can
  occasionally mismatch or miss players with unusual name formatting.
- **Rookie projections are a rough estimate**, not real scouting data see
  the Data Sources section above.
- **Team grading uses last season's actual points** for veterans, which is a
  backward-looking number, not a forecast for the season the ADP is drafted
  for.
- **Batch value analysis reflects the AI drafters' behavior, not necessarily
  real-world draft inefficiency.** With `AI_DRAFT_STRATEGY = "points"`, the
  value report mostly shows which players the noisy points-based AI happens
  to draft inconsistently. Switch to `AI_DRAFT_STRATEGY = "adp"` in
  `mock_draft_simulator.py` for a value analysis closer to real market ADP.

## Possible next steps

- Swap in a real projections API (FantasyPros, Fantasy Nerds, SportsDataIO)
  for both veterans and rookies instead of last season's actuals.
- Add K/DST support if your league starts those positions.
- Export the mock draft results to CSV for easier post-draft analysis.
- Add a convergence check to `batch_draft_analysis.py` that runs increasing
  batch sizes (10, 20, 40...) and stops once the value rankings stabilize,
  instead of guessing `NUM_DRAFTS` up front.
