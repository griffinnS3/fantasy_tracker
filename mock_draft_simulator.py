"""
Griffin Smith
12-Team Mock Draft Simulator
-----------------------------
Uses the same ADP + fantasy points dataset built in adp_vs_fantasy_points.py
to simulate a 12-team snake draft.

Draft logic:
  - Each team's open roster slots determine which positions it can draft
    (required starters first, then FLEX, then bench).
  - Among eligible players, the "drafter" picks based on ADP with a bit of
    random noise added, to mimic the natural variance of real human drafters
    (nobody drafts in perfect ADP order -- there are reaches and falls).
  - This uses ADP to drive draft order/behavior (or points, if
    AI_DRAFT_STRATEGY = "points"). Rookies have no prior-season stats, so
    their "points" value is an ADP-based estimate from adp_vs_fantasy_points.py,
    flagged in the data and tagged "(R)" wherever a rookie appears in output.

Run this from the same directory as adp_vs_fantasy_points.py -- it imports
that file's build_merged_dataset() function to reuse the ADP + points pull.

Requirements:
    pip install nflreadpy pandas matplotlib requests adjustText numpy --break-system-packages
"""

import numpy as np
import pandas as pd

from adp_vs_fantasy_points import build_merged_dataset

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
NUM_TEAMS = 12
NOISE_STD = 4.0            # ADP noise: bigger = more "reaches"/"falls" vs strict ADP order; 0 = pure ADP order
POINTS_NOISE_STD = 15.0    # fantasy-points noise: bigger = more deviation from strict points order
RANDOM_SEED = None          # set an int (e.g. 42) for a reproducible draft

AI_DRAFT_STRATEGY = "ADP"  # "points" = AI drafts by last season's fantasy points, "adp" = by ADP

HUMAN_TEAMS = {1}     # team numbers (1-NUM_TEAMS) controlled by a person; empty set = fully simulated
NUM_SHOWN_CANDIDATES = 15  # how many top-available players to show a human drafter each pick

ROSTER_SLOTS = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "FLEX": 1,    # RB/WR/TE eligible
    "BENCH": 6,
}
FLEX_ELIGIBLE = {"RB", "WR", "TE"}


def get_eligible_positions(slots_filled: dict) -> set:
    """Positions a team can still draft for, given its open roster slots."""
    open_positions = set()

    for pos in ("QB", "RB", "WR", "TE"):
        if slots_filled.get(pos, 0) < ROSTER_SLOTS.get(pos, 0):
            open_positions.add(pos)

    if slots_filled.get("FLEX", 0) < ROSTER_SLOTS.get("FLEX", 0):
        open_positions |= FLEX_ELIGIBLE

    if slots_filled.get("BENCH", 0) < ROSTER_SLOTS.get("BENCH", 0):
        open_positions |= {"QB", "RB", "WR", "TE"}

    return open_positions or {"QB", "RB", "WR", "TE"}


def assign_slot(position: str, slots_filled: dict) -> str:
    """Decide which roster slot a newly drafted player fills."""
    if slots_filled.get(position, 0) < ROSTER_SLOTS.get(position, 0):
        return position
    if position in FLEX_ELIGIBLE and slots_filled.get("FLEX", 0) < ROSTER_SLOTS.get("FLEX", 0):
        return "FLEX"
    return "BENCH"


def human_pick(candidates: pd.DataFrame, team: int, overall_pick: int, rnd: int) -> pd.Index:
    """Show the human drafter the top available eligible players and let them choose."""
    sort_col = "adp" if AI_DRAFT_STRATEGY == "adp" else "fantasy_points"
    ascending = AI_DRAFT_STRATEGY == "adp"  # low ADP is good, high points is good
    ranked = candidates.sort_values(sort_col, ascending=ascending).head(NUM_SHOWN_CANDIDATES).reset_index()

    print(f"\n--- Pick {overall_pick} (Round {rnd}) — YOUR PICK (Team {team}) ---")
    print(f"{'#':<3} {'Player':<28} {'Pos':<4} {'ADP':<7} {'Points (proj. for rookies)'}")
    for i, row in ranked.iterrows():
        tag = " (R)" if row.get("is_rookie") else ""
        print(f"{i:<3} {row['player_display_name'] + tag:<28} {row['position_stats']:<4} "
              f"{row['adp']:<7.1f} {row['fantasy_points']:.1f}")

    while True:
        choice = input(
            "\nEnter a number to draft that player, or type part of a player's "
            "name to search: "
        ).strip()

        if choice.isdigit() and int(choice) in ranked.index:
            return ranked.loc[int(choice), "index"]

        # Fall back to a name search across ALL eligible candidates, not just
        # the ones shown, in case the human wants someone further down the list.
        matches = candidates[
            candidates["player_display_name"].str.contains(choice, case=False, na=False)
        ]
        if len(matches) == 1:
            return matches.index[0]
        elif len(matches) > 1:
            print("Multiple matches found, be more specific:")
            print(matches[["player_display_name", "position_stats", "adp"]].to_string(index=False))
        else:
            print("No eligible player found matching that. Try again.")


def simulate_draft(
    players: pd.DataFrame,
    num_teams: int = NUM_TEAMS,
    seed=None,
    human_teams: set = None,
    verbose: bool = True,
):
    """
    Run one simulated draft.

    human_teams: overrides the module-level HUMAN_TEAMS when provided (e.g. pass
        set() for a fully-automated run, used by batch analysis scripts).
    verbose: when False, suppresses the live pick-by-pick print output -- useful
        when running many drafts back to back.
    """
    if human_teams is None:
        human_teams = HUMAN_TEAMS

    rng = np.random.default_rng(seed)
    total_rounds = sum(ROSTER_SLOTS.values())

    available = players.sort_values("adp").reset_index(drop=True).copy()
    teams = {
        team: {"slots_filled": {pos: 0 for pos in ROSTER_SLOTS}, "roster": []}
        for team in range(1, num_teams + 1)
    }

    draft_board = []
    overall_pick = 0

    for rnd in range(1, total_rounds + 1):
        order = range(1, num_teams + 1) if rnd % 2 == 1 else range(num_teams, 0, -1)

        for team in order:
            if available.empty:
                break

            overall_pick += 1
            eligible = get_eligible_positions(teams[team]["slots_filled"])
            candidates = available[available["position_stats"].isin(eligible)]
            if candidates.empty:
                candidates = available  # fallback if the roster shape runs out of eligible players

            if team in human_teams:
                pick_idx = human_pick(candidates, team, overall_pick, rnd)
            elif AI_DRAFT_STRATEGY == "points":
                noisy_value = candidates["fantasy_points"] + rng.normal(0, POINTS_NOISE_STD, size=len(candidates))
                pick_idx = noisy_value.idxmax()  # higher points is better
            else:
                noisy_adp = candidates["adp"] + rng.normal(0, NOISE_STD, size=len(candidates))
                pick_idx = noisy_adp.idxmin()  # lower ADP is better

            player = available.loc[pick_idx]
            is_rookie = bool(player.get("is_rookie"))
            rookie_tag = " (R)" if is_rookie else ""

            slot = assign_slot(player["position_stats"], teams[team]["slots_filled"])
            teams[team]["slots_filled"][slot] += 1
            teams[team]["roster"].append(
                {
                    "slot": slot,
                    "player": player["player_display_name"],
                    "position": player["position_stats"],
                    "adp": round(player["adp"], 1),
                    "points": round(player["fantasy_points"], 1),
                    "is_rookie": is_rookie,
                    "overall_pick": overall_pick,
                }
            )

            draft_board.append(
                {
                    "overall_pick": overall_pick,
                    "round": rnd,
                    "team": team,
                    "player": player["player_display_name"],
                    "position": player["position_stats"],
                    "adp": round(player["adp"], 1),
                    "points": round(player["fantasy_points"], 1),
                    "is_rookie": is_rookie,
                }
            )

            available = available.drop(pick_idx)

            if verbose and team not in human_teams:
                print(
                    f"Pick {overall_pick:>3} (Rd {rnd:>2}) - Team {team:>2} drafts: "
                    f"{player['player_display_name']}{rookie_tag} ({player['position_stats']}, ADP {player['adp']:.1f})"
                )

    return draft_board, teams


def print_draft_board(draft_board):
    print("\n=== DRAFT BOARD ===")
    for pick in draft_board:
        tag = " (R)" if pick.get("is_rookie") else ""
        print(
            f"Pick {pick['overall_pick']:>3} (Rd {pick['round']:>2}) "
            f"- Team {pick['team']:>2}: {pick['player']}{tag} ({pick['position']}, ADP {pick['adp']})"
        )


def print_team_rosters(teams):
    print("\n=== FINAL ROSTERS (actual last-season points; rookies use an ADP-based estimate, marked (R)) ===")
    for team, data in teams.items():
        total_points = sum(p["points"] for p in data["roster"])
        print(f"\nTeam {team} — total points: {total_points:.1f}")
        for p in data["roster"]:
            tag = " (R)" if p.get("is_rookie") else ""
            print(
                f"  {p['slot']:<6} {p['player'] + tag:<28} {p['position']:<3} "
                f"ADP {p['adp']:<6} {p['points']} pts"
            )

    ranked = sorted(
        teams.items(),
        key=lambda kv: sum(p["points"] for p in kv[1]["roster"]),
        reverse=True,
    )
    print("\n=== TEAM RANKINGS ===")
    for rank, (team, data) in enumerate(ranked, start=1):
        total_points = sum(p["points"] for p in data["roster"])
        print(f"{rank:>2}. Team {team} — {total_points:.1f} pts")


if __name__ == "__main__":
    data = build_merged_dataset()
    board, teams = simulate_draft(data, num_teams=NUM_TEAMS, seed=RANDOM_SEED)
    print_draft_board(board)
    print_team_rosters(teams)
