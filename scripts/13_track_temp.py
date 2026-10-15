"""
Step 13: does track temperature explain degradation?

My CV professor asked what if the same circuit degrades differently at
different times. This actually bothered me, because our per circuit numbers
could partly be that day's weather rather than the track.

Two tests, and they are not equally trustworthy.

Inside a race the circuit and the car never change, so if hot stints degrade
more than cool ones its the temperature doing it. Thats the clean test. The
catch is the track only moves a couple of degrees during a race.

Across circuits theres loads of range, 18 degrees at Canada up to 54 at
Madrid, but only 15 points and temperature comes bundled with everything else
about a track.

Written down before measuring so I cant fudge it after: hotter should mean
more degradation. Flat or backwards is also an answer.
"""

import warnings
from pathlib import Path

import fastf1
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

YEAR = 2026
STINTS_CSV = "data/stints_2026_cleanair.csv"
ALL_STINTS_CSV = "data/stints_2026.csv"
OUT_CSV = "data/track_temp_2026.csv"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e1e0d9"
ACCENT = "#2a78d6"
WARN = "#eb6834"

Path("cache").mkdir(exist_ok=True)
Path("outputs").mkdir(exist_ok=True)
fastf1.Cache.enable_cache("cache")


# ---------------------------------------------------------------------------
# Part 1: a track temperature for every stint
# ---------------------------------------------------------------------------

# Weather readings and laps are both stamped with a session time, so theyre on
# the same clock and we can just look up what the weather was doing while a
# stint was out there. One reading a minute.

stints = pd.read_csv(STINTS_CSV)
print(f"{len(stints)} stints across {stints['race'].nunique()} races\n")

schedule = fastf1.get_event_schedule(YEAR)
races = schedule[
    (schedule["RoundNumber"] > 0)
    & (schedule["EventDate"] < pd.Timestamp.now())
]

rows = []

for _, event in races.iterrows():
    round_no = int(event["RoundNumber"])
    name = event["EventName"].replace(" Grand Prix", "")

    race_stints = stints[stints["race"] == name]
    if race_stints.empty:
        continue

    try:
        session = fastf1.get_session(YEAR, round_no, "R")
        # weather is the one thing we want here. telemetry still doesnt load
        # for 2026 on this fastf1 version
        session.load(telemetry=False, weather=True, messages=False)
    except Exception as err:
        print(f"R{round_no:02d} {name}: FAILED to load ({err})")
        continue

    laps = session.laps
    weather = session.weather_data

    if weather is None or weather.empty:
        print(f"R{round_no:02d} {name}: no weather data")
        continue

    done = 0

    for _, row in race_stints.iterrows():
        driver = row["driver"]
        stint_no = row["stint"]

        # Stint is a float in the laps table and an int in our csv. forget the
        # cast and this matches nothing at all, silently, which is worse
        stint_laps = laps[
            (laps["Driver"] == driver) & (laps["Stint"] == float(stint_no))
        ]
        if stint_laps.empty:
            continue

        start_time = stint_laps["LapStartTime"].min()
        end_time = stint_laps["Time"].max()

        during = weather[
            (weather["Time"] >= start_time) & (weather["Time"] <= end_time)
        ]
        if during.empty:
            # stint shorter than the 60s between readings, happens rarely
            continue

        rows.append({
            "race": name,
            "driver": driver,
            "stint": stint_no,
            "track_temp": during["TrackTemp"].median(),
            "air_temp": during["AirTemp"].median(),
            "readings": len(during),
        })
        done += 1

    print(f"R{round_no:02d} {name}: {done} stints matched to weather")

temps = pd.DataFrame(rows)
temps.to_csv(OUT_CSV, index=False)
print(f"\nSaved {len(temps)} rows to {OUT_CSV}")


print("\n" + "=" * 60)
print("SANITY CHECKS")
print("=" * 60)

# the track is always hotter than the air. if this isnt 100% we grabbed the
# wrong column or the join is lining up the wrong rows
hotter = (temps["track_temp"] > temps["air_temp"]).mean()
print(f"track hotter than air: {hotter:.1%} of stints (want 100%)")

# this next table decides whether the whole step is worth doing. the inside a
# race test runs on this swing, so if its tiny theres nothing to find
swing = temps.groupby("race")["track_temp"].agg(["min", "max", "median"])
swing["swing"] = swing["max"] - swing["min"]
print("\ntrack temp swing inside each race:")
print(swing.sort_values("swing", ascending=False).to_string(
    float_format=lambda x: f"{x:.1f}"))


# ---------------------------------------------------------------------------
# Test 1: inside a race
# ---------------------------------------------------------------------------

d = stints.merge(temps, on=["race", "driver", "stint"])

# race_laps only lives in the full stints file. needed for the confound check
race_lengths = pd.read_csv(ALL_STINTS_CSV).groupby("race")["race_laps"].max()
d["race_fraction"] = d["start_lap"] / d["race"].map(race_lengths)

print(f"\n{len(d)} stints with both a degradation number and a temperature")

# This is the bit worth understanding. Take each race's own median off every
# column, and a row stops saying "Barcelona, 50 degrees, 0.139" and starts
# saying "2 degrees hotter than normal for its race, 0.01 more degradation
# than normal for its race". The circuit has cancelled itself out, so all 15
# races can go in one pile and the comparison is still within a race.
for col in ["track_temp", "deg_per_lap", "race_fraction"]:
    d[col + "_c"] = d[col] - d.groupby("race")[col].transform("median")

slope, intercept = np.polyfit(d["track_temp_c"], d["deg_per_lap_c"], 1)

print("\n" + "=" * 60)
print("TEST 1: hotter stints vs cooler stints, inside the same race")
print("=" * 60)
print(f"{slope:+.5f} s/lap per degree, so {slope * 10:+.4f} per 10 degrees")

# dont quote that per 10 degrees number anywhere. we never had 10 degrees, so
# its an extrapolation past the data. this is the effect we could ever see
typical = swing["swing"].median()
real = abs(slope) * typical
print(f"but a race only swings {typical:.1f} degrees, so really {real:.4f} s/lap")
print(f"harshest to gentlest circuit is 0.134 apart, so thats "
      f"{real / 0.134:.1%} of what we care about")

r = d["track_temp_c"].corr(d["deg_per_lap_c"])
print(f"correlation {r:+.3f}, so temp explains {r**2:.1%} of the wiggle")

# below this a correlation is just noise and the sign means nothing
floor = 1.96 / np.sqrt(len(d))
print(f"noise floor for {len(d)} points is {floor:.3f}", end="  ")
print("<- real" if abs(r) > floor else "<- under it, so this is nothing")

# The one that could ruin the test. Track temp drops through an afternoon and
# later stints are also later in the race, so if those two move together we
# have no idea which of them we actually measured.
conf = d["track_temp_c"].corr(d["race_fraction_c"])
print(f"\nconfound check, temp vs where in the race: {conf:+.3f}")
if abs(conf) > 0.5:
    print("  too close to tell hotter apart from earlier in the race")
else:
    print("  loose enough that temp isnt just standing in for race phase")


# ---------------------------------------------------------------------------
# Test 2: across circuits
# ---------------------------------------------------------------------------

circuits = d.groupby("race").agg(
    deg=("deg_per_lap", "median"),
    track_temp=("track_temp", "median"),
).dropna()

print("\n" + "=" * 60)
print("TEST 2: across circuits")
print("=" * 60)
print(circuits.sort_values("track_temp").to_string(
    float_format=lambda x: f"{x:.3f}"))

r2 = circuits["track_temp"].corr(circuits["deg"])
floor2 = 1.96 / np.sqrt(len(circuits))
print(f"\ncorrelation across {len(circuits)} circuits: {r2:+.3f}")
print(f"noise floor for {len(circuits)} points is {floor2:.3f}", end="  ")
print("<- real" if abs(r2) > floor2 else "<- under it, so this is nothing")

# Barcelona and Madrid are the pair everyone reaches for, nearly the same
# temperature and nothing like the same degradation. Careful though, Madrid is
# the worst measured circuit of the season, a third of its stints come out
# negative. Monza is the better comparison, its sampled properly.
pair = circuits[circuits.index.isin(["Barcelona", "Spanish", "Italian"])]
print("\nBarcelona vs Madrid vs Monza:")
print(pair.to_string(float_format=lambda x: f"{x:.3f}"))


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------

def tidy(ax):
    """Axis styling the rest of the project uses, no point repeating it."""
    ax.set_facecolor(SURFACE)
    ax.grid(color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


fig, ax = plt.subplots(figsize=(8, 5.5))
fig.patch.set_facecolor(SURFACE)
tidy(ax)

ax.scatter(d["track_temp_c"], d["deg_per_lap_c"],
           s=18, color=ACCENT, alpha=0.45, zorder=3, edgecolor="none")

xs = np.linspace(d["track_temp_c"].min(), d["track_temp_c"].max(), 50)
ax.plot(xs, slope * xs + intercept, color=INK, linewidth=2, zorder=4)
ax.axhline(0, color=GRID, linewidth=1, zorder=1)
ax.axvline(0, color=GRID, linewidth=1, zorder=1)

ax.set_xlabel("track temp vs normal for that race (degrees)", color=INK_SOFT)
ax.set_ylabel("degradation vs normal for that race (s/lap)", color=INK_SOFT)
ax.set_title(f"Inside a race: {slope * 10:+.4f} s/lap per 10 degrees",
             color=INK, fontsize=13, fontweight="bold", loc="left")
fig.text(0.01, 0.01, "each race centred on its own median so the circuit "
                     "cancels out", fontsize=9, color=INK_SOFT)

plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig("outputs/13_track_temp_within.png", dpi=150,
            facecolor=SURFACE, bbox_inches="tight")
plt.close()
print("\nsaved outputs/13_track_temp_within.png")


fig, ax = plt.subplots(figsize=(8.5, 5.5))
fig.patch.set_facecolor(SURFACE)
tidy(ax)

for race, row in circuits.iterrows():
    # orange for the three that make the point
    pick = race in ("Barcelona", "Spanish", "Italian")
    ax.scatter(row["track_temp"], row["deg"],
               s=110 if pick else 70,
               color=WARN if pick else ACCENT,
               zorder=4 if pick else 3,
               edgecolor=SURFACE, linewidth=1.5)
    ax.annotate(race, (row["track_temp"], row["deg"]),
                xytext=(6, 4), textcoords="offset points", fontsize=9,
                color=INK if pick else INK_SOFT,
                fontweight="bold" if pick else "normal")

ax.set_xlabel("median track temp on race day (degrees)", color=INK_SOFT)
ax.set_ylabel("degradation (s/lap of tyre age)", color=INK_SOFT)
ax.set_title(f"Across circuits: correlation {r2:+.2f}, on only 15 points",
             color=INK, fontsize=13, fontweight="bold", loc="left")
fig.text(0.01, 0.01, "Barcelona, Madrid and Monza in orange: all hot, "
                     "nothing like the same degradation",
         fontsize=9, color=INK_SOFT)

plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig("outputs/13_track_temp_between.png", dpi=150,
            facecolor=SURFACE, bbox_inches="tight")
plt.close()
print("saved outputs/13_track_temp_between.png")
