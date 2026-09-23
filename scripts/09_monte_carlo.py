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

What we found at Barcelona
--------------------------
1. Safety cars save you about 0.7s per stop, just from the chance that one of
   your planned stops happens to land while its out. More stops = more chances.

2. Reacting to a safety car only helps if it comes CLOSE to when you were
   going to stop anyway:

       window 0  -> 140.82   basically ignore safety cars
       window 4  -> 140.12   best
       window 30 -> 153.02   always pit under safety car

   Always pitting under a safety car is 12 seconds WORSE than never reacting.
   If you pit 15 laps early you save 12 seconds on the stop but wreck your
   stint balance, and one of your tyres ends up ancient. Thats why you
   sometimes see a team leave a driver out under a safety car.
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

def make_safety_cars(total_laps):
    """Roll the dice for the whole race and give back which laps had a SC out."""
    sc_laps = set()

    for lap in range(1, total_laps+1):
        if random.random() < SC_CHANCE_PER_LAP:
            # it stays out for a few laps so mark all of them.
            # a set cant hold the same lap twice which is handy if two
            # safety cars end up overlapping
            for n in range(lap, lap + SC_LENGTH_LAPS):
                sc_laps.add(n)
    return sc_laps


# we define this function so that we dont always pit during a SC because a real strategist wont
# we pit when it is close to the originallly intended pitting window

# react_window = how many laps EARLY we are willing to pit if a SC shows up.
# 0 means dont react at all, 30 means grab any safety car going.
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


def average_reacting(deg, pit_loss, total_laps, pit_laps, react_window, runs=10000):
    """Simulate the same strategy thousands of times and average it.

    One race tells us nothing because it all depends on whether the dice gave
    us a safety car. Thousands of races tells us what usually happens.
    """
    total = 0

    for i in range(runs): # simulating 10000 times
        # fresh safety cars every run, thats the whole point
        sc_laps = make_safety_cars(total_laps)
        total = total + time_lost_reaction(
            deg, pit_loss, total_laps, pit_laps, sc_laps, react_window
        )

    return total / runs

# ---------------------------------------------------------------------------
# try it on whichever circuit you want
# ---------------------------------------------------------------------------

RACE = "Monaco"          # change this: Spanish, Italian, Monaco, Hungarian...
WINDOWS = [0, 2, 4, 8, 15, 30]
MAX_STOPS = 4

circuits = load_circuits()
row = circuits.loc[RACE]

deg = row["deg"]
pit_loss = row["pit_loss"]
race_laps = int(row["race_laps"])

print(f"{RACE}: {race_laps} laps, deg {deg:.3f} s/lap, pit loss {pit_loss:.1f}s")

# some circuits dont have enough data to believe. we still let you run them,
# you just get told not to trust the answer
if not row["trusted"]:
    print(f"WARNING: only {int(row['stops'])} green flag stops here, "
          f"so the pit loss is a guess. Dont trust the numbers below.")

print()
print("rows = number of stops, columns = how many laps early we react to a safety car")
print()
print("stops  " + "".join(f"{w:>9}" for w in WINDOWS))

best = None

for stops in range(1, MAX_STOPS + 1):
    plan = even_pit_laps(race_laps, stops)

    print(f"{stops:>5}  ", end="")
    for window in WINDOWS:
        result = average_reacting(deg, pit_loss, race_laps, plan, window)
        print(f"{result:>9.2f}", end="")

        if best is None or result < best[0]:
            best = (result, stops, window, plan)

    print()

print()
print(f"best: {best[1]} stops at {best[3]}, reacting within {best[2]} laps, "
      f"losing {best[0]:.2f}s")
