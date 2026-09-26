"""
Step 11: The what if tool

Take a drivers real race, try the strategies they could have run instead, and
say what each one would have been worth.

How it works
------------
1. Pull their REAL pit laps out of the data and run them through the model.
   That gives what the strategy they actually ran cost them.
2. Try every alternative. One stop, two stops, three stops, at every lap.
3. Best alternative minus what they did = the seconds they left on the table.
4. Turn those seconds into positions, using the real gaps around them.

I use the REAL safety cars from that race, not random ones like step 9, so the
alternatives get judged in the same conditions the driver actually had.

Two separate questions
----------------------
Watching the Spanish GP, Norris ran what looked like the same strategy as
Antonelli and still came out behind. When I looked it up, his pit stop had taken
about 3 seconds longer than his teammates, and he lost second place by 0.7.

The tool couldnt see that, because it charged everyone the circuits typical pit
loss. So a driver who had a disaster in the pit box looked identical to one who
didnt.

Now it splits a race into two questions that have different people to blame:

    was the PLAN good?   was the STOP good?

It works the second one out by comparing each drivers time in the pit lane
against the typical stop at that race.

What this still CANT do
-----------------------
Step 10 measured how wrong the model is: it picks the better strategy about 8
times out of 10, but it cant tell you the gap in seconds reliably. So read the
ORDER of these results, not the exact numbers.

I thought traffic was the reason for that. Step 13 proved me wrong, its the pace
estimate. Traffic is in here anyway because its real, just small.
"""

import warnings
from itertools import combinations
from pathlib import Path

import fastf1
import matplotlib.pyplot as plt
import pandas as pd

from strategy import (load_circuits, even_pit_laps, time_lost_real,
                      real_pit_stops, load_overtaking, field_times,
                      traffic_cost as traffic_for)

warnings.filterwarnings("ignore")

# ---- settings: change these ----
YEAR = 2026
RACE = "Azerbaijan"
DRIVER = "SAI"
MAX_STOPS = 3

# any time penalty they picked up, in seconds. FastF1 doesnt give us these
# reliably so you have to type it in. 5 and 10 second penalties are the common
# ones, and they get added at the next stop or at the flag
PENALTY = 5.0

# if the pit loss for this circuit had to be borrowed, how far out might it be?
# across the circuits we can measure, pit loss spans about 2.6s, so 3 covers it
PIT_LOSS_UNCERTAINTY = 3.0
# --------------------------------

# colours, checked for colourblind readability
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a"]   # 1 stop, 2 stops, 3 stops
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e1e0d9"

fastf1.Cache.enable_cache("cache")


# ---------------------------------------------------------------------------
# get the circuit numbers and what really happened in the race
# ---------------------------------------------------------------------------

circuits = load_circuits()
row = circuits.loc[RACE]

if not row["trusted"]:
    print(f"WARNING: {RACE} doesnt have enough data to trust. "
          f"Only {int(row['stops'])} green flag stops.")

deg = row["deg"]
pit_loss = row["pit_loss"]

session = fastf1.get_session(YEAR, RACE, "R")
session.load(telemetry=False, weather=False, messages=False)

laps = session.laps.copy()
laps["ts"] = laps["TrackStatus"].fillna("").astype(str)
total_laps = int(laps["LapNumber"].max())

# the laps that really were under safety car or red flag
sc_laps = {int(n) for n in laps.loc[laps.ts.str.contains("[467]"), "LapNumber"]}
red_laps = {int(n) for n in laps.loc[laps.ts.str.contains("5"), "LapNumber"]}

mine = laps[laps["Driver"] == DRIVER].sort_values("LapNumber")
# only the laps where the tyre really changed, see real_pit_stops
actual_stops = sorted(real_pit_stops(mine))


# ---------------------------------------------------------------------------
# how good were their stops, not just their plan?
# ---------------------------------------------------------------------------
# up to now every stop got charged the circuits typical pit loss, so a driver
# who had a disaster in the pit box looked identical to one who didnt. Norris at
# Spain is the example: perfect strategy, 3.4s lost in the pit box, lost P2 by 0.7.
#
# the pit lane time (crossing the entry line to crossing the exit line) is in
# the data for every stop, so we can compare each driver's stop to the typical
# stop at that race:
#
#     extra = their pit lane time - the typical pit lane time here
#
# positive means the crew were slower than normal, and thats a loss that has
# nothing to do with strategy

def lane_times(driver_laps):
    """(lap, seconds in the pit lane) for every stop this driver made."""
    out = []
    driver_laps = driver_laps.sort_values("LapNumber")
    changed_tyres = set(real_pit_stops(driver_laps))
    for _, in_lap in driver_laps[driver_laps["PitInTime"].notna()].iterrows():
        if int(in_lap["LapNumber"]) not in changed_tyres:
            continue
        nxt = driver_laps[driver_laps["LapNumber"] == in_lap["LapNumber"] + 1]
        if nxt.empty or pd.isna(nxt.iloc[0]["PitOutTime"]):
            continue

        secs = (nxt.iloc[0]["PitOutTime"] - in_lap["PitInTime"]).total_seconds()

        # under a red flag the cars just sit in the pit lane, so this timer keeps
        # running for half an hour. I only noticed because Monaco came back
        # saying drivers lost 2100 seconds in the pit box. those arent stops
        if secs > 120:
            continue

        out.append((int(in_lap["LapNumber"]), secs))
    return out


every_stop = []
for _, dl in laps.groupby("Driver"):
    every_stop += [secs for _, secs in lane_times(dl)]

typical_lane = float(pd.Series(every_stop).median()) if every_stop else 0.0
my_stops = lane_times(mine)
slow_stop_cost = sum(secs - typical_lane for _, secs in my_stops)

print(f"{DRIVER} at the {RACE} GP {YEAR}, {total_laps} laps")
print(f"  deg {deg:.3f} s/lap, pit loss {pit_loss:.1f}s")
print(f"  safety car on laps: {sorted(sc_laps) if sc_laps else 'none'}")
print(f"  they actually stopped on laps: {actual_stops}")

# ---------------------------------------------------------------------------
# traffic: where do you come out, and how long are you stuck there?
# ---------------------------------------------------------------------------
# this is the thing step 10 said was wrecking our accuracy. the model had no
# idea other cars existed, so pitting into the middle of a queue looked free.
#
# we know the real race, so we can work out exactly where an alternative stop
# would have dropped them:
#
#   1. take their REAL time at each lap
#   2. add on however much better or worse the alternative plan is up to there
#   3. see whose real time that lands just behind
#
# then charge the dirty air cost we measured in step 6 for as many laps as
# step 12 says you stay stuck at this circuit

# how many laps you stay stuck here, measured in step 12
laps_stuck = load_overtaking(RACE)

# everyones real time at the end of each lap
field_time = field_times(laps)


def traffic_cost(pit_laps):
    """What this plan would cost in traffic. See strategy.py for the details."""
    return traffic_for(DRIVER, pit_laps, deg, pit_loss, total_laps, sc_laps,
                       red_laps, field_time, actual_stops, laps_stuck)


def cost(pit_laps):
    """Everything a strategy costs: tyres, stops, and traffic."""
    return (time_lost_real(deg, pit_loss, total_laps, set(pit_laps),
                           sc_laps, red_laps)
            + traffic_cost(pit_laps))


# the plan on its own, assuming a normal stop every time
tyres_and_stops = time_lost_real(deg, pit_loss, total_laps, set(actual_stops),
                                 sc_laps, red_laps)
traffic = traffic_cost(actual_stops)
plan_cost = tyres_and_stops + traffic

# and what their stops really cost on top of that, plus any penalty
actual_cost = plan_cost + slow_stop_cost + PENALTY

print()
print(f"  typical stop here takes {typical_lane:.1f}s in the pit lane")
for lap, secs in my_stops:
    print(f"    lap {lap:>2}: {secs:>5.1f}s   {secs - typical_lane:+.1f}s vs typical")
print()
print(f"  stuck behind someone   {laps_stuck:.1f} laps on average here")
print()
print(f"  tyres and stops        {tyres_and_stops:>7.1f}s")
print(f"  traffic                {traffic:>+7.1f}s")
print(f"  their plan cost        {plan_cost:>7.1f}s")
print(f"  their stops cost       {slow_stop_cost:>+7.1f}s")
if PENALTY:
    print(f"  time penalty           {PENALTY:>+7.1f}s")
print(f"  total                  {actual_cost:>7.1f}s")
print()


# ---------------------------------------------------------------------------
# try everything they could have done instead
# ---------------------------------------------------------------------------
# for 1 and 2 stops we try every single combination of laps.
# for 3 we use every other lap, otherwise its tens of thousands of options and
# the answer barely changes

print("=" * 66)
print("WHAT ELSE COULD THEY HAVE DONE?")
print("=" * 66)

best_per_stops = {}

for stops in range(1, MAX_STOPS + 1):
    possible = range(2, total_laps)
    if stops == 3:
        possible = range(2, total_laps, 2)

    best = None
    for plan in combinations(possible, stops):
        c = cost(plan)
        if best is None or c < best[0]:
            best = (c, list(plan))

    best_per_stops[stops] = best
    # compare against their PLAN, not their total. a different plan wouldnt
    # have had the same slow stop, thats a separate problem
    gain = plan_cost - best[0]
    print(f"  best {stops} stop: {str(best[1]):<22} {best[0]:>7.1f}s   "
          f"{gain:+.1f}s vs what they did")

best_cost, best_plan = min(best_per_stops.values())
overall_stops = min(best_per_stops, key=lambda s: best_per_stops[s][0])
plan_gain = plan_cost - best_cost

print()
if plan_gain <= 0.5:
    print(f"THE PLAN: they basically nailed it, nothing beat it by more than "
          f"{plan_gain:.1f}s.")
else:
    print(f"THE PLAN: {best_plan} was worth {plan_gain:.1f}s more than what they ran.")

if slow_stop_cost > 1:
    print(f"THE STOPS: they lost {slow_stop_cost:.1f}s in the pit box compared to "
          f"a normal stop here.")
elif slow_stop_cost < -1:
    print(f"THE STOPS: the crew gained them {abs(slow_stop_cost):.1f}s, "
          f"their stops were quicker than normal.")
else:
    print("THE STOPS: normal, nothing gained or lost.")

# everything they could have had: a better plan AND a normal stop
gain = plan_gain + max(slow_stop_cost, 0.0)


# ---------------------------------------------------------------------------
# would the answer survive being wrong about the pit loss?
# ---------------------------------------------------------------------------
# a borrowed pit loss could be a couple of seconds out. that only matters if it
# would change which strategy wins, so we just try it and see

def best_stop_count(alt_pit_loss):
    best = None
    for stops, (_, plan) in best_per_stops.items():
        c = (time_lost_real(deg, alt_pit_loss, total_laps, set(plan),
                            sc_laps, red_laps) + traffic_cost(plan))
        if best is None or c < best[0]:
            best = (c, stops)
    return best[1]

low = best_stop_count(pit_loss - PIT_LOSS_UNCERTAINTY)
high = best_stop_count(pit_loss + PIT_LOSS_UNCERTAINTY)

print()
if low == high == overall_stops:
    print(f"Pit loss check: still {overall_stops} stops even if the pit loss is "
          f"{PIT_LOSS_UNCERTAINTY:.0f}s out either way. The answer holds.")
else:
    print(f"CAREFUL: the answer depends on the pit loss. "
          f"{PIT_LOSS_UNCERTAINTY:.0f}s cheaper says {low} stops, "
          f"{PIT_LOSS_UNCERTAINTY:.0f}s dearer says {high} stops.")


# ---------------------------------------------------------------------------
# what would those seconds have been worth in positions?
# ---------------------------------------------------------------------------

finishers = {}
for drv, dl in laps.groupby("Driver"):
    if int(dl["LapNumber"].max()) == total_laps and dl["Time"].notna().any():
        finishers[drv] = dl["Time"].max().total_seconds()

if DRIVER in finishers and gain > 0:
    my_time = finishers[DRIVER]
    new_time = my_time - gain

    # who finished in between where they were and where they would have been
    passed = [d for d, t in finishers.items() if new_time < t < my_time]

    print()
    print("=" * 66)
    print("WOULD IT HAVE CHANGED ANYTHING?")
    print("=" * 66)
    if passed:
        print(f"  {gain:.1f}s would have got them past: {', '.join(sorted(passed))}")
        print(f"  so {len(passed)} position(s) better")
    else:
        ahead = sorted([t - my_time for t in finishers.values() if t < my_time])
        if ahead:
            print(f"  no positions. the car ahead finished {abs(ahead[-1]):.1f}s up the road,")
            print(f"  and {gain:.1f}s wasnt enough to catch them")
        else:
            print("  they won, so there was nobody to pass")


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
# left: how much the first stop lap matters, one line per number of stops
# right: the best of each, next to what they actually did

fig, (ax_curve, ax_bars) = plt.subplots(
    1, 2, figsize=(13, 5.5), gridspec_kw={"width_ratios": [1.5, 1]}
)
fig.patch.set_facecolor(SURFACE)

for i, stops in enumerate(range(1, MAX_STOPS + 1)):
    xs, ys = [], []
    # slide the whole plan earlier and later, keeping the stints even,
    # so we can see how much the timing matters
    for first in range(2, total_laps - stops):
        plan = [first]
        # spread the rest evenly through whats left
        for k in range(1, stops):
            plan.append(first + round(k * (total_laps - first) / stops))
        if len(set(plan)) != stops or max(plan) >= total_laps:
            continue
        xs.append(first)
        ys.append(cost(plan))

    ax_curve.plot(xs, ys, linewidth=2, color=COLOURS[i], zorder=3)

    # label each line at its right hand end instead of using a legend box.
    # they are nicely spread out over there so the labels dont collide
    ax_curve.annotate(f"{stops} stop" + ("s" if stops > 1 else ""),
                      (xs[-1], ys[-1]), textcoords="offset points",
                      xytext=(8, 0), va="center", fontsize=10,
                      color=COLOURS[i], fontweight="bold")

# where they actually were
ax_curve.scatter([actual_stops[0] if actual_stops else 0], [actual_cost],
                 s=90, color=INK, zorder=5, edgecolor=SURFACE, linewidth=2)
ax_curve.annotate(f"what {DRIVER} did: {len(actual_stops)} stop"
                  f"{'s' if len(actual_stops) != 1 else ''}, {actual_cost:.0f}s",
                  (actual_stops[0], actual_cost),
                  textcoords="offset points", xytext=(14, 26),
                  fontsize=10, color=INK, fontweight="bold",
                  arrowprops=dict(arrowstyle="-", color=INK, linewidth=1))

# room on the right for the line labels
ax_curve.set_xlim(0, total_laps + 10)
ax_curve.set_xlabel("lap of the first pit stop", color=INK_SOFT)
ax_curve.set_ylabel("time lost (seconds)", color=INK_SOFT)
ax_curve.set_title(f"{DRIVER}, {RACE} GP {YEAR}: when to stop",
                   color=INK, fontsize=13, fontweight="bold", loc="left")

labels = [f"{DRIVER} actual"] + [f"best {s} stop" for s in best_per_stops]
values = [actual_cost] + [best_per_stops[s][0] for s in best_per_stops]
colours = [INK] + COLOURS[:len(best_per_stops)]

bars = ax_bars.barh(range(len(values)), values, color=colours, height=0.6)
ax_bars.set_yticks(range(len(values)))
ax_bars.set_yticklabels(labels, color=INK_SOFT)
ax_bars.invert_yaxis()
ax_bars.set_xlabel("time lost (seconds)", color=INK_SOFT)
ax_bars.set_title("best of each, vs what happened",
                  color=INK, fontsize=13, fontweight="bold", loc="left")

for bar, value in zip(bars, values):
    ax_bars.text(value + max(values) * 0.02, bar.get_y() + bar.get_height() / 2,
                 f"{value:.0f}s", va="center", fontsize=10, color=INK_SOFT)
ax_bars.set_xlim(0, max(values) * 1.18)

for ax in (ax_curve, ax_bars):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="x" if ax is ax_bars else "y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_SOFT)

fig.text(0.01, 0.01,
         "Model ignores traffic, so read the order of these, not the exact seconds.",
         fontsize=9, color=INK_SOFT)

plt.tight_layout(rect=[0, 0.03, 1, 1])

Path("outputs").mkdir(exist_ok=True)
out = f"outputs/11_{YEAR}_{RACE}_{DRIVER}_whatif.png"
plt.savefig(out, dpi=150, facecolor=SURFACE, bbox_inches="tight")
print(f"\nSaved chart to {out}")

plt.show()
