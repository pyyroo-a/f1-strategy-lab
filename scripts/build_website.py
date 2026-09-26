"""
Build the website data.

A web page cant run python, so it cant call any of this. Instead this script
works out every answer up front and writes them into one file that the page
just looks things up in.

It does the same job as 11_what_if.py, but for every driver in every race
instead of one at a time. 11 stays around as the version you poke at from the
terminal when youre curious about one driver.

One shortcut compared to 11
---------------------------
11 tries EVERY combination of pit laps for 1 and 2 stops. Thats thousands of
options per driver, and doing that for 300 drivers would take forever.

Here we slide the first stop through the race and spread the rest evenly after
it, which is about 50 options per stop count instead of thousands. Thats the
same family of strategies the chart draws anyway, and step 8 showed the best
strategies are evenly spaced, so were not losing much.

Run this whenever a new race happens, then the page is up to date.

It also builds the page itself, by gluing together the bits in docs/src and
dropping the data in. Output is one self contained docs/index.html.
"""

import json
import warnings
from datetime import date
from pathlib import Path

import fastf1
import pandas as pd

from strategy import (load_circuits, load_overtaking, field_times,
                      time_lost_real, traffic_cost, real_pit_stops)

warnings.filterwarnings("ignore")

# ---- settings ----
YEAR = 2026
MAX_STOPS = 3
OUT = Path("docs/data.json")
# ------------------

fastf1.Cache.enable_cache("cache")
OUT.parent.mkdir(exist_ok=True)


def lane_times(driver_laps):
    """(lap, seconds in the pit lane) for every real stop this driver made."""
    out = []
    driver_laps = driver_laps.sort_values("LapNumber")
    changed = set(real_pit_stops(driver_laps))

    for _, in_lap in driver_laps[driver_laps["PitInTime"].notna()].iterrows():
        if int(in_lap["LapNumber"]) not in changed:
            continue
        nxt = driver_laps[driver_laps["LapNumber"] == in_lap["LapNumber"] + 1]
        if nxt.empty or pd.isna(nxt.iloc[0]["PitOutTime"]):
            continue

        secs = (nxt.iloc[0]["PitOutTime"] - in_lap["PitInTime"]).total_seconds()
        # a red flag leaves the timer running for half an hour, thats not a stop
        if secs > 120:
            continue
        out.append((int(in_lap["LapNumber"]), round(secs, 1)))

    return out


def spread_plan(first, stops, total_laps):
    """A plan starting at `first` with the rest spread evenly after it."""
    plan = [first]
    for k in range(1, stops):
        plan.append(first + round(k * (total_laps - first) / stops))
    return plan


circuits = load_circuits()
schedule = fastf1.get_event_schedule(YEAR)
races = schedule[
    (schedule["RoundNumber"] > 0) & (schedule["EventDate"] < pd.Timestamp.now())
]

site = {
    "season": YEAR,
    "built": str(date.today()),
    "circuits": {},
    "races": [],
    "drivers": {},
}

# the season wide numbers the overview page shows
overtaking = pd.read_csv("data/overtaking_2026.csv").set_index("race")

print("Building site data...\n")

for _, event in races.iterrows():
    race = event["EventName"].replace(" Grand Prix", "")
    round_no = int(event["RoundNumber"])

    if race not in circuits.index or not circuits.loc[race, "usable"]:
        print(f"  {race:<12} skipped, we cant say anything useful about it")
        continue

    row = circuits.loc[race]
    deg = float(row["deg"])
    pit_loss = float(row["pit_loss"])

    try:
        session = fastf1.get_session(YEAR, round_no, "R")
        session.load(telemetry=False, weather=False, messages=False)
    except Exception as err:
        print(f"  {race:<12} FAILED ({err})")
        continue

    laps = session.laps.copy()
    laps["ts"] = laps["TrackStatus"].fillna("").astype(str)
    total_laps = int(laps["LapNumber"].max())

    sc_laps = {int(n) for n in laps.loc[laps.ts.str.contains("[467]"), "LapNumber"]}
    red_laps = {int(n) for n in laps.loc[laps.ts.str.contains("5"), "LapNumber"]}

    laps_stuck = load_overtaking(race)
    field_time = field_times(laps)
    results = session.results.set_index("Abbreviation")

    # how long a normal stop takes here, so we can spot a slow one
    every = []
    for _, dl in laps.groupby("Driver"):
        every += [s for _, s in lane_times(dl)]
    typical_lane = float(pd.Series(every).median()) if every else 0.0

    site["circuits"][race] = {
        "round": round_no,
        "laps": total_laps,
        "deg": round(deg, 4),
        "pit_loss": round(pit_loss, 1),
        "pit_loss_borrowed": bool(row["borrowed"]),
        "stops_measured": int(row["stops"]),
        "laps_stuck": round(laps_stuck, 1),
        "stickiness": round(float(overtaking.loc[race, "stickiness"]), 2)
                      if race in overtaking.index else None,
        "safety_car_laps": sorted(sc_laps),
        "typical_pit_lane": round(typical_lane, 1),
    }
    site["races"].append(race)
    site["drivers"][race] = {}

    done = 0
    for driver, dl in laps.groupby("Driver"):
        dl = dl.sort_values("LapNumber")

        # drivers who got to the end, including ones who got lapped. we use
        # THEIR race length rather than the winners, otherwise a lapped car
        # looks like it ran an extra stint
        laps_done = int(dl["LapNumber"].max())
        if laps_done < total_laps * 0.8:
            continue

        actual = sorted(real_pit_stops(dl))
        if not actual:
            continue

        stops_taken = lane_times(dl)
        slow_stop_cost = sum(s - typical_lane for _, s in stops_taken)

        def total_cost(plan):
            return (time_lost_real(deg, pit_loss, laps_done, set(plan),
                                   sc_laps, red_laps)
                    + traffic_cost(driver, plan, deg, pit_loss, laps_done,
                                   sc_laps, red_laps, field_time, actual,
                                   laps_stuck))

        tyres_and_stops = time_lost_real(deg, pit_loss, laps_done, set(actual),
                                         sc_laps, red_laps)
        traffic = traffic_cost(driver, actual, deg, pit_loss, laps_done,
                               sc_laps, red_laps, field_time, actual, laps_stuck)
        plan_cost = tyres_and_stops + traffic

        # the curves the chart draws, and the best of each
        curves = {}
        best = None
        for stops in range(1, MAX_STOPS + 1):
            points = []
            for first in range(2, laps_done - stops):
                plan = spread_plan(first, stops, laps_done)
                if len(set(plan)) != stops or max(plan) >= laps_done:
                    continue
                c = total_cost(plan)
                points.append([first, round(c, 1)])
                if best is None or c < best[0]:
                    best = (c, stops, plan)
            curves[str(stops)] = points

        gain = plan_cost - best[0]

        # who they would have got past. only works for cars on the lead lap,
        # a lapped car isnt racing the people around it on the timing screen
        finishers = {d: t for d, t in field_time.get(total_laps, {}).items()}
        passed = []
        if driver in finishers and gain > 0:
            mine = finishers[driver]
            passed = sorted(d for d, t in finishers.items()
                            if mine - gain < t < mine)

        site["drivers"][race][driver] = {
            "team": str(results.loc[driver, "TeamName"])
                    if driver in results.index else None,
            "grid": int(results.loc[driver, "GridPosition"])
                    if driver in results.index and pd.notna(results.loc[driver, "GridPosition"]) else None,
            "finish": int(results.loc[driver, "Position"])
                      if driver in results.index and pd.notna(results.loc[driver, "Position"]) else None,
            "laps_done": laps_done,
            "lapped": laps_done < total_laps,
            "actual_stops": actual,
            "pit_lane_times": stops_taken,
            "tyres_and_stops": round(tyres_and_stops, 1),
            "traffic": round(traffic, 1),
            "plan_cost": round(plan_cost, 1),
            "slow_stop_cost": round(slow_stop_cost, 1),
            "total": round(plan_cost + slow_stop_cost, 1),
            "best_stops": best[1],
            "best_plan": best[2],
            "best_cost": round(best[0], 1),
            "gain": round(gain, 1),
            "would_pass": passed,
            "curves": curves,
        }
        done += 1

    print(f"  {race:<12} {done} drivers")


with open(OUT, "w", encoding="utf-8") as f:
    json.dump(site, f, separators=(",", ":"))

# ---------------------------------------------------------------------------
# build the page
# ---------------------------------------------------------------------------
# the source lives split up in docs/src so its easy to work on:
#
#   page.html   the markup
#   styles.css  the styling
#   app.js      the pickers, the chart, the tables
#
# but a published page cant pull in a separate stylesheet or data file, so we
# glue all four pieces (those three plus the data) into one docs/index.html.
# that single file is what github pages serves

src = Path("docs/src")
if src.exists():
    page = (src / "page.html").read_text(encoding="utf-8")
    page = page.replace("/*__CSS__*/", (src / "styles.css").read_text(encoding="utf-8").strip())
    page = page.replace("/*__JS__*/", (src / "app.js").read_text(encoding="utf-8").strip())
    page = page.replace("/*__DATA__*/", json.dumps(site, separators=(",", ":")))

    banner = ("<!-- GENERATED FILE, DO NOT EDIT. "
              "Edit docs/src/page.html, styles.css or app.js, "
              "then run: python scripts/build_website.py -->")
    Path("docs/index.html").write_text(banner + chr(10) + page, encoding="utf-8")
    print("Saved docs/index.html "
          f"({Path('docs/index.html').stat().st_size / 1024:.0f} KB)")

size = OUT.stat().st_size / 1024
print(f"\nSaved {OUT} ({size:.0f} KB)")
print(f"  {len(site['races'])} races, "
      f"{sum(len(v) for v in site['drivers'].values())} drivers")
