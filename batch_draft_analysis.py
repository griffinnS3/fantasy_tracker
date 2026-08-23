"""
Griffin Smith
Batch Mock Draft Analysis
--------------------------
Runs many simulated mock drafts (fully automated, no human input) and
aggregates which players tend to be the best/worst "value" picks -- players
who get drafted later than their production supports (good value) vs.
players who get drafted earlier than their production supports (bad value).

Why this needs multiple drafts: mock_draft_simulator.py's AI drafters use
some randomness (NOISE_STD / POINTS_NOISE_STD), so the same player doesn't
go at the exact same pick every time -- they might go pick 24 in one draft
and pick 41 in another. Running many drafts and looking at where a player
*typically* gets taken, versus what they typically produce, is what surfaces
a real going-rate rather than a single noisy draft's results.

"Value" is computed relative to an expected-points-by-draft-slot curve fit
SEPARATELY FOR EACH POSITION across all the simulated picks (not vs. ADP,
and not pooled across positions) -- this avoids QBs looking like automatic
"great value" just because they score more raw points per roster spot than
RB/WR/TE (only one QB starts per team, so QBs bank points other positions
can't match at the same draft slot). Fitting one curve per position means a
QB's value is only ever measured against other QBs taken around the same
pick, not against the whole player pool.

Run this from the same directory as adp_vs_fantasy_points.py and
mock_draft_simulator.py.

Requirements:
    pip install nflreadpy pandas matplotlib requests adjustText numpy --break-system-packages
"""

import numpy as np
import pandas as pd

from adp_vs_fantasy_points import build_merged_dataset
from mock_draft_simulator import simulate_draft, NUM_TEAMS

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
NUM_DRAFTS = 100
BASE_SEED = None     # each draft uses BASE_SEED + draft_num for reproducibility; set to None for fully random runs each time
TOP_N = 15          # how many best/worst value players to show
MIN_TIMES_DRAFTED = 3   # ignore players drafted in fewer than this many of the N drafts (too little signal)


def run_batch_drafts(data: pd.DataFrame, num_drafts: int = NUM_DRAFTS) -> pd.DataFrame:
    """Run several simulated drafts and return one row per pick per draft."""
    all_picks = []

    for draft_num in range(1, num_drafts + 1):
        seed = None if BASE_SEED is None else BASE_SEED + draft_num
        board, _ = simulate_draft(
            data,
            num_teams=NUM_TEAMS,
            seed=seed,
            human_teams=set(),   # fully simulated -- no input() prompts during batch runs
            verbose=False,        # suppress per-pick printing across N drafts
        )
        for pick in board:
            pick = dict(pick)
            pick["draft_num"] = draft_num
            all_picks.append(pick)

        print(f"Completed draft {draft_num}/{num_drafts}")

    return pd.DataFrame(all_picks)


def fit_expected_points_curve(all_picks: pd.DataFrame) -> dict:
    """
    Fit points ~= a * overall_pick^b SEPARATELY for each position, giving an
    "expected points for a player at this position, taken at this pick number"
    baseline. Fitting one curve across all positions combined would bias
    QBs toward always looking like great value (they score more points per
    roster spot than RB/WR/TE, since only one QB starts per team, so a single
    pooled curve underestimates QB expectations and overestimates everyone
    else's) -- fitting per-position keeps players compared only against
    others at the same position.

    Returns a dict of {position: expected_points_fn}.
    """
    curves = {}

    for position, group in all_picks.groupby("position"):
        valid = group[group["points"] > 0]
        if len(valid) < 10:
            # Not enough picks at this position to fit a reliable curve --
            # fall back to the overall (all-position) curve for these players.
            continue

        log_pick = np.log(valid["overall_pick"])
        log_points = np.log(valid["points"])
        slope, intercept = np.polyfit(log_pick, log_points, 1)
        curves[position] = (slope, intercept)

    # Fallback curve pooling all positions, used only if a specific position
    # didn't have enough data to fit its own curve above.
    valid_all = all_picks[all_picks["points"] > 0]
    fallback_slope, fallback_intercept = np.polyfit(
        np.log(valid_all["overall_pick"]), np.log(valid_all["points"]), 1
    )
    curves["__fallback__"] = (fallback_slope, fallback_intercept)

    def expected_points(pick: float, position: str) -> float:
        slope, intercept = curves.get(position, curves["__fallback__"])
        return float(np.exp(intercept) * pick ** slope)

    return expected_points


def analyze_value(all_picks: pd.DataFrame) -> pd.DataFrame:
    expected_points = fit_expected_points_curve(all_picks)

    all_picks = all_picks.copy()
    all_picks["expected_points"] = all_picks.apply(
        lambda row: expected_points(row["overall_pick"], row["position"]), axis=1
    )
    all_picks["value"] = all_picks["points"] - all_picks["expected_points"]

    summary = (
        all_picks.groupby(["player", "position", "is_rookie"])
        .agg(
            times_drafted=("draft_num", "count"),
            avg_pick=("overall_pick", "mean"),
            pick_std=("overall_pick", "std"),
            avg_points=("points", "mean"),
            avg_value=("value", "mean"),
        )
        .reset_index()
    )
    summary["pick_std"] = summary["pick_std"].fillna(0)
    summary = summary[summary["times_drafted"] >= MIN_TIMES_DRAFTED]

    return summary.sort_values("avg_value", ascending=False)


def print_value_report(summary: pd.DataFrame, num_drafts: int):
    def fmt_rows(rows):
        for _, row in rows.iterrows():
            tag = " (R)" if row["is_rookie"] else ""
            print(
                f"  {row['player'] + tag:<28} {row['position']:<3} "
                f"avg pick {row['avg_pick']:>6.1f} (±{row['pick_std']:.1f})   "
                f"avg pts {row['avg_points']:>7.1f}   "
                f"value {row['avg_value']:+7.1f}   "
                f"drafted {int(row['times_drafted'])}/{num_drafts}"
            )

    print(f"\n=== BEST VALUE PICKS (across {num_drafts} drafts) ===")
    print("Players who outproduce where they typically get drafted:\n")
    fmt_rows(summary.head(TOP_N))

    print(f"\n=== WORST VALUE PICKS (across {num_drafts} drafts) ===")
    print("Players who get drafted earlier than their production supports:\n")
    fmt_rows(summary.tail(TOP_N).sort_values("avg_value"))

    print(
        "\nNote: 'value' compares each player's points to the typical points "
        "produced by OTHER PLAYERS AT THE SAME POSITION taken around the same "
        "overall pick number, based on a curve fit per position across all the "
        "simulated picks -- not vs. ADP, and not pooled across positions (which "
        "would otherwise make QBs look artificially like great value). Rookie "
        "points are themselves an ADP-based estimate (see adp_vs_fantasy_points.py), "
        "so rookie value numbers carry an extra layer of uncertainty."
    )


if __name__ == "__main__":
    data = build_merged_dataset()
    picks = run_batch_drafts(data, num_drafts=NUM_DRAFTS)
    value_summary = analyze_value(picks)
    print_value_report(value_summary, NUM_DRAFTS)