"""
Step 6: Clean air only

Fuel is sorted and track evolution is sorted. But track evolution is the same
for everyone, so it couldnt change which tyre looked worse. That means whatever
is left has to be different from stint to stint inside the same race.

Traffic is the obvious one. If a driver is stuck 0.8s behind someone for 15
laps they lose time to dirty air, and our fit blames all of that on the tyre.
Another driver in free air pays none of it.

Dirty air
---------
A car basically punches a hole in the air. If you follow close behind, your
wings are working in messy air so you get less downforce, less grip, slower
corners, and the tyres overheat because they slide more. Under about 1.5s
behind it costs real lap time.

How we get the gap
------------------
fastf1 doesnt have a "gap to car ahead" column so we make it ourselves. The
Time column is the moment a car crossed the line. Sort the cars by that on each
lap, take away the time of the car in front, and thats the gap.

We work out the gap on ALL laps before filtering anything. If we filtered first
we might delete the car in front and then measure the gap to someone miles up
the road.

Nobody knows the exact gap where dirty air stops mattering, so like the fuel
number we try a few and see if the answer changes.

What we found: it helped the circuit numbers, but soft vs hard still didnt
move. The noise between stints is 10x bigger than the soft vs hard difference,
so we stopped chasing compounds and kept degradation per circuit.
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

# gaps to try in seconds. 0 means no traffic filter at all, which is exactly
# what step 5 did, so thats what we compare against
THRESHOLDS = [0.0, 1.0, 1.5, 2.0, 3.0]

MAIN_THRESHOLD = 1.5        # the one we save to the csv
OUT_CSV = Path("data/stints_2026_cleanair.csv")
# ------------------

fastf1.Cache.enable_cache("cache")
OUT_CSV.parent.mkdir(exist_ok=True)


def fit_race(df):
    """Fit tyre age and lap number together, same as step 5."""
    X = pd.concat(
        [
            pd.get_dummies(df["Driver"], prefix="drv", drop_first=True),
            pd.get_dummies(df["Compound"], prefix="cmp", drop_first=True),
            df[["TyreLife", "LapNumber"]],
        ],
        axis=1,
    ).astype(float)
    X.insert(0, "const", 1.0)

    coef, *_ = np.linalg.lstsq(X.to_numpy(), df["FuelCorrectedSec"].to_numpy(float),
                               rcond=None)
    return coef[X.columns.get_loc("TyreLife")], coef[X.columns.get_loc("LapNumber")]


# ---------------------------------------------------------------------------
# load every race once, work out the gaps, and keep it all in memory
# so we can try every threshold without loading again
# ---------------------------------------------------------------------------

schedule = fastf1.get_event_schedule(YEAR)
races = schedule[
    (schedule["RoundNumber"] > 0) & (schedule["EventDate"] < pd.Timestamp.now())
]

loaded = []

print("Loading races and working out gaps...\n")

for _, event in races.iterrows():
    round_no = int(event["RoundNumber"])
    name = event["EventName"].replace(" Grand Prix", "")

    try:
        session = fastf1.get_session(YEAR, round_no, "R")
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as err:
        print(f"  R{round_no:02d} {name}: FAILED ({err})")
        continue

    laps = session.laps
    if laps is None or laps.empty:
        continue

    laps = laps.copy()
    total_laps = int(laps["LapNumber"].max())

    # --- the gap, worked out on ALL laps ---
    # sort by lap number, then by when each car crossed the line
    laps = laps.sort_values(["LapNumber", "Time"])

    # diff() takes each car's crossing time minus the car in front of it
    # on the same lap. that difference is the gap
    laps["GapAhead"] = (
        laps.groupby("LapNumber")["Time"].diff().dt.total_seconds()
    )

    # the leader has nobody in front so they get nothing. fill it with a
    # massive number so they always count as clean air
    laps["GapAhead"] = laps["GapAhead"].fillna(999.0)

    # --- usual filters and fuel correction ---
    kg_per_lap = STARTING_FUEL_KG / total_laps

    clean = laps[
        laps["PitInTime"].isna()
        & laps["PitOutTime"].isna()
        & (laps["TrackStatus"] == "1")
        & laps["IsAccurate"]
        & laps["Compound"].isin(DRY_COMPOUNDS)
    ].copy()

    if len(clean) < 100:
        continue

    clean["LapTimeSec"] = clean["LapTime"].dt.total_seconds()
    clean["FuelCorrectedSec"] = clean["LapTimeSec"] - (
        (total_laps - clean["LapNumber"]) * kg_per_lap * SECONDS_PER_KG
    )

    loaded.append({"round": round_no, "race": name,
                   "total_laps": total_laps, "clean": clean})

    in_traffic = (clean["GapAhead"] < 1.5).mean() * 100
    print(f"  R{round_no:02d} {name:<12} {len(clean):4d} clean laps, "
          f"{in_traffic:4.1f}% of them within 1.5s of a car")


# ---------------------------------------------------------------------------
# run the whole thing once for each threshold
# ---------------------------------------------------------------------------

def measure(threshold):
    """Do steps 5 and 6 at one traffic threshold and give back the stint table."""
    rows = []

    for race in loaded:
        df = race["clean"]

        # 0 means keep everything, no traffic filter.
        # thats the same as step 5 so we can see what filtering actually changed
        if threshold > 0:
            df = df[df["GapAhead"] >= threshold]

        # a harsh filter can wipe out most of a race. the fit needs enough laps
        # and enough drivers, because drivers being on different tyre ages at
        # the same time is what lets us split tyre age from track evolution
        if len(df) < 80 or df["Driver"].nunique() < 5:
            continue

        deg, evo = fit_race(df)

        # take the track effect out, same as step 5
        df = df.copy()
        df["Corrected"] = df["FuelCorrectedSec"] - evo * df["LapNumber"]

        for (driver, stint_no), stint in df.groupby(["Driver", "Stint"]):
            if len(stint) < MIN_CLEAN_LAPS:
                continue

            age = stint["TyreLife"].to_numpy(float)
            slope, intercept = np.polyfit(age, stint["Corrected"].to_numpy(float), 1)

            # median_gap is saved so we can check later that the stints left
            # really were in clean air
            rows.append({
                "race": race["race"],
                "driver": driver,
                "stint": int(stint_no),
                "compound": stint["Compound"].iloc[0],
                "clean_laps": len(stint),
                "start_lap": int(stint["LapNumber"].min()),
                "deg_per_lap": slope,
                "pace_at_age5": slope * 5 + intercept,
                "median_gap": stint["GapAhead"].median(),
            })

    return pd.DataFrame(rows)


def score(stints):
    """Three checks to see if the results make sense.

    We dont have an answer key for degradation, so we check against things we
    already know are true:

      1. degradation cant be negative (a tyre cant get faster with age)
      2. softs should degrade faster than hards
      3. that difference should show up once each circuit is levelled out

    If a change makes these better, it was a real improvement.
    """
    # check 1: any circuit where the typical stint is negative is broken
    per_race = stints.groupby("race")["deg_per_lap"].median()

    by_circuit = pd.crosstab(stints["race"], stints["compound"],
                             values=stints["deg_per_lap"], aggfunc="median")

    # check 2: soft vs hard INSIDE each circuit. comparing across circuits
    # doesnt work because teams use hards at harsh tracks, so we'd basically
    # be comparing barcelona to canada
    if "SOFT" in by_circuit and "HARD" in by_circuit:
        diff = (by_circuit["SOFT"] - by_circuit["HARD"]).dropna()
        right, total = int((diff > 0).sum()), len(diff)
    else:
        right = total = 0

    # check 3: same idea but all together. take each circuit's median away
    # from its stints, so a barcelona stint is only compared with other
    # barcelona stints and every circuit is on the same level
    vs = stints["deg_per_lap"] - stints.groupby("race")["deg_per_lap"].transform("median")
    med = vs.groupby(stints["compound"]).median()

    return {
        "stints": len(stints),
        "negative_circuits": int((per_race < 0).sum()),
        "soft_hard_right": f"{right}/{total}",
        "SOFT": med.get("SOFT", np.nan),
        "MEDIUM": med.get("MEDIUM", np.nan),
        "HARD": med.get("HARD", np.nan),
    }


print()
print("=" * 74)
print("DOES FILTERING TRAFFIC CHANGE THE ANSWER?")
print("=" * 74)
print("stints            how much data survives the filter")
print("negative_circuits circuits with impossible negative degradation. Want 0.")
print("soft_hard_right   circuits where soft degrades faster than hard. Want all.")
print("SOFT/MEDIUM/HARD  degradation with the circuit level removed.")
print("                  Want SOFT highest, HARD lowest, and a real gap.\n")

table = {}
saved = None

for t in THRESHOLDS:
    stints = measure(t)
    if stints.empty:
        print(f"gap >= {t}s : no data survived")
        continue
    label = "no filter" if t == 0 else f">= {t}s"
    table[label] = score(stints)
    if t == MAIN_THRESHOLD:
        saved = stints

print(pd.DataFrame(table).T.to_string(float_format=lambda x: f"{x:+.3f}"))

print()
print("Read the SOFT/MEDIUM/HARD columns down the page. If they stay flat as we")
print("filter harder, traffic wasn't the problem either. If a gap opens up in")
print("the right order, we've found it.")

if saved is not None:
    saved.to_csv(OUT_CSV, index=False)
    print(f"\nSaved the {MAIN_THRESHOLD}s version ({len(saved)} stints) to {OUT_CSV}")

    print()
    print("=" * 74)
    print(f"SOFT MINUS HARD PER CIRCUIT, at gap >= {MAIN_THRESHOLD}s")
    print("=" * 74)
    print("Positive = correct direction. Compare against step 5's 6 of 9.\n")

    bc = pd.crosstab(saved["race"], saved["compound"],
                     values=saved["deg_per_lap"], aggfunc="median")
    if "SOFT" in bc and "HARD" in bc:
        d = (bc["SOFT"] - bc["HARD"]).dropna().sort_values(ascending=False)
        print(d.to_string(float_format=lambda x: f"{x:+.3f}"))
        print(f"\nCorrect direction at {(d > 0).sum()} of {len(d)} circuits")

    print()
    print("=" * 74)
    print("DEGRADATION BY CIRCUIT, in clean air only")
    print("=" * 74)
    print(
        saved.groupby("race").agg(
            stints=("deg_per_lap", "size"),
            median_deg=("deg_per_lap", "median"),
        ).sort_values("median_deg", ascending=False)
        .to_string(float_format=lambda x: f"{x:.3f}")
    )
    print()
    print("MONACO CHECK: your prediction was that Monaco's odd track evolution")
    print("number was traffic. If so, Monaco should move more than most here.")
