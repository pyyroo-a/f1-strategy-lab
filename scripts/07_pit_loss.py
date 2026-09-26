"""
Step 7: How much does a pit stop cost?

We already have degradation, how much time old tyres cost you every lap. This
is the other half, how much you pay to get rid of them. Put them together and
you can basically ask: is the time I gain from fresh tyres worth the time I
lose going to get them?

What a pit stop actually costs
------------------------------
The tyre change itself is only about 2 seconds, thats the bit everyone watches
but its hardly any of the cost. The real cost is the pit lane. The speed limit
is 80 km/h and on track cars go through that same bit at like 250. So a long
pit lane costs more than a short one.

How we measure it
-----------------
When a driver pits two laps get wrecked:

    the IN LAP  - slowing down to go into the pits
    the OUT LAP - coming back out on cold tyres

So we compare those two laps against what the driver was normally doing just
before and after. The difference is the cost of the stop.

    pit loss = (in lap + out lap) - (2 x normal lap)

For the normal lap we use the driver's own median lap time around the stop.
Fuel, track evolution and how fast their car is barely change over a few laps,
so using their own nearby laps takes care of all of that for free.

What we throw out
-----------------
RED FLAG stops. The race gets stopped and teams can change tyres for free on
the grid. No pit lane, no 20 seconds. Monza 2026 had a red flag on lap 3
(Leclerc crashed) and 21 of its 32 stops were from that.

SAFETY CAR and VSC stops. Everyone is driving slowly so stopping is way cheaper
than normal. Theyre real stops but a different question to what we're asking.

YELLOW FLAG stops, same idea but smaller.

When we dont give an answer
---------------------------
After throwing all that out some circuits hardly have any stops left. Italy has
2. Thats not a real measurement, and if we print it anyway it goes into the
break even table and says stuff like "stop when your tyres are 121 laps old"
for a 53 lap race.

So if a circuit has less than MIN_STOPS we mark it as not trusted and leave it
out. Better to say we dont know than to quietly give a junk number.
"""

import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

from strategy import real_pit_stops

warnings.filterwarnings("ignore")

# ---- settings ----
YEAR = 2026

# how many laps before and after the stop to use for the normal lap time
WINDOW = 6
MIN_REFERENCE_LAPS = 4      # need at least this many clean laps around the stop

# less than this many stops and we dont trust the circuit.
# 2 stops isnt a measurement. italy is the example, the red flag meant everyone
# got free tyres so there were hardly any normal stops left
MIN_STOPS = 8

OUT_CSV = Path("data/pit_stops_2026.csv")
DEG_CSV = Path("data/stints_2026_cleanair.csv")   # made by step 6
# ------------------

fastf1.Cache.enable_cache("cache")
OUT_CSV.parent.mkdir(exist_ok=True)


schedule = fastf1.get_event_schedule(YEAR)
races = schedule[
    (schedule["RoundNumber"] > 0) & (schedule["EventDate"] < pd.Timestamp.now())
]

stops = []

print("Measuring pit stops...\n")

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
    laps["LapTimeSec"] = laps["LapTime"].dt.total_seconds()

    kept = dropped_red = dropped_sc = dropped_yellow = dropped_notime = 0
    dropped_nochange = 0

    for driver, dl in laps.groupby("Driver"):
        dl = dl.sort_values("LapNumber")

        # normal laps: green flag, not an in or out lap, accurate timing,
        # and not lap 1 because the standing start makes it slow
        normal = dl[
            dl["PitInTime"].isna()
            & dl["PitOutTime"].isna()
            & (dl["TrackStatus"] == "1")
            & dl["IsAccurate"]
            & (dl["LapNumber"] > 1)
        ]

        # a real stop is one where the tyre actually changed. going through the
        # pit lane without stopping doesnt count, see real_pit_stops
        changed_tyres = set(real_pit_stops(dl))

        for _, in_lap in dl[dl["PitInTime"].notna()].iterrows():
            n = in_lap["LapNumber"]

            if int(n) not in changed_tyres:
                dropped_nochange += 1
                continue

            # the out lap is the next lap and it should have a PitOutTime
            nxt = dl[dl["LapNumber"] == n + 1]
            if nxt.empty:
                continue
            out_lap = nxt.iloc[0]
            if pd.isna(out_lap["PitOutTime"]):
                continue

            # skip the very start of the race (pit lane starts and all that)
            if n <= 1:
                continue

            # was the race green or not?
            #
            # TrackStatus is a string of codes for everything that happened
            # on that lap, so one lap can say "245"
            #
            #   1 = green    2 = yellow    4 = safety car
            #   5 = RED FLAG    6/7 = virtual safety car
            #
            # we check this BEFORE lap times, because lap times are usually
            # missing when the race got stopped. this way we drop those stops
            # on purpose and know why, instead of by accident
            status = str(in_lap["TrackStatus"]) + str(out_lap["TrackStatus"])

            # red flag, tyres changed for free on the grid.
            # keeping these would pull pit loss way down
            if "5" in status:
                dropped_red += 1
                continue

            # safety car or VSC, everyone is slow so the stop is cheap
            if "4" in status or "6" in status or "7" in status:
                dropped_sc += 1
                continue

            # anything else thats not green, basically yellow flags
            if in_lap["TrackStatus"] != "1" or out_lap["TrackStatus"] != "1":
                dropped_yellow += 1
                continue

            # only now do we need real lap times. if one is still missing
            # here its an actual gap in the data, not a stoppage
            if pd.isna(in_lap["LapTimeSec"]) or pd.isna(out_lap["LapTimeSec"]):
                dropped_notime += 1
                continue

            # the driver's normal pace around this stop
            window = normal[
                (normal["LapNumber"] >= n - WINDOW)
                & (normal["LapNumber"] <= n + WINDOW + 1)
            ]
            if len(window) < MIN_REFERENCE_LAPS:
                continue

            reference = window["LapTimeSec"].median()

            # the whole calculation in one line
            loss = (in_lap["LapTimeSec"] + out_lap["LapTimeSec"]) - 2 * reference

            # how long they were actually in the pit lane, entry line to exit
            # line. nice to have as a check that the pit loss makes sense
            transit = (out_lap["PitOutTime"] - in_lap["PitInTime"]).total_seconds()

            stops.append({
                "round": round_no,
                "race": name,
                "driver": driver,
                "lap": int(n),
                "reference_lap": reference,
                "in_lap": in_lap["LapTimeSec"],
                "out_lap": out_lap["LapTimeSec"],
                "pit_loss": loss,
                "pit_lane_time": transit,
            })
            kept += 1

    print(f"  R{round_no:02d} {name:<12} {kept:3d} usable  "
          f"(dropped: {dropped_red} red flag, {dropped_sc} safety car, "
          f"{dropped_yellow} yellow, {dropped_notime} no timing, "
          f"{dropped_nochange} no tyre change)")


stops = pd.DataFrame(stops)
stops.to_csv(OUT_CSV, index=False)
print(f"\nSaved {len(stops)} pit stops to {OUT_CSV}\n")


# ---------------------------------------------------------------------------
# 1. pit loss per circuit
# ---------------------------------------------------------------------------

print("=" * 72)
print("PIT LOSS PER CIRCUIT (seconds)")
print("=" * 72)
print("median      the typical cost of stopping here")
print("spread      middle-half spread. Small means drivers agree, so we can")
print("            trust the number. Large means something else is going on.")
print("lane_time   time spent between the pit entry and exit lines\n")

per_race = stops.groupby("race").agg(
    stops=("pit_loss", "size"),
    median=("pit_loss", "median"),
    spread=("pit_loss", lambda x: x.quantile(0.75) - x.quantile(0.25)),
    lane_time=("pit_lane_time", "median"),
).sort_values("median", ascending=False)

# mark the circuits that dont have enough stops to trust
per_race["trust"] = np.where(per_race["stops"] >= MIN_STOPS, "yes", "NO")

print(per_race.to_string(float_format=lambda x: f"{x:.1f}"))

unreliable = per_race[per_race["trust"] == "NO"]
if len(unreliable):
    print()
    print(f"NOT TRUSTED (under {MIN_STOPS} usable stops), excluded from everything below:")
    for race, row in unreliable.iterrows():
        print(f"  {race}: only {int(row['stops'])} stops")

print()
trusted_races = per_race.index[per_race["stops"] >= MIN_STOPS]
trusted = stops[stops["race"].isin(trusted_races)]
print(f"Across trusted circuits, typical pit loss is {trusted['pit_loss'].median():.1f}s")
print("Real F1 pit loss is roughly 16 to 30 seconds depending on the track,")
print("so anything landing in that range is believable.")


# ---------------------------------------------------------------------------
# 2. pit loss and degradation together: when is stopping worth it?
# ---------------------------------------------------------------------------

if DEG_CSV.exists():
    deg = pd.read_csv(DEG_CSV).groupby("race")["deg_per_lap"].median()

    both = pd.DataFrame({
        "pit_loss": per_race.loc[per_race["trust"] == "yes", "median"],
        "deg_per_lap": deg,
    }).dropna()

    # only circuits with positive degradation. canada is negative which is
    # broken, and dividing by it gives nonsense
    both = both[both["deg_per_lap"] > 0]

    # rough version of the trade off.
    #
    # if your tyres are A laps old, fresh ones make you about (deg x A) seconds
    # a lap faster. with L laps left you gain about (deg x A x L) in total, and
    # you paid pit_loss to get it.
    #
    # break even when   deg x A x L = pit_loss
    # so               A = pit_loss / (deg x L)
    #
    # this is basically a rough guess. it ignores that the new tyre gets old
    # too and it ignores traffic. the simulator in step 8 does it properly
    LAPS_LEFT = 20
    both["tyre_age_to_justify_stop"] = both["pit_loss"] / (both["deg_per_lap"] * LAPS_LEFT)

    print()
    print("=" * 72)
    print(f"ROUGH: HOW OLD MUST YOUR TYRES BE BEFORE STOPPING PAYS?")
    print("=" * 72)
    print(f"Assuming {LAPS_LEFT} laps left to run, and ignoring traffic.")
    print("Lower number = stopping is worth it sooner.\n")

    print(both.sort_values("tyre_age_to_justify_stop")
          .to_string(float_format=lambda x: f"{x:.2f}"))

    print()
    print("This is the whole project in one table. High degradation makes")
    print("stopping cheap in real terms, low degradation makes it a waste.")
    print("A proper answer needs the simulator, because the fresh tyre ages too")
    print("and because rejoining in traffic can undo the entire gain.")
else:
    print(f"\n(Run step 6 first to get {DEG_CSV}, then this script can also")
    print(" combine pit loss with degradation.)")
