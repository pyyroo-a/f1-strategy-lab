"""
Step 3: Every driver in one race

Step 2 only gave us 4 degradation numbers from Norris. Thats not enough to say
anything, one weird stint and we'd never know.

So here we run the exact same thing for every driver in the race and put it all
in one table. Around 60 stints instead of 4.

This is where we first saw hards looking worse than softs, which is backwards.
Turned out at Hungary each tyre was only used at one point in the race
(mediums at the start, hards in the middle, softs at the end) so we couldnt
tell "which tyre" apart from "when in the race".

Output:
  - a table of every stint, worst degradation first
  - a summary per compound
  - a chart showing the spread
"""

import warnings

import fastf1
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---- settings ----
YEAR = 2026
RACE = "Hungary"

STARTING_FUEL_KG = 72.0
SECONDS_PER_KG = 0.03

# a stint needs at least this many clean laps before we trust its slope,
# a line through 3 noisy dots means nothing
MIN_CLEAN_LAPS = 6

# dry tyres only, wet races are a whole different problem
DRY_COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]
# ------------------

fastf1.Cache.enable_cache("cache")

session = fastf1.get_session(YEAR, RACE, "R")
session.load(telemetry=False, weather=False, messages=False)

laps = session.laps
total_laps = int(laps["LapNumber"].max())
kg_per_lap = STARTING_FUEL_KG / total_laps

print(f"{RACE} {YEAR}, {total_laps} laps")
print(f"Fuel: {kg_per_lap:.3f} kg/lap = {kg_per_lap * SECONDS_PER_KG:.3f} s/lap\n")


# ---------------------------------------------------------------------------
# filter and fuel correct every lap, all drivers at once.
# same as step 2 just not only for one driver
# ---------------------------------------------------------------------------

clean = laps[
    laps["PitInTime"].isna()
    & laps["PitOutTime"].isna()
    & (laps["TrackStatus"] == "1")
    & laps["IsAccurate"]
    & laps["Compound"].isin(DRY_COMPOUNDS)
].copy()

clean["LapTimeSec"] = clean["LapTime"].dt.total_seconds()

# same fuel correction as step 2
laps_remaining = total_laps - clean["LapNumber"]
clean["FuelCorrectedSec"] = clean["LapTimeSec"] - (
    laps_remaining * kg_per_lap * SECONDS_PER_KG
)

print(f"{len(laps)} laps total -> {len(clean)} clean dry laps\n")


# ---------------------------------------------------------------------------
# measure every stint
# ---------------------------------------------------------------------------

# one dictionary per stint goes in here, then we turn it into a table at the end
results = []

# grouping by driver AND stint means each group is one driver on one set of tyres
for (driver, stint_no), stint in clean.groupby(["Driver", "Stint"]):

    # skip stints that are too short to fit a proper line
    if len(stint) < MIN_CLEAN_LAPS:
        continue

    age = stint["TyreLife"].to_numpy(dtype=float)
    times = stint["FuelCorrectedSec"].to_numpy(dtype=float)

    slope, intercept = np.polyfit(age, times, 1)

    results.append(
        {
            "driver": driver,
            "stint": int(stint_no),
            "compound": stint["Compound"].iloc[0],
            "clean_laps": len(stint),
            "start_lap": int(stint["LapNumber"].min()),
            "deg_per_lap": slope,
            # pace when the tyre is 5 laps old, so stints can be compared.
            # 5 because the tyre is new-ish but warmed up by then
            "pace_at_age5": slope * 5 + intercept,
        }
    )

# turn the list into a proper table
stints = pd.DataFrame(results)


# ---------------------------------------------------------------------------
# look at the results
# ---------------------------------------------------------------------------

print(f"Measured {len(stints)} stints "
      f"across {stints['driver'].nunique()} drivers\n")

print("=" * 62)
print("EVERY STINT, worst degradation first")
print("=" * 62)
print(
    stints.sort_values("deg_per_lap", ascending=False)
    .to_string(index=False, float_format=lambda x: f"{x:.3f}")
)

print()
print("=" * 62)
print("SUMMARY BY COMPOUND")
print("=" * 62)

# median not average, one freak stint can drag an average way off
# but the median just ignores the extremes
summary = stints.groupby("compound").agg(
    stints=("deg_per_lap", "size"),
    median_deg=("deg_per_lap", "median"),
    min_deg=("deg_per_lap", "min"),
    max_deg=("deg_per_lap", "max"),
    median_pace=("pace_at_age5", "median"),
)

# soft, medium, hard order instead of alphabetical
summary = summary.reindex([c for c in DRY_COMPOUNDS if c in summary.index])

print(summary.to_string(float_format=lambda x: f"{x:.3f}"))
print()
print("median_deg  = typical seconds lost per extra lap on that tyre")
print("median_pace = typical lap time at 5 laps old (lower = faster tyre)")


# ---------------------------------------------------------------------------
# chart: every stint as a dot, grouped by compound
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(figsize=(9, 6))

colours = {"SOFT": "#e2504a", "MEDIUM": "#e8c33f", "HARD": "#8d8d94"}

# one column of dots per compound
for x_pos, compound in enumerate(DRY_COMPOUNDS):
    subset = stints[stints["compound"] == compound]
    if subset.empty:
        continue

    # spread the dots sideways a bit so they dont sit on top of each other.
    # this is called jitter and its only for looks
    jitter = np.random.uniform(-0.12, 0.12, size=len(subset))

    ax.scatter(
        x_pos + jitter,
        subset["deg_per_lap"],
        s=70,
        alpha=0.7,
        color=colours[compound],
        edgecolor="black",
        linewidth=0.5,
        zorder=3,
    )

    # thick black bar at the median so the typical value is easy to see
    median = subset["deg_per_lap"].median()
    ax.plot([x_pos - 0.28, x_pos + 0.28], [median, median],
            color="black", linewidth=2.5, zorder=4)
    ax.text(x_pos + 0.33, median, f"{median:.3f}",
            va="center", fontsize=10, fontweight="bold")

# line at zero. anything below it means the tyre got FASTER with age
# which shouldnt happen, so those stints are worth looking at
ax.axhline(0, color="black", linewidth=0.8, linestyle=":", zorder=1)

ax.set_xticks(range(len(DRY_COMPOUNDS)))
ax.set_xticklabels(DRY_COMPOUNDS)
ax.set_ylabel("Degradation (seconds lost per lap)")
ax.set_title(f"{RACE} {YEAR} - degradation by compound\n"
             f"one dot per stint, black bar = median")
ax.grid(axis="y", alpha=0.3)

out = f"outputs/03_{YEAR}_{RACE}_by_compound.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nSaved plot to {out}")

plt.show()
