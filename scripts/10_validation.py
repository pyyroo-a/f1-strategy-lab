"""
Step 10: Validation, how wrong is the model?

Everything so far has been us checking the model against things we already knew
(Barcelona is harsh, Monza is gentle, Spain is a one stop). Thats fine but its
not a number.

This is the number. How many seconds out is the model when it predicts a gap?

The idea
--------
We dont have an answer key for "what was the best strategy", nobody does. But we
DO have an answer key for a smaller question: how far apart did two drivers
finish? Thats just a fact.

So we take two drivers from the same race who ran different strategies, feed
their REAL pit laps into the model, and see if the gap the model predicts
matches the gap that actually happened.

Why teammates
-------------
You cant compare any two drivers because a Red Bull beating a Haas has nothing
to do with strategy. Teammates share the same car, same upgrades, same engine,
so if they run different strategies then most of the difference left is the
strategy. Its about as close to a controlled experiment as F1 gets.

Why the gap CHANGE and not the finishing gap
--------------------------------------------
If one teammate starts 3rd and the other 12th they will finish far apart no
matter what tyres they use. So instead of the raw finishing gap we use:

    (gap at the flag) - (gap at the end of lap 1)

Grid position cancels out and whats left is race pace and strategy.

Two versions of the prediction
------------------------------
v1 STRATEGY ONLY. Assume teammates are identical and the only difference is
   what tyres they were on and when they stopped.

   This failed. Median error 13.3s, and just guessing "no difference" would
   have been out by only 9.3s. Teammates are NOT identical, one of them is
   usually quicker on the day, and that swamped everything.

v2 STRATEGY + PACE. Same thing but we also work out how much quicker one
   teammate actually was per lap, and add that on.

   The pace comes from the same fit we used in step 5, on CLEAN AIR laps only,
   with tyre age already taken out. So its "how fast was this driver at equal
   tyre age with nobody in front".

   That last bit matters. If we measured pace using every lap then a driver who
   spent the race stuck in traffic would look slow, and we would be quietly
   feeding the answer back into the question. Clean air laps keep it honest:
   traffic losses stay in the error where they belong.

What we DO know about each race
-------------------------------
Unlike step 9 we are not guessing at safety cars here, we know exactly which
laps had one. So a stop that really happened under a safety car gets charged the
cheap price, and a stop during a red flag is free (tyres get changed on the grid).
"""

import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

from strategy import load_circuits

warnings.filterwarnings("ignore")

# ---- settings ----
YEAR = 2026

STARTING_FUEL_KG = 72.0
SECONDS_PER_KG = 0.03

SC_PIT_LOSS_FACTOR = 0.5    # same assumption as step 9
CLEAN_AIR_GAP = 1.5         # same as step 6

OUT_CSV = Path("data/validation_2026.csv")
# ------------------

fastf1.Cache.enable_cache("cache")


def predicted_time_lost(deg, pit_loss, total_laps, pit_laps, sc_laps, red_laps):
    """Same maths as the simulator, but using what REALLY happened.

    pit_laps  = the laps this driver actually pitted on
    sc_laps   = laps that really were under safety car or VSC
    red_laps  = laps that really were under red flag
    """
    age = 0
    total = 0

    for lap in range(1, total_laps + 1):
        if lap in pit_laps:
            if lap in red_laps:
                cost = 0.0                              # free tyres on the grid
            elif lap in sc_laps:
                cost = pit_loss * SC_PIT_LOSS_FACTOR    # cheap stop
            else:
                cost = pit_loss                         # normal stop
            total = total + cost
            age = 0

        total = total + deg * age
        age += 1

    return total


def driver_pace(clean):
    """How fast each driver was per lap, once tyre age and track are taken out.

    Same fit as step 5 but we keep the DRIVER numbers this time instead of
    throwing them away. Positive means slower than the reference driver.

    Then we shrink them, which is the important bit.

    Why shrink
    ----------
    A pace number is seconds PER LAP, and we multiply it by 70 odd laps. So a
    small error in the estimate gets multiplied by 70 as well. A driver with
    only 5 clean air laps can easily look half a second a lap quicker than they
    really were, and that turns into a 35 second prediction out of nowhere.

    Thats exactly what happened at Monaco, where theres barely any clean air.
    It gave us pace gaps of 70 seconds between teammates, which is nonsense.

    So we pull each driver's number towards zero depending on how shaky it is:

        shrink factor = real spread / (real spread + this driver's noise)

    A driver with loads of clean laps has little noise so they keep nearly all
    of their number. A driver with a handful gets pulled most of the way to
    zero. Nobody picks a cutoff, the data decides.
    """
    driver_cols = pd.get_dummies(clean["Driver"], prefix="drv", drop_first=True)
    compound_cols = pd.get_dummies(clean["Compound"], prefix="cmp", drop_first=True)

    X = pd.concat([driver_cols, compound_cols,
                   clean[["TyreLife", "LapNumber"]]], axis=1).astype(float)
    X.insert(0, "const", 1.0)

    y = clean["FuelCorrectedSec"].to_numpy(float)
    coef, *_ = np.linalg.lstsq(X.to_numpy(), y, rcond=None)

    # the driver that got dropped is the reference, so everyone starts at 0
    pace = {d: 0.0 for d in clean["Driver"].unique()}
    for col in driver_cols.columns:
        pace[col.replace("drv_", "")] = coef[X.columns.get_loc(col)]

    # how noisy is each driver's number?
    #
    # first, how far off the fit is on a typical lap
    Xm = X.to_numpy()
    residuals = y - Xm @ coef
    dof = max(len(y) - Xm.shape[1], 1)
    lap_noise = float(residuals @ residuals) / dof

    # then the proper uncertainty for each driver, which also knows about
    # drivers who barely have any clean laps or whose laps are tangled up with
    # everything else in the fit. at Monaco thats most of them, which is why a
    # simpler "noise divided by number of laps" was not enough
    covariance = np.linalg.pinv(Xm.T @ Xm) * lap_noise

    noise = {d: 0.0 for d in pace}
    for col in driver_cols.columns:
        j = X.columns.get_loc(col)
        noise[col.replace("drv_", "")] = covariance[j, j]

    # how much drivers really differ, once we take the noise back out
    spread = float(np.var(list(pace.values())) - np.mean(list(noise.values())))
    spread = max(spread, 1e-9)

    return {d: v * spread / (spread + noise[d]) for d, v in pace.items()}


circuits = load_circuits()
trusted = circuits[circuits["trusted"]]

print(f"Validating on {len(trusted)} trusted circuits\n")

rows = []

for race in trusted.index:
    deg = trusted.loc[race, "deg"]
    pit_loss = trusted.loc[race, "pit_loss"]

    try:
        session = fastf1.get_session(YEAR, race, "R")
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as err:
        print(f"  {race}: FAILED ({err})")
        continue

    laps = session.laps.copy().sort_values(["LapNumber", "Time"])
    laps["ts"] = laps["TrackStatus"].fillna("").astype(str)
    laps["GapAhead"] = laps.groupby("LapNumber")["Time"].diff().dt.total_seconds().fillna(999.0)
    total_laps = int(laps["LapNumber"].max())

    # which laps really had a safety car / VSC / red flag
    sc_laps = {int(n) for n in laps.loc[laps.ts.str.contains("[467]"), "LapNumber"]}
    red_laps = {int(n) for n in laps.loc[laps.ts.str.contains("5"), "LapNumber"]}

    # clean air laps, for working out how fast each driver actually was
    kg_per_lap = STARTING_FUEL_KG / total_laps
    clean = laps[
        laps["PitInTime"].isna()
        & laps["PitOutTime"].isna()
        & (laps["TrackStatus"] == "1")
        & laps["IsAccurate"]
        & laps["Compound"].isin(["SOFT", "MEDIUM", "HARD"])
        & (laps["GapAhead"] >= CLEAN_AIR_GAP)
    ].copy()

    if len(clean) < 80:
        print(f"  {race:<12} not enough clean air laps, skipping")
        continue

    clean["FuelCorrectedSec"] = clean["LapTime"].dt.total_seconds() - (
        (total_laps - clean["LapNumber"]) * kg_per_lap * SECONDS_PER_KG
    )
    pace = driver_pace(clean)
    clean_laps_each = clean["Driver"].value_counts().to_dict()

    results = session.results.set_index("Abbreviation")

    info = {}
    for driver, dl in laps.groupby("Driver"):
        dl = dl.sort_values("LapNumber")

        # only use drivers who made it to the end
        if int(dl["LapNumber"].max()) != total_laps:
            continue
        if driver not in pace:
            continue

        lap1 = dl[dl["LapNumber"] == 1]
        if lap1.empty or pd.isna(lap1.iloc[0]["Time"]):
            continue

        info[driver] = {
            "team": results.loc[driver, "TeamName"] if driver in results.index else None,
            "pit_laps": {int(n) for n in dl.loc[dl["PitInTime"].notna(), "LapNumber"]},
            "pace": pace[driver],
            "n_clean": clean_laps_each.get(driver, 0),
            # Time is the moment they crossed the line, so the last one is when
            # they finished and lap 1 is where they were after the first lap
            "lap1_time": lap1.iloc[0]["Time"].total_seconds(),
            "finish_time": dl["Time"].max().total_seconds(),
        }

    # pair up teammates
    pairs = 0
    drivers = list(info)
    for i, a in enumerate(drivers):
        for b in drivers[i+1:]:
            if info[a]["team"] is None or info[a]["team"] != info[b]["team"]:
                continue
            # no point comparing two identical strategies
            if info[a]["pit_laps"] == info[b]["pit_laps"]:
                continue

            pred_a = predicted_time_lost(deg, pit_loss, total_laps,
                                         info[a]["pit_laps"], sc_laps, red_laps)
            pred_b = predicted_time_lost(deg, pit_loss, total_laps,
                                         info[b]["pit_laps"], sc_laps, red_laps)

            # v1: strategy only. positive means the model thinks A ends up behind B
            strategy_gap = pred_a - pred_b

            # v2: strategy plus how much slower A was per lap.
            # we measure the gap from the end of lap 1, so the pace applies to
            # the remaining laps, not all of them
            pace_gap = (info[a]["pace"] - info[b]["pace"]) * (total_laps - 1)

            # what actually happened, with the lap 1 gap taken out so that
            # starting position doesnt count
            actual_gap = (
                (info[a]["finish_time"] - info[b]["finish_time"])
                - (info[a]["lap1_time"] - info[b]["lap1_time"])
            )

            rows.append({
                "race": race,
                "team": info[a]["team"],
                "driver_a": a,
                "driver_b": b,
                "stops_a": len(info[a]["pit_laps"]),
                "stops_b": len(info[b]["pit_laps"]),
                "strategy_gap": strategy_gap,
                "pace_gap": pace_gap,
                "n_clean_a": info[a]["n_clean"],
                "n_clean_b": info[b]["n_clean"],
                "predicted_gap": strategy_gap + pace_gap,
                "actual_gap": actual_gap,
                "error_v1": strategy_gap - actual_gap,
                "error_v2": strategy_gap + pace_gap - actual_gap,
            })
            pairs += 1

    print(f"  {race:<12} {pairs} teammate pairs with different strategies")


val = pd.DataFrame(rows)
val.to_csv(OUT_CSV, index=False)
print(f"\nSaved {len(val)} comparisons to {OUT_CSV}\n")

if val.empty:
    raise SystemExit("no pairs found, nothing to validate")

print("=" * 80)
print("WORST TEN, by the v2 error")
print("=" * 80)
print(val.reindex(val.error_v2.abs().sort_values(ascending=False).index)
      .head(10)
      .to_string(index=False, float_format=lambda x: f"{x:.1f}"))

print()
print("=" * 80)
print("HOW WRONG IS THE MODEL?")
print("=" * 80)

# a model that just says "there was no difference at all" is the bar to beat.
# if we cant beat that we are adding nothing
baseline = val["actual_gap"].abs()

def report(name, err):
    right = ((err.abs() < baseline.abs()) | (err.abs() < 1)).sum()
    print(f"{name:<24} median {err.abs().median():>6.1f}s   "
          f"mean {err.abs().mean():>6.1f}s   "
          f"within 5s {(err.abs() < 5).sum():>3}/{len(err)}   "
          f"beats saying nothing {right:>3}/{len(err)}")

report("say nothing", baseline)
report("v1 strategy only", val["error_v1"])
report("v2 strategy + pace", val["error_v2"])

print()
for name, col in [("v1", "strategy_gap"), ("v2", "predicted_gap")]:
    right = ((val[col] > 0) == (val["actual_gap"] > 0)).sum()
    print(f"{name} gets the direction right {right}/{len(val)}, "
          f"correlation with reality {val[col].corr(val['actual_gap']):.2f}")


# ---------------------------------------------------------------------------
# Calibration, with a train/test split so we dont kid ourselves
# ---------------------------------------------------------------------------
#
# v2 gets the DIRECTION right most of the time but the SIZE wrong, always in
# the same direction: it predicts about twice as much as really happens.
#
# A consistent error like that can be corrected. But if we work out the
# correction using all the races and then report how good it is on those same
# races, of course it looks great, we tuned it on them. Thats cheating.
#
# So we split the season in half:
#   - work out the correction on one half
#   - test it on the other half, which the correction has never seen
#   - then swap the halves round and do it again
#
# Only the test halves count.

print()
print("=" * 80)
print("CALIBRATION, TESTED ON RACES IT WAS NOT FITTED ON")
print("=" * 80)

rounds = pd.read_csv("data/stints_2026.csv").groupby("race")["round"].max()
val["round"] = val["race"].map(rounds)
val = val.sort_values("round")

order = list(dict.fromkeys(val["race"]))
first_half = set(order[:len(order) // 2])

def best_scale(d):
    """The single number that, multiplied through, fits these races best."""
    return float((d["predicted_gap"] * d["actual_gap"]).sum()
                 / (d["predicted_gap"] ** 2).sum())

tested = []

for label, train_races in [("first half", first_half),
                           ("second half", set(order) - first_half)]:
    train = val[val["race"].isin(train_races)]
    test = val[~val["race"].isin(train_races)]

    scale = best_scale(train)
    err = (test["predicted_gap"] * scale - test["actual_gap"]).abs()

    print()
    print(f"fitted on the {label} ({len(train)} pairs), "
          f"tested on the other {len(test)}")
    print(f"  correction found      x{scale:.2f}")
    print(f"  say nothing           {test['actual_gap'].abs().median():.1f}s")
    print(f"  before correcting     {(test['predicted_gap'] - test['actual_gap']).abs().median():.1f}s")
    print(f"  after correcting      {err.median():.1f}s")

    tested.append(pd.DataFrame({
        "race": test["race"],
        "err": err,
        "baseline": test["actual_gap"].abs(),
        "raw": (test["predicted_gap"] - test["actual_gap"]).abs(),
    }))

both = pd.concat(tested)

print()
print("=" * 80)
print("FINAL ANSWER")
print("=" * 80)
print("Every pair below was predicted by a model that never saw its race.")
print()
print(f"  pairs tested            {len(both)}")
print(f"  say nothing             {both['baseline'].median():.1f}s")
print(f"  our model, uncorrected  {both['raw'].median():.1f}s")
print(f"  our model, corrected    {both['err'].median():.1f}s")
print(f"  within 5 seconds        {(both['err'] < 5).sum()} of {len(both)}")
print(f"  within 10 seconds       {(both['err'] < 10).sum()} of {len(both)}")
