"""
Step 2: Remove the fuel effect

The car starts heavy with fuel and gets lighter every lap, which makes it
faster for reasons that have nothing to do with the tyres. That basically
hides some of the degradation.

So we correct every lap to what it would have been on an empty tank, then all
the laps can be compared fairly.

Plots raw vs corrected side by side.
"""

import warnings

import fastf1
import matplotlib.pyplot as plt
import numpy as np

warnings.filterwarnings("ignore")

YEAR = 2026
RACE = "Hungary"
DRIVER = "NOR"

# These two are basically estimates, teams never publish their fuel loads.
# 2026 cars run around 70-75 kg so we pick one in that range and then check
# if the choice even matters (it doesnt, less than 0.005 s/lap difference).
# Left at 75 here because this is the file we tested it in, the other files use 72.
STARTING_FUEL_KG = 75.0
SECONDS_PER_KG = 0.03 # each extra kg costs about 0.03s per lap

fastf1.Cache.enable_cache("cache")

session = fastf1.get_session(YEAR, RACE, "R")
session.load(telemetry=False, weather=False, messages=False)

laps = session.laps

driver_laps = laps[laps["Driver"] == DRIVER].copy()

# same four filters as step 1, no pitting, green flag, accurate timing
clean = driver_laps[
    driver_laps["PitInTime"].isna()
    & driver_laps["PitOutTime"].isna()
    & (driver_laps["TrackStatus"] == "1")
    & driver_laps["IsAccurate"]
].copy()

# turn the lap time into plain seconds so we can do maths on it
clean["LapTimeSec"] =  clean["LapTime"].dt.total_seconds()

# How long was the race? Take the highest lap number anyone reached.
# We use the full laps table, not just our driver, in case they retired early.
total_laps = int(laps["LapNumber"].max())

# spread the fuel evenly across the race. real burn isnt perfectly even but
# its close enough and way simpler
kg_per_lap = STARTING_FUEL_KG / total_laps

# fuel still in the car on any lap = laps still to go x kg burned per lap.
# lap 1 of 70 has nearly a full tank, lap 69 is basically empty
laps_remaining = total_laps - clean["LapNumber"]
fuel_on_board_kg = laps_remaining * kg_per_lap

# that fuel is weight and weight costs time. this is how many seconds the lap
# got slowed down by the fuel still in the car
fuel_penalty_sec = fuel_on_board_kg * SECONDS_PER_KG

# take the penalty away to get the empty tank lap time.
# early laps change a lot, late laps barely change.
# we keep the raw column too so we can compare
clean["FuelCorrectedSec"] = clean["LapTimeSec"] - fuel_penalty_sec

print(f"{DRIVER}, {RACE} {YEAR}  ({total_laps} lap race)")
print(f"  {STARTING_FUEL_KG} kg over {total_laps} laps = {kg_per_lap:.3f} kg/lap")
print(f"  = {kg_per_lap * SECONDS_PER_KG:.3f} s/lap of free speed from burning fuel")
print()
print(f"  {'Stint':<20} {'raw':>9} {'corrected':>11}")

# print the before and after slope for each stint.
# if the correction worked the corrected slopes should be BIGGER,
# because the fuel was hiding real degradation
for stint_no, stint in clean.groupby("Stint"):
    # need at least 3 laps for a line to mean anything
    if len(stint) < 3:
        continue

    compound = stint["Compound"].iloc[0]
    age = stint["TyreLife"].to_numpy(dtype=float)

    # same straight line fit as before but done twice, raw and corrected
    raw_slope, _ = np.polyfit(age, stint["LapTimeSec"], 1)
    corr_slope, _ = np.polyfit(age, stint["FuelCorrectedSec"], 1)

    label = f"{int(stint_no)} ({compound})"
    print(f"  {label:<20} {raw_slope:>+8.3f} {corr_slope:>+10.3f}")

# two charts side by side. sharey=True makes them use the same vertical scale,
# thats the whole point, you can see the corrected stints pull closer together
fig, (ax_raw, ax_corr) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

# draw the same thing on both charts, just from a different column
for column, ax, title in [
    ("LapTimeSec", ax_raw, "Raw lap times"),
    ("FuelCorrectedSec", ax_corr, "Fuel corrected (empty tank)"),
]:
    for stint_no, stint in clean.groupby("Stint"):
        compound = stint["Compound"].iloc[0]
        age = stint["TyreLife"].to_numpy(dtype=float)
        times = stint[column].to_numpy(dtype=float)

        line, = ax.plot(
            age, times, marker="o", label=f"Stint {int(stint_no)} ({compound})"
        )

        if len(stint) >= 3:
            slope, intercept = np.polyfit(age, times, 1)
            ax.plot(age, slope * age + intercept, linestyle="--",
                    color=line.get_color())

    ax.set_title(title)
    ax.set_xlabel("Tyre age (laps)")
    ax.grid(alpha=0.3)

ax_raw.set_ylabel("Lap time (seconds)")
ax_raw.legend()

fig.suptitle(f"{DRIVER}, {RACE} {YEAR}")

# fuel weight goes in the file name so the 70/72/75 kg charts dont overwrite each other
out = f"outputs/02_{YEAR}_{RACE}_{DRIVER}_{STARTING_FUEL_KG:.0f}kg.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nSaved plot to {out}")

plt.show()
