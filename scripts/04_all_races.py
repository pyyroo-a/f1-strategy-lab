"""
Step 4: Every race of the season

Hungary on its own couldnt tell us which tyre degrades fastest, because each
tyre was only used at one point in the race. So here we pool every race
together. Different circuits use tyres at different times, so that should
break it apart.

It did break that apart, but hards STILL looked worse than softs. Turns out
teams pick hards because the track is harsh on tyres. So the hard pile was
full of Barcelona and the soft pile was full of Canada, and we were basically
comparing tracks not tyres.

This saves every stint to data/stints_2026.csv so later files can just read
it instead of downloading everything again. The simulator uses it for how many
laps each race is.

First run is slow (a few minutes) because it downloads every race, after that
its cached and fast.

Steps 5 and 6 do everything this does and more, but this one is the simplest
version so its worth reading first.
"""

import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---- settings ----
YEAR = 2026

STARTING_FUEL_KG = 72.0
SECONDS_PER_KG = 0.03

# raised from 6 in step 3. short stints gave slopes that jumped all over the
# place and messed up the medians. we lose some stints but its worth it
MIN_CLEAN_LAPS = 8
DRY_COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

OUT_CSV = Path("data/stints_2026.csv")
# ------------------

fastf1.Cache.enable_cache("cache")

# make sure the data folder exists before we save into it
OUT_CSV.parent.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# work out which races have actually happened
# ---------------------------------------------------------------------------

schedule = fastf1.get_event_schedule(YEAR)

# round 0 is pre season testing so drop it,
# and only keep races with a date in the past
races = schedule[
    (schedule["RoundNumber"] > 0)
    & (schedule["EventDate"] < pd.Timestamp.now())
]

print(f"Found {len(races)} completed races in {YEAR}\n")


# ---------------------------------------------------------------------------
# measure every stint of every race
# ---------------------------------------------------------------------------

all_stints = []

for _, event in races.iterrows():
    round_no = int(event["RoundNumber"])
    name = event["EventName"]

    # a race can fail to load (data not out yet, internet, whatever).
    # one bad race shouldnt stop everything so we just skip it and carry on
    try:
        session = fastf1.get_session(YEAR, round_no, "R")
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as err:
        print(f"  R{round_no:02d} {name}: FAILED to load ({err})")
        continue

    laps = session.laps
    if laps is None or laps.empty:
        print(f"  R{round_no:02d} {name}: no lap data")
        continue

    # every race is a different length so fuel burn per lap is different.
    # a 44 lap race burns way more per lap than a 70 lap one
    total_laps = int(laps["LapNumber"].max())
    kg_per_lap = STARTING_FUEL_KG / total_laps

    # same filters as before, green flag, no pit laps, dry tyres only
    clean = laps[
        laps["PitInTime"].isna()
        & laps["PitOutTime"].isna()
        & (laps["TrackStatus"] == "1")
        & laps["IsAccurate"]
        & laps["Compound"].isin(DRY_COMPOUNDS)
    ].copy()

    if clean.empty:
        print(f"  R{round_no:02d} {name}: no clean dry laps (wet race?)")
        continue

    clean["LapTimeSec"] = clean["LapTime"].dt.total_seconds()
    clean["FuelCorrectedSec"] = clean["LapTimeSec"] - (
        (total_laps - clean["LapNumber"]) * kg_per_lap * SECONDS_PER_KG
    )

    stints_here = 0

    for (driver, stint_no), stint in clean.groupby(["Driver", "Stint"]):
        if len(stint) < MIN_CLEAN_LAPS:
            continue

        age = stint["TyreLife"].to_numpy(dtype=float)
        times = stint["FuelCorrectedSec"].to_numpy(dtype=float)

        slope, intercept = np.polyfit(age, times, 1)

        all_stints.append(
            {
                "round": round_no,
                "race": name.replace(" Grand Prix", ""),
                "race_laps": total_laps,
                "driver": driver,
                "stint": int(stint_no),
                "compound": stint["Compound"].iloc[0],
                "clean_laps": len(stint),
                "start_lap": int(stint["LapNumber"].min()),
                # where in the race the stint started, from 0 to 1.
                # fairer than lap number because lap 30 is late in a 44 lap
                # race but only halfway in a 70 lap one
                "race_fraction": stint["LapNumber"].min() / total_laps,
                "deg_per_lap": slope,
                "pace_at_age5": slope * 5 + intercept,
            }
        )
        stints_here += 1

    print(f"  R{round_no:02d} {name}: {stints_here} stints "
          f"({total_laps} laps)")


stints = pd.DataFrame(all_stints)
stints.to_csv(OUT_CSV, index=False)

print(f"\nSaved {len(stints)} stints to {OUT_CSV}")
print(f"  {stints['race'].nunique()} races, {stints['driver'].nunique()} drivers\n")


# ---------------------------------------------------------------------------
# did pooling the races actually fix the problem from step 3?
# ---------------------------------------------------------------------------

# chop the race into thirds (early, mid, late) based on where each stint started.
# the top is 1.01 not 1.0 because pd.cut leaves out the top edge, so a stint
# starting on the last lap would go missing
stints["phase"] = pd.cut(
    stints["race_fraction"],
    [0, 0.33, 0.66, 1.01],
    labels=["early", "mid", "late"],
)

print("=" * 60)
print("CONFOUND CHECK: how many stints in each compound/phase box?")
print("=" * 60)
print(pd.crosstab(stints["phase"], stints["compound"]).to_string())
print()
print("At Hungary alone several of these boxes were 0 or 1, which is why")
print("we couldn't separate 'which tyre' from 'when in the race'.")
print("The more evenly filled this table is, the better.\n")

print("=" * 60)
print("DEGRADATION BY COMPOUND (all races pooled)")
print("=" * 60)

# median everywhere in this project, one freak stint can wreck an average
summary = stints.groupby("compound").agg(
    stints=("deg_per_lap", "size"),
    median_deg=("deg_per_lap", "median"),
)
summary = summary.reindex([c for c in DRY_COMPOUNDS if c in summary.index])
print(summary.to_string(float_format=lambda x: f"{x:.3f}"))

print()
print("=" * 60)
print("SAME THING, SPLIT BY RACE PHASE")
print("=" * 60)
print("If the compound ordering is the same in every row, the compound")
print("effect is real. If it flips around, phase was doing the work.\n")

by_phase = pd.crosstab(
    stints["phase"], stints["compound"],
    values=stints["deg_per_lap"], aggfunc="median",
)
by_phase = by_phase[[c for c in DRY_COMPOUNDS if c in by_phase.columns]]
print(by_phase.to_string(float_format=lambda x: f"{x:.3f}"))

print()
print("=" * 60)
print("DEGRADATION BY CIRCUIT")
print("=" * 60)
per_race = stints.groupby("race").agg(
    stints=("deg_per_lap", "size"),
    median_deg=("deg_per_lap", "median"),
).sort_values("median_deg", ascending=False)
print(per_race.to_string(float_format=lambda x: f"{x:.3f}"))
