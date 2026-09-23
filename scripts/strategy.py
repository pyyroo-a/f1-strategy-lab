"""
Shared bits used by more than one script.

Step 8 and 9 both need the circuit numbers and the same two little functions,
and steps 10 and 11 will too. Rather than copy paste them into every file they
live here once, and the other scripts just import them:

    from strategy import load_circuits, time_lost, even_pit_laps

This works because python puts the script's own folder on the path, so any file
in scripts/ can import any other file in scripts/.
"""

import pandas as pd


def load_circuits(min_stops=8):
    """Build the one table with everything the simulator needs per circuit.

    Columns: deg, pit_loss, stops, race_laps, trusted

    trusted is False when we dont have enough data to believe the numbers:
      - degradation came out negative (impossible, Canada)
      - or there werent enough green flag pit stops (China, Italy)

    We keep the untrusted ones in the table instead of deleting them, so you can
    still look at them on purpose, you just get warned.
    """
    clean_air_stints = pd.read_csv("data/stints_2026_cleanair.csv")
    pit_stops = pd.read_csv("data/pit_stops_2026.csv")
    all_stints = pd.read_csv("data/stints_2026.csv")  # has the race lengths

    circuits = pd.DataFrame({
        "deg": clean_air_stints.groupby("race")["deg_per_lap"].median(),
        "pit_loss": pit_stops.groupby("race")["pit_loss"].median(),
        "stops": pit_stops.groupby("race").size(),
        "race_laps": all_stints.groupby("race")["race_laps"].max(),
    })

    circuits["trusted"] = (circuits["deg"] > 0) & (circuits["stops"] >= min_stops)

    return circuits


def time_lost(deg, pit_loss, total_laps, pit_laps):
    """How many seconds a strategy loses in a clean race with no safety cars.

    Fuel, track evolution and how fast the car is are the same whatever
    strategy you pick, so they cancel out and we can ignore them. Only two
    things change between strategies:

        deg x (tyre age added up over every lap) + stops x pit loss
    """
    age = 0
    total = 0

    for lap in range(1, total_laps + 1):
        if lap in pit_laps:
            total = total + pit_loss
            age = 0

        total = total + deg * age  # add how much this current tyre costs you
        age += 1

    return total


def even_pit_laps(total_laps, stops):
    """Where to stop if you want the stints to be even.

    When we tried every single pit lap for a one stop at Barcelona the best was
    lap 34, right in the middle. Pitting too early or too late are both bad
    because one of the tyres ends up really old.
    """
    # divide the stints equally because most pit stops happen in the middle of the race
    stint_length = total_laps / (stops + 1)
    pit_laps = []

    for k in range(1, stops + 1):
        pit_laps.append(round(stint_length * k) + 1)

    return pit_laps


def time_lost_real(deg, pit_loss, total_laps, pit_laps, sc_laps, red_laps):
    """Same as time_lost, but using what REALLY happened in that race.

    pit_laps  = the laps this strategy stops on
    sc_laps   = laps that really were under safety car or VSC, stops are cheaper
    red_laps  = laps that really were under red flag, tyres are changed for free

    Steps 10 and 11 both use this, because there we know exactly what happened
    instead of having to roll dice for it like step 9 does.
    """
    age = 0
    total = 0

    for lap in range(1, total_laps + 1):
        if lap in pit_laps:
            if lap in red_laps:
                cost = 0.0                  # free tyres on the grid
            elif lap in sc_laps:
                cost = pit_loss * 0.5       # cheap stop
            else:
                cost = pit_loss             # normal stop
            total = total + cost
            age = 0

        total = total + deg * age
        age += 1

    return total
