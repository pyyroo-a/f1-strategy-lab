"""
Step 1: First look at the data

Before doing anything fancy we just want to SEE what tyre degradation looks
like. We plot lap time vs tyre age for one driver in one race, one line per
stint.

If the line goes up to the right, the laps are getting slower as the tyre gets
older, which is degradation.

Change the settings below to look at a different driver or race.
"""

import warnings

import fastf1  # downloads the F1 timing data
import matplotlib.pyplot as plt  # draws the chart
import numpy as np  # for fitting the straight line

# fastf1 prints loads of harmless warnings, this hides them
warnings.filterwarnings("ignore")

# ---- settings: change these ----
YEAR = 2026
RACE = "Hungary"
DRIVER = "NOR"  # three letter driver code, e.g. NOR, VER, LEC, HAM
# --------------------------------

# downloading is slow so we save everything in a cache folder,
# second time you run it it loads instantly
fastf1.Cache.enable_cache("cache")

# "R" is the race. Q would be qualifying, FP1/FP2/FP3 are practice
session = fastf1.get_session(YEAR, RACE, "R")

# we turn off telemetry, weather and radio messages because we dont need them
# and they are the slow parts
session.load(telemetry=False, weather=False, messages=False)

# session.laps is a table with one row per lap for every driver.
# the columns we care about:
#   Driver      - three letter code
#   LapNumber   - which lap of the race
#   Stint       - which set of tyres (1 = first set, 2 = after first stop)
#   Compound    - SOFT / MEDIUM / HARD
#   TyreLife    - how many laps old the tyre is
#   LapTime     - the lap time
laps = session.laps

# only keep our driver's laps. .copy() stops pandas complaining later
# when we add a new column
driver_laps = laps[laps["Driver"] == DRIVER].copy()
total_laps = len(driver_laps)

# now we throw away laps that would mess up the picture.
# basically a lap is only "clean" if nothing else was making it slow:
#
#   PitInTime empty   -> not an in lap (slowing down to pit)
#   PitOutTime empty  -> not an out lap (leaving the pits on cold tyres)
#   TrackStatus "1"   -> green flag, no safety car or yellow flags
#   IsAccurate        -> fastf1 thinks the timing is trustworthy
#
# .isna() means "is empty" and & means AND, so a lap has to pass all four
clean = driver_laps[
    driver_laps["PitInTime"].isna()
    & driver_laps["PitOutTime"].isna()
    & (driver_laps["TrackStatus"] == "1")
    & driver_laps["IsAccurate"]
].copy()

# LapTime is a duration object which we cant plot, so turn it into seconds
clean["LapTimeSec"] = clean["LapTime"].dt.total_seconds()

print(f"{DRIVER}, {RACE} {YEAR}")
print(f"  {total_laps} laps total, {len(clean)} left after filtering")
print()

# fig is the whole image, ax is the actual plot area
fig, ax = plt.subplots(figsize=(10, 6))

# groupby("Stint") splits the laps up by tyre set, so we draw one line per stint
for stint_no, stint in clean.groupby("Stint"):
    # every lap in a stint is on the same compound so just take the first one
    compound = stint["Compound"].iloc[0]

    age = stint["TyreLife"].to_numpy(dtype=float)
    times = stint["LapTimeSec"].to_numpy(dtype=float)

    # draw the stint, marker="o" puts a dot on each lap
    line = ax.plot(age, times, marker="o", label=f"Stint {int(stint_no)} ({compound})")

    # fit a straight line through the dots so we get an actual number.
    # the slope is how many seconds slower each extra lap on the tyre is.
    # need at least 3 laps or the line means nothing
    if len(stint) >= 3:
        slope, incercept = np.polyfit(age, times, 1)

        #draw staright line version of the stint, dashed same color
        ax.plot(age, slope * age + incercept, linestyle="--", color=line[0].get_color())
        print(
            f"  Stint {int(stint_no)} ({compound:>6}): "
            f"{len(stint):2d} clean laps, "
            f"slope = {slope:+.3f} s/lap"
        )

print()
print("Reminder: this slope is NOT real degradation yet.")
print("The car is also burning fuel and getting lighter, which makes it faster.")
print("That fuel effect is hiding some of the degradation. We fix that in step 2.")

ax.set_xlabel("Tyre age (laps)")
ax.set_ylabel("Lap time (seconds)")
ax.set_title(f"{DRIVER}, {RACE} {YEAR} - lap time vs tyre age")
ax.legend()  # shows the stint names
ax.grid(alpha=0.3)  # faint grid lines so its easier to read

# save a copy in outputs so i can look at it later
out = f"outputs/01_{YEAR}_{RACE}_{DRIVER}.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nSaved plot to {out}")

plt.show()
