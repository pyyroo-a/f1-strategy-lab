"""
Step 9: Monte Carlo, adding randomness

Races are very unpredicatable and we cannot predict what exactly will happen in a
race weekend. However, we are able to add randomness to the system to be able to
run thousands of simulations and see patterns in it.

This allows us to find patterns rather than simply trying to predict what will
happen.

The randomness we add here is safety cars. Step 8 planned a perfectly clean race,
which is why it kept saying fewer stops than the real teams did. A safety car
makes a pit stop way cheaper because everyone else is crawling, so teams grab
free tyres when one shows up.

What we found
-------------
1. Safety cars save you about 0.7s per stop, just from the chance that one of
   your planned stops happens to land while its out. More stops = more chances.

2. Reacting to a safety car only helps if it comes CLOSE to when you were
   going to stop anyway. At Barcelona always pitting under a safety car is 12
   seconds WORSE than never reacting, because pitting 15 laps early wrecks your
   stint balance and one tyre ends up ancient. Thats why you sometimes see a
   team leave a driver out under a safety car.

3. But that flips on low degradation tracks. At Spain a lap of tyre age only
   costs 0.011s, so pitting early costs almost nothing while the safety car
   still saves you 13 seconds. There the best move is to grab any safety car
   going.

   So the rule isnt "react within 4 laps", its:
       high deg track -> be picky
       low deg track  -> take anything

Nothing here is hand picked. We search every window and keep adding stops until
it stops helping.
"""

import random

from strategy import load_circuits, even_pit_laps

# ---- measured from the 2026 season ----
# out of 855 laps the SC was out only 7 times, so we can use that to estimate
# the percentage at which the safety car comes out
SC_CHANCE_PER_LAP = 0.0082

# safety cars last about 6.6 laps on average, rounded up
SC_LENGTH_LAPS = 7

# a stop under the safety car costs about half as much.
# this one is an assumption, not measured, so worth testing later
SC_PIT_LOSS_FACTOR = 0.5
# ---------------------------------------

RUNS = 2000      # how many simulated races per strategy
SEED = 1         # fixed seed so we get the same answer every time we run it


def make_safety_cars(total_laps):
    """Roll the dice for one race and give back which laps had a SC out."""
    sc_laps = set()

    for lap in range(1, total_laps+1):
        if random.random() < SC_CHANCE_PER_LAP:
            # it stays out for a few laps so mark all of them.
            # a set cant hold the same lap twice which is handy if two
            # safety cars end up overlapping
            for n in range(lap, lap + SC_LENGTH_LAPS):
                sc_laps.add(n)
    return sc_laps


def make_scenarios(total_laps, runs=RUNS):
    """Roll ALL the races up front, once, and reuse them for every strategy.

    This is a trick called common random numbers. If every strategy gets fresh
    dice then one of them can just get lucky, and with 2000 runs the luck is
    about the same size as the differences we are looking for.

    Rolling the scenarios once and testing every strategy against the exact
    same 2000 races means the luck is identical for all of them, so any
    difference has to be the strategy. Same idea as comparing teammates instead
    of comparing different teams.
    """
    random.seed(SEED)
    return [make_safety_cars(total_laps) for _ in range(runs)]


# we define this function so that we dont always pit during a SC because a real strategist wont
# we pit when it is close to the originallly intended pitting window
#
# react_window = how many laps EARLY we are willing to pit if a SC shows up.
# 0 means dont react at all, race_laps means grab any safety car going.
def time_lost_reaction(deg, pit_loss, total_laps, pit_laps, sc_laps, react_window):
    age = 0
    total = 0

    # sorted() makes a copy so we dont wreck the original list
    remaining = sorted(pit_laps)

    for lap in range(1, total_laps+1):

        # safety car is out AND we are close enough to our planned stop.
        # remaining[0] is the next stop we still have to make
        if remaining and lap in sc_laps and lap >= remaining[0] - react_window:
            total = total + pit_loss * SC_PIT_LOSS_FACTOR
            age = 0
            remaining.pop(0) # that stop is done so drop it off the list

        # otherwise just stop when we planned to
        elif remaining and lap == remaining[0]:
            if lap in sc_laps:
                total = total + pit_loss * SC_PIT_LOSS_FACTOR
            else:
                total = total + pit_loss
            age = 0
            remaining.pop(0)

        total = total + deg * age
        age += 1

    return total


def average_reacting(deg, pit_loss, total_laps, pit_laps, react_window, scenarios):
    """Run one strategy against every scenario and average the time lost."""
    total = 0

    for sc_laps in scenarios:
        total = total + time_lost_reaction(
            deg, pit_loss, total_laps, pit_laps, sc_laps, react_window
        )

    return total / len(scenarios)


def best_window(deg, pit_loss, total_laps, plan, scenarios):
    """Try EVERY reaction window and give back the best one.

    No hand picked list. The window only matters up to the first planned stop,
    because past that you would be reacting before the race even starts, so
    thats where we stop looking.
    """
    best = None

    for window in range(0, plan[0] + 1):
        result = average_reacting(deg, pit_loss, total_laps, plan, window, scenarios)

        if best is None or result < best[0]:
            best = (result, window)

    return best


# ---------------------------------------------------------------------------
# try it on whichever circuit you want
# ---------------------------------------------------------------------------

RACE = "Barcelona"          # change this: Spanish, Italian, Monaco, Hungarian...

circuits = load_circuits()
row = circuits.loc[RACE]

deg = row["deg"]
pit_loss = row["pit_loss"]
race_laps = int(row["race_laps"])

print(f"{RACE}: {race_laps} laps, deg {deg:.3f} s/lap, pit loss {pit_loss:.1f}s")

# some circuits dont have enough data to believe. we still let you run them,
# you just get told not to trust the answer
if row["borrowed"]:
    print(f"NOTE: only {int(row['stops'])} green flag stops here, so the pit "
          f"loss is borrowed from the season typical ({pit_loss:.1f}s)")

scenarios = make_scenarios(race_laps)
print(f"{len(scenarios)} simulated races, same ones used for every strategy\n")

print("stops   plan                  best window   time lost")

overall = None
previous = None
stops = 1

# keep adding stops until it stops helping.
# the curve only bends one way (down, bottom, up) so the first time it gets
# worse we are past the best and can stop looking
while True:
    plan = even_pit_laps(race_laps, stops)
    result, window = best_window(deg, pit_loss, race_laps, plan, scenarios)

    print(f"{stops:>5}   {str(plan):<20}  {window:>11}   {result:>9.2f}")

    if previous is not None and result > previous:
        print(f"\n{stops} stops is worse than {stops - 1}, so we stop looking")
        break

    if overall is None or result < overall[0]:
        overall = (result, stops, window, plan)

    previous = result
    stops += 1

print()
print(f"best: {overall[1]} stops at {overall[3]}, "
      f"reacting to a safety car up to {overall[2]} laps early, "
      f"losing {overall[0]:.2f}s")
