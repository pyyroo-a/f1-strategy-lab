"""
Step 5: Track evolution

Up to step 4 we fitted one line per stint and blamed all of it on tyre age.
But two things are happening at the same time during a stint:

    tyre gets older   -> car gets SLOWER
    track rubbers in  -> car gets FASTER

Cars lay rubber on the track and rubber grips rubber, so the track basically
gets grippier as the race goes on. Our slope was both of those mashed together
so it came out too small. Canada and China even came out NEGATIVE, meaning the
tyre got faster with age, which is impossible. Thats how we knew something was
missing.

Fuel we could look up. Track evolution we cant, its different at every track,
so we have to measure it from the data.

How we split the two apart
--------------------------
Inside one stint, tyre age and lap number go up together every lap, so you
cant tell them apart. What saves us is that drivers pit at different times.

On lap 30 one driver might be on 18 lap old tyres and another on 5 lap old
tyres. Same lap, same track, different tyre age. So any gap between them has
to be the tyres.

So we fit every clean lap of the race at once:

    lap time = (tyre age effect) + (lap number effect)
             + (which driver)  + (which compound)

and let the maths work out how much belongs to each. Driver and compound are in
there so it doesnt think "verstappen is fast" or "softs are fast" is a tyre age
thing.

Then we take the track effect away from every lap and measure degradation the
same way as step 4, so the numbers can be compared.

What we found: it fixed China and got every circuit closer to real numbers,
but it couldnt fix soft vs hard. The track is the same for everyone so it moves
every stint in a race by the same amount, and that cant change the order.
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

MIN_CLEAN_LAPS = 8
DRY_COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

OUT_CSV = Path("data/stints_2026_corrected.csv")
# ------------------

fastf1.Cache.enable_cache("cache")
OUT_CSV.parent.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# the new bit: fit tyre age and lap number at the same time
# ---------------------------------------------------------------------------

def fit_race(clean):
    """Fit one whole race at once and give back (deg_per_lap, evo_per_lap).

    deg_per_lap = seconds lost per extra lap of tyre age (should be positive)
    evo_per_lap = seconds gained per lap as the race goes on (should be
                  negative, because the track getting faster means lap times
                  going down)
    """

    # a dummy column is basically a yes/no column. get_dummies turns the
    # Driver column into one column per driver with a 1 or 0.
    # this gives every driver their own baseline pace, so a fast car doesnt
    # get mistaken for a good tyre.
    #
    # drop_first=True leaves one driver out on purpose. that driver is the
    # reference and everyone else is measured against them, without it the
    # maths doesnt have one answer
    driver_cols = pd.get_dummies(clean["Driver"], prefix="drv", drop_first=True)

    # same thing for compound. softs are just faster than hards at any age,
    # that has nothing to do with degradation or the track
    compound_cols = pd.get_dummies(clean["Compound"], prefix="cmp", drop_first=True)

    # the two columns we actually care about go on the end
    X = pd.concat(
        [driver_cols, compound_cols, clean[["TyreLife", "LapNumber"]]],
        axis=1,
    ).astype(float)

    # column of all 1s, this is the starting lap time everything else adds on to
    X.insert(0, "const", 1.0)

    y = clean["FuelCorrectedSec"].to_numpy(dtype=float)

    # lstsq is like polyfit's bigger brother. polyfit fits a line with one x,
    # lstsq fits with loads of x columns at once and gives back one number per column
    coef, *_ = np.linalg.lstsq(X.to_numpy(), y, rcond=None)

    # grab the two numbers we want by finding where their columns are
    deg = coef[X.columns.get_loc("TyreLife")]
    evo = coef[X.columns.get_loc("LapNumber")]

    return deg, evo


# ---------------------------------------------------------------------------
# which races have happened
# ---------------------------------------------------------------------------

schedule = fastf1.get_event_schedule(YEAR)
races = schedule[
    (schedule["RoundNumber"] > 0)
    & (schedule["EventDate"] < pd.Timestamp.now())
]

print(f"Found {len(races)} completed races in {YEAR}\n")

all_stints = []
evolution_rows = []

for _, event in races.iterrows():
    round_no = int(event["RoundNumber"])
    name = event["EventName"]

    try:
        session = fastf1.get_session(YEAR, round_no, "R")
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as err:
        print(f"  R{round_no:02d} {name}: FAILED to load ({err})")
        continue

    laps = session.laps
    if laps is None or laps.empty:
        continue

    total_laps = int(laps["LapNumber"].max())
    kg_per_lap = STARTING_FUEL_KG / total_laps

    # same filters and fuel correction as step 4
    clean = laps[
        laps["PitInTime"].isna()
        & laps["PitOutTime"].isna()
        & (laps["TrackStatus"] == "1")
        & laps["IsAccurate"]
        & laps["Compound"].isin(DRY_COMPOUNDS)
    ].copy()

    if len(clean) < 100:
        print(f"  R{round_no:02d} {name}: only {len(clean)} clean laps, skipping")
        continue

    clean["LapTimeSec"] = clean["LapTime"].dt.total_seconds()
    clean["FuelCorrectedSec"] = clean["LapTimeSec"] - (
        (total_laps - clean["LapNumber"]) * kg_per_lap * SECONDS_PER_KG
    )

    # safety check. this only works if tyre age and lap number DONT move
    # perfectly together, which staggered pit stops make sure of.
    # corr gives a number from -1 to 1 for how tightly they move together,
    # 1.0 would mean we cant split them at all. under about 0.9 is fine
    lock = clean["TyreLife"].corr(clean["LapNumber"])

    deg, evo = fit_race(clean)

    evolution_rows.append(
        {
            "round": round_no,
            "race": name.replace(" Grand Prix", ""),
            "clean_laps": len(clean),
            "lockstep": lock,
            "field_deg": deg,
            "evo_per_lap": evo,
            # total seconds the track gave back from lap 1 to the end
            "evo_total_sec": evo * total_laps,
        }
    )

    # take the track effect away from every lap.
    # evo is negative when the track gets faster, so taking it away ADDS time
    # back onto the later laps
    clean["TrackCorrectedSec"] = clean["FuelCorrectedSec"] - evo * clean["LapNumber"]

    # measure each stint again on the corrected times, same as step 4
    stints_here = 0
    for (driver, stint_no), stint in clean.groupby(["Driver", "Stint"]):
        if len(stint) < MIN_CLEAN_LAPS:
            continue

        age = stint["TyreLife"].to_numpy(dtype=float)

        # fit the same stint twice, before and after, so we can see what changed
        old_slope, _ = np.polyfit(age, stint["FuelCorrectedSec"].to_numpy(float), 1)
        new_slope, new_int = np.polyfit(age, stint["TrackCorrectedSec"].to_numpy(float), 1)

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
                "race_fraction": stint["LapNumber"].min() / total_laps,
                "deg_old": old_slope,
                "deg_per_lap": new_slope,
                "pace_at_age5": new_slope * 5 + new_int,
            }
        )
        stints_here += 1

    print(f"  R{round_no:02d} {name:<12} evo {evo:+.4f} s/lap "
          f"({evo * total_laps:+.2f}s over the race), {stints_here} stints")


stints = pd.DataFrame(all_stints)
evolution = pd.DataFrame(evolution_rows)
stints.to_csv(OUT_CSV, index=False)
print(f"\nSaved {len(stints)} stints to {OUT_CSV}\n")


# ---------------------------------------------------------------------------
# 1. how much track evolution did we find
# ---------------------------------------------------------------------------

print("=" * 68)
print("TRACK EVOLUTION PER CIRCUIT")
print("=" * 68)
print("evo_per_lap   negative = track improving (lap times falling)")
print("evo_total_sec how much free time the track handed out across the race")
print("lockstep      how tightly tyre age and lap number move together.")
print("              near 1.0 would mean we can't trust the split.\n")

print(
    evolution[["race", "lockstep", "evo_per_lap", "evo_total_sec", "field_deg"]]
    .sort_values("evo_per_lap")
    .to_string(index=False, float_format=lambda x: f"{x:.3f}")
)


# ---------------------------------------------------------------------------
# 2. did it fix the impossible negative races
# ---------------------------------------------------------------------------

print()
print("=" * 68)
print("DEGRADATION BY CIRCUIT, BEFORE AND AFTER")
print("=" * 68)
print("Any negative number here is physically impossible and means the")
print("measurement is still broken.\n")

per_race = stints.groupby("race").agg(
    stints=("deg_per_lap", "size"),
    before=("deg_old", "median"),
    after=("deg_per_lap", "median"),
).sort_values("after", ascending=False)
print(per_race.to_string(float_format=lambda x: f"{x:.3f}"))

n_before = (per_race["before"] < 0).sum()
n_after = (per_race["after"] < 0).sum()
print(f"\nCircuits with impossible negative degradation: "
      f"{n_before} before -> {n_after} after")


# ---------------------------------------------------------------------------
# 3. can we tell the compounds apart now
# ---------------------------------------------------------------------------

print()
print("=" * 68)
print("DEGRADATION BY COMPOUND")
print("=" * 68)

# pooled numbers still have the circuit problem from step 4 in them
# (softs at easy tracks, hards at harsh ones) but we print them anyway to see the change
pooled = stints.groupby("compound").agg(
    stints=("deg_per_lap", "size"),
    before=("deg_old", "median"),
    after=("deg_per_lap", "median"),
).reindex([c for c in DRY_COMPOUNDS if c in stints["compound"].unique()])
print("Pooled (still has the circuit confound in it):")
print(pooled.to_string(float_format=lambda x: f"{x:.3f}"))

# now take the circuit out. every stint gets compared to the typical stint at
# its own race, so barcelona and canada are on the same level
stints["vs_circuit"] = (
    stints["deg_per_lap"] - stints.groupby("race")["deg_per_lap"].transform("median")
)

print("\nWith the circuit effect removed (the number that actually means something):")
print(
    stints.groupby("compound")["vs_circuit"]
    .agg(stints="size", median="median")
    .reindex([c for c in DRY_COMPOUNDS if c in stints["compound"].unique()])
    .to_string(float_format=lambda x: f"{x:+.3f}")
)
print("\nWe want SOFT highest and HARD lowest. Before this step all three")
print("sat at zero, meaning we couldn't tell them apart at all.")


# ---------------------------------------------------------------------------
# 4. soft vs hard inside each circuit
# ---------------------------------------------------------------------------

print()
print("=" * 68)
print("SOFT MINUS HARD, WITHIN EACH CIRCUIT")
print("=" * 68)
print("Positive = soft degrades faster = the correct direction.\n")

by_circuit = pd.crosstab(
    stints["race"], stints["compound"],
    values=stints["deg_per_lap"], aggfunc="median",
)
if "SOFT" in by_circuit and "HARD" in by_circuit:
    diff = (by_circuit["SOFT"] - by_circuit["HARD"]).dropna().sort_values(ascending=False)
    print(diff.to_string(float_format=lambda x: f"{x:+.3f}"))
    print(f"\nCorrect direction at {(diff > 0).sum()} of {len(diff)} circuits "
          f"(was 6 of 9 before this step)")
