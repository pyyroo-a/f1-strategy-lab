"""
Step 8: The simulator

We give it a strategy and it tells us how many seconds that strategy loses.
Then we use that to find the best number of pit stops for every circuit.

Fuel, track evolution and how fast the car is are the same no matter what
strategy you pick, so they basically cancel out. Only two things actually
change between strategies:

    time lost = deg x (tyre age added up over every lap) + stops x pit loss

"""

import pandas as pd


"""
Part 1:

We load the pitstop file and clean air files and then group the clean air file
to get the median degradation per circuit. We also load the stints file from
step 4 because it has how many laps each race is.

Next we also get the median value for pit loss as its more accurate than mean.

And finally in the end we basically remove the circuits with weird degradation values and
have circuits which have at least 8 pit stops.

"""

clean_air_stints = pd.read_csv("data/stints_2026_cleanair.csv")
pit_stops = pd.read_csv("data/pit_stops_2026.csv")
all_stints = pd.read_csv("data/stints_2026.csv") # contains the number of laps per circuit


# vital as this shows how much seconds is being lost per lap when in clean air
deg_per_circuit = clean_air_stints.groupby("race")["deg_per_lap"].median()

# Median used here because average could have outliers
# Median gives us a close estimate to how much time each pit stop takes
pit_loss_per_circuit = pit_stops.groupby("race")["pit_loss"].median()

total_pit_stops = pit_stops.groupby("race").size()
race_length_per_circuit = all_stints.groupby("race")["race_laps"].max()

circuits = pd.DataFrame({
    "deg_per_circuit": deg_per_circuit,
    "pit_loss_per_circuit": pit_loss_per_circuit,
    "total_pit_stops": total_pit_stops,
    "race_length": race_length_per_circuit
})

# deg above 0 gets rid of canada (still weird idk why)
# 8 or more stops gets rid of china and italy, not enough stops to trust
circuits = circuits[(circuits["deg_per_circuit"] > 0) & (circuits["total_pit_stops"] >= 8)]


"""
Part 2

The most vital section of this script.

Here we give it a strategy and see how many seconds the strategy loses. We
built it with test values first (5 lap race, deg 0.1, pit loss 20) and checked
it by hand before using the real data.

How it is supposed to work,
1. Start with tyre age = 0 and time lost = 0
2. For each lap:
    - If it is a pit lap then add the pit loss to the total and reset tyre age to 0
    - Add degradation x tyre age to total time
    - Tyre age goes up by 1
3. Then return total

Order matters here, if tyre age goes up before we add the cost then every lap
gets charged one extra lap of age.

"""

def time_lost(deg, pit_loss, total_laps, pit_laps):
    age = 0
    total = 0

    for lap in range(1, total_laps + 1):
        if lap in pit_laps:
            total = total + pit_loss
            age = 0

        total = total + deg * age # add how much this current tyre costs you
        age += 1

    return total


"""
Part 3

Works out where to stop if you want the stints to be even.

When we tried every single pit lap for a one stop at Barcelona the best was
lap 34, right in the middle. Pitting too early or too late both lose a lot of
time because one of the tyres ends up really old. So the best stops are always
evenly spaced.

This saves us trying every combination, which gets crazy fast (5 stops at
Barcelona would be over 7 million combinations).

"""

def even_pit_laps(total_laps, stops):
    # divide the stints equally because most pit stops happen in the middle of the race
    stint_length = total_laps / (stops + 1)
    pit_laps = []

    for k in range(1, stops + 1):
        pit_laps.append(round(stint_length * k) + 1)

    return pit_laps


"""
Part 4

Go through every circuit and try 1 to 5 stops, then keep the one that loses
the least time.

best_stops and best_time get reset inside the circuit loop, otherwise the next
circuit would be compared against the last circuit's best.

"""

for race, row in circuits.iterrows():
    deg = row["deg_per_circuit"]
    pit_loss = row["pit_loss_per_circuit"]
    race_laps = int(row["race_length"]) # iterrows turns it into 66.0, range needs a whole number

    best_stops = None
    best_time = 999999

    for stops in range(1, 6):
        laps = even_pit_laps(race_laps, stops)

        result = time_lost(deg, pit_loss, race_laps, laps)

        if result < best_time:
            best_time = result
            best_stops = stops

    print(race, "best:", best_stops, "stops")
