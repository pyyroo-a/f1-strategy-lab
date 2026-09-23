"""
Step 11: The what if tool

Take a driver's real race, try the strategies they could have run instead, and
say what each one would have been worth.

How it works
------------
1. Pull their REAL pit laps out of the data and run them through the model.
   That gives what the strategy they actually ran cost them.
2. Try every alternative. One stop, two stops, three stops, at every lap.
3. Best alternative minus what they actually did = the seconds they left on
   the table.
4. Turn those seconds into positions, using the real gaps to the cars around
   them at the flag.

We use the REAL safety cars from that race, not random ones like step 9, so the
alternative gets judged in the same conditions they actually had.

What this CANT do (from step 10)
--------------------------------
The model has no idea other cars exist. In real life you pit, come out behind
someone slower, and sit there losing time for six laps. None of that is in here.

Step 10 measured exactly how bad that makes it: the model picks the better
strategy about 8 times out of 10, but it cant tell you the gap in seconds
reliably. So read the ORDER of these results, not the exact numbers.
"""

import warnings
from itertools import combinations
from pathlib import Path

import fastf1
import matplotlib.pyplot as plt
import pandas as pd

from strategy import load_circuits, even_pit_laps, time_lost_real

warnings.filterwarnings("ignore")

# ---- settings: change these ----
YEAR = 2026
RACE = "Spanish"
DRIVER = "NOR"
MAX_STOPS = 3
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
actual_stops = sorted({int(n) for n in mine.loc[mine["PitInTime"].notna(), "LapNumber"]})


# ---------------------------------------------------------------------------
# how good were their stops, not just their plan?
# ---------------------------------------------------------------------------
# up to now every stop got charged the circuit's typical pit loss, so a driver
# who had a disaster in the pit box looked identical to one who didnt.
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
    for _, in_lap in driver_laps[driver_laps["PitInTime"].notna()].iterrows():
        nxt = driver_laps[driver_laps["LapNumber"] == in_lap["LapNumber"] + 1]
        if nxt.empty or pd.isna(nxt.iloc[0]["PitOutTime"]):
            continue
        out.append((int(in_lap["LapNumber"]),
                    (nxt.iloc[0]["PitOutTime"] - in_lap["PitInTime"]).total_seconds()))
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

# the plan on its own, assuming a normal stop every time
plan_cost = time_lost_real(deg, pit_loss, total_laps, set(actual_stops),
                           sc_laps, red_laps)

# and what their stops really cost on top of that
actual_cost = plan_cost + slow_stop_cost

print()
print(f"  typical stop here takes {typical_lane:.1f}s in the pit lane")
for lap, secs in my_stops:
    print(f"    lap {lap:>2}: {secs:>5.1f}s   {secs - typical_lane:+.1f}s vs typical")
print()
print(f"  their plan cost        {plan_cost:>7.1f}s")
print(f"  their stops cost       {slow_stop_cost:>+7.1f}s")
print(f"  total                  {actual_cost:>7.1f}s")
print()


def cost(pit_laps):
    return time_lost_real(deg, pit_loss, total_laps, set(pit_laps), sc_laps, red_laps)


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
