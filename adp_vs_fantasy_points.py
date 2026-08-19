"""
ADP vs. Fantasy Points Dot Plot
--------------------------------
Combines:
  - Season fantasy points from nflverse (via nflreadpy)
  - Average Draft Position (ADP) from the Fantasy Football Calculator API

Produces a scatter/dot plot: ADP on the x-axis, fantasy points on the y-axis.
Points drafted early (low ADP) that scored a lot of fantasy points land in the
top-left. Late-round players who outscored expectations ("sleepers") also show
up in the top-right, while early picks that underperformed show up bottom-left.

Requirements:
    pip install nflreadpy pandas matplotlib requests adjustText --break-system-packages

Note: nflreadpy replaced the older, now-unmaintained nfl_data_py package.
nfl_data_py had fallen behind on newer nflverse data file locations, which
caused 404 errors when requesting recent seasons. nflreadpy is the official,
actively maintained successor from the nflverse team.
"""

import re
import sys

import matplotlib.pyplot as plt
import nflreadpy as nfl
import numpy as np
import pandas as pd
import requests
from adjustText import adjust_text

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
SEASON = 2025          # season of actual stats to plot (most recently completed season)
ADP_YEAR = 2026         # season the ADP data is drafted for
SCORING = "ppr"          # one of: "standard", "ppr", "half-ppr", "2qb", "dynasty", "rookie"
TEAMS = 12               # league size used for the ADP calculation
POSITIONS_TO_PLOT = {"QB", "RB", "WR", "TE"}
FANTASY_POINTS_COL = "fantasy_points_ppr"   # use "fantasy_points" for standard scoring
MAX_PLAYERS_TO_LABEL = 120   # cap on how many players appear on the chart (by best ADP)
LABEL_FONT_SIZE = 7


def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes/punctuation so names match across sources."""
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = re.sub(r"[.\']", "", name)                     # remove periods/apostrophes
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)    # remove suffixes
    name = re.sub(r"[^a-z\s]", "", name)                   # drop any remaining punctuation
    name = re.sub(r"\s+", " ", name).strip()
    return name


def get_season_fantasy_points(season: int) -> pd.DataFrame:
    """Pull weekly stats from nflverse (via nflreadpy) and sum to season totals per player."""
    weekly = nfl.load_player_stats(seasons=[season]).to_pandas()

    season_totals = (
        weekly.groupby(["player_id", "player_display_name", "position"], as_index=False)[
            FANTASY_POINTS_COL
        ]
        .sum()
        .rename(columns={FANTASY_POINTS_COL: "fantasy_points"})
    )

    season_totals = season_totals[season_totals["position"].isin(POSITIONS_TO_PLOT)]
    season_totals["name_key"] = season_totals["player_display_name"].apply(normalize_name)
    return season_totals


def get_adp(year: int, teams: int, scoring: str) -> pd.DataFrame:
    """Pull ADP data from the Fantasy Football Calculator public API."""
    url = f"https://fantasyfootballcalculator.com/api/v1/adp/{scoring}"
    params = {"teams": teams, "year": year, "position": "all"}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    adp_df = pd.DataFrame(payload["players"])
    adp_df = adp_df.rename(columns={"name": "player_name", "position": "position"})
    adp_df["name_key"] = adp_df["player_name"].apply(normalize_name)
    return adp_df[["name_key", "player_name", "position", "adp"]]


def estimate_rookie_projection(merged: pd.DataFrame) -> pd.DataFrame:
    """
    Fill in a projected-points estimate for players with no prior-season stats
    (i.e. rookies -- they haven't played an NFL game yet, so there's no real
    stats source for them). The estimate is a simple power-law curve
    (points ~= a * adp^b) fit on veteran players, using ADP as the only
    signal -- it's a rough proxy, not a real projection, and is flagged as
    such via the "points_type" column.
    """
    merged = merged.copy()
    merged["is_rookie"] = merged["fantasy_points"].isna()

    veterans = merged[~merged["is_rookie"] & (merged["fantasy_points"] > 0)]
    if len(veterans) < 10:
        # Not enough data to fit a curve -- leave rookies as NaN rather than guess wildly.
        merged["points_type"] = np.where(merged["is_rookie"], "no data", "actual")
        return merged

    log_adp = np.log(veterans["adp"])
    log_points = np.log(veterans["fantasy_points"])
    slope, intercept = np.polyfit(log_adp, log_points, 1)

    def project(adp: float) -> float:
        return float(np.exp(intercept) * adp ** slope)

    rookie_mask = merged["is_rookie"]
    merged.loc[rookie_mask, "fantasy_points"] = merged.loc[rookie_mask, "adp"].apply(project)
    merged["points_type"] = np.where(merged["is_rookie"], "projected (rookie est.)", "actual")

    # Rookies won't have a player_id / display name / position from the stats
    # source since they weren't matched -- fall back to the ADP-side values.
    merged["player_display_name"] = merged["player_display_name"].fillna(merged["player_name"])
    merged["position_stats"] = merged["position_stats"].fillna(merged["position_adp"])

    return merged


def build_merged_dataset() -> pd.DataFrame:
    points_df = get_season_fantasy_points(SEASON)
    adp_df = get_adp(ADP_YEAR, TEAMS, SCORING)

    # Left merge from ADP so rookies (who have no prior-season stats) are kept
    # instead of silently dropped by an inner join.
    merged = pd.merge(
        adp_df,
        points_df,
        on="name_key",
        how="left",
        suffixes=("_adp", "_stats"),
    )

    if merged.empty:
        sys.exit(
            "No players matched between the ADP and stats datasets. "
            "Check that SEASON / ADP_YEAR / SCORING are set correctly."
        )

    merged = estimate_rookie_projection(merged)
    merged = merged[merged["position_stats"].isin(POSITIONS_TO_PLOT)].reset_index(drop=True)

    return merged


def plot_adp_vs_points(df: pd.DataFrame) -> None:
    # Keep the chart readable: limit to the players with the best (lowest) ADP.
    # Late-round/undrafted players add clutter without adding much insight here.
    df = df.sort_values("adp").head(MAX_PLAYERS_TO_LABEL).copy()

    fig, ax = plt.subplots(figsize=(20, 14))

    position_colors = {
        "QB": "#d62728",
        "RB": "#1f77b4",
        "WR": "#2ca02c",
        "TE": "#ff7f0e",
    }

    for position, color in position_colors.items():
        vets = df[(df["position_stats"] == position) & (~df["is_rookie"])]
        rookies = df[(df["position_stats"] == position) & (df["is_rookie"])]

        ax.scatter(
            vets["adp"],
            vets["fantasy_points"],
            label=position,
            color=color,
            alpha=0.8,
            edgecolors="white",
            linewidths=0.6,
            s=55,
            zorder=3,
        )
        ax.scatter(
            rookies["adp"],
            rookies["fantasy_points"],
            label=f"{position} (rookie, est.)",
            color=color,
            alpha=0.9,
            edgecolors="black",
            linewidths=0.8,
            marker="*",
            s=140,
            zorder=3,
        )

    # Label every plotted player, then let adjustText spread the labels apart
    # so they don't overlap each other or the dots.
    texts = []
    for _, row in df.iterrows():
        texts.append(
            ax.text(
                row["adp"],
                row["fantasy_points"],
                row["player_display_name"],
                fontsize=LABEL_FONT_SIZE,
                zorder=4,
            )
        )

    adjust_text(
        texts,
        ax=ax,
        expand_points=(1.4, 1.6),
        expand_text=(1.1, 1.3),
        arrowprops=dict(arrowstyle="-", color="grey", lw=0.5, alpha=0.6),
    )

    ax.set_xlabel(f"Average Draft Position ({ADP_YEAR}, {TEAMS}-team {SCORING.upper()})")
    ax.set_ylabel(f"{SEASON} Season Fantasy Points (rookies: ADP-based estimate, marked with ★)")
    ax.set_title(
        f"Fantasy Points vs. ADP — {SEASON} Season "
        f"(top {len(df)} players by ADP)"
    )
    ax.invert_xaxis()  # ADP 1 (first pick) on the left
    ax.legend(title="Position")
    ax.grid(True, linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig("adp_vs_fantasy_points.png", dpi=200)
    print("Saved chart to adp_vs_fantasy_points.png")
    plt.show()


if __name__ == "__main__":
    data = build_merged_dataset()
    plot_adp_vs_points(data)
