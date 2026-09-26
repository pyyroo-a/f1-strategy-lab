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

    Columns: deg, pit_loss, stops, race_laps, borrowed, trusted, usable

    Some circuits dont have enough green flag pit stops to measure pit loss.
    Baku is the example: everyone pitted under the safety car so only 2 real
    stops survived, and the simulator just refused to talk about the race.

    But pit loss barely moves between circuits. Across the ones we CAN measure
    it only spans 19.4 to 27.8 seconds, a spread of 2.6s. And the decisions we
    make hinge on 10 to 30 second differences, so being 2s out doesnt flip an
    answer.

    So for those circuits we borrow the season typical number and mark it, the
    same way we guessed the fuel constant and then checked it didnt matter.

      trusted = everything measured properly
      usable  = we can say something, but the pit loss might be borrowed

    Canada stays out of both because its degradation is negative, which is
    impossible, and no borrowing fixes that.
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

    enough = circuits["stops"] >= min_stops

    # the typical stop across circuits we actually trust
    season_pit_loss = float(circuits.loc[enough, "pit_loss"].median())

    circuits["borrowed"] = ~enough
    circuits.loc[~enough, "pit_loss"] = season_pit_loss

    circuits["trusted"] = (circuits["deg"] > 0) & enough
    circuits["usable"] = circuits["deg"] > 0

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


def real_pit_stops(driver_laps):
    """Which laps this driver ACTUALLY changed tyres on.

    We used to count any lap with a PitInTime as a pit stop. Baku 2026 proved
    that wrong. Albon crashed, and the whole field got sent through the pit
    lane on lap 36 without stopping. FastF1 records that as a pit entry, so 15
    of Baku's 36 "stops" never happened and it looked like a 2 stop race when
    it was a 1 stop.

    A real stop leaves a mark on the tyre. Either the compound is different
    afterwards, or the tyre age resets to 1. Verstappen came out of that lap 36
    trip on the same softs with the age still counting up (5, 6, 7), so it
    fails both checks and gets dropped.

    This also catches things like a driver serving a penalty in the pit lane.

    (A stop on the very last lap gets missed because theres no next lap to
    check, but nobody pits on the last lap.)
    """
    dl = driver_laps.sort_values("LapNumber")
    stops = []

    for _, in_lap in dl[dl["PitInTime"].notna()].iterrows():
        nxt = dl[dl["LapNumber"] == in_lap["LapNumber"] + 1]
        if nxt.empty:
            continue

        after = nxt.iloc[0]
        changed = (
            after["Compound"] != in_lap["Compound"]
            or after["TyreLife"] < in_lap["TyreLife"]
        )
        if changed:
            stops.append(int(in_lap["LapNumber"]))

    return stops


# ---------------------------------------------------------------------------
# traffic
# ---------------------------------------------------------------------------
# step 10 said the models big weakness was having no idea other cars existed.
# step 12 measured how long you stay stuck behind someone at each circuit.
# this is where we spend that.


def dirty_air_cost(gap):
    """Seconds lost per lap from sitting behind someone, measured in step 6."""
    if gap < 0.5:
        return 0.615
    if gap < 1.0:
        return 0.289
    if gap < 1.5:
        return 0.071
    return 0.0


def load_overtaking(race, default_laps_stuck=3.0):
    """How many laps you stay stuck at this circuit, from step 12."""
    try:
        ov = pd.read_csv("data/overtaking_2026.csv").set_index("race")
        return float(ov.loc[race, "laps_stuck"])
    except Exception:
        return default_laps_stuck


def field_times(laps):
    """Everyones real time at the end of each lap: {lap: {driver: seconds}}."""
    out = {}
    for _, row in laps.iterrows():
        if pd.notna(row["Time"]):
            out.setdefault(int(row["LapNumber"]), {})[row["Driver"]] = (
                row["Time"].total_seconds()
            )
    return out


def cost_by_lap(deg, pit_loss, total_laps, pit_laps, sc_laps, red_laps):
    """Running total of time lost, lap by lap, so we can compare part way."""
    age = 0
    total = 0.0
    out = {}

    for lap in range(1, total_laps + 1):
        if lap in pit_laps:
            if lap in red_laps:
                total += 0.0
            elif lap in sc_laps:
                total += pit_loss * 0.5
            else:
                total += pit_loss
            age = 0

        total += deg * age
        age += 1
        out[lap] = total

    return out


def traffic_cost(driver, pit_laps, deg, pit_loss, total_laps, sc_laps,
                 red_laps, field_time, reference_plan, laps_stuck):
    """What coming out in traffic costs with this plan.

    You hardly ever rejoin right on someones gearbox. The median gap on the lap
    after a stop is about 6 seconds. What really happens is you come out a few
    seconds back on fresh tyres, reel them in over the next few laps, and THEN
    youre stuck.

    So we walk forwards from each stop watching for the lap where we catch
    someone. Once we do, were held there for however long step 12 says you stay
    stuck at this circuit, paying the dirty air cost every lap and falling
    further behind while we do.

    reference_plan is what the driver really did. We work out where an
    alternative plan would put them by taking their real time and adding on
    however much better or worse the alternative is up to that point. If you
    pass their real plan as the reference, you get an estimate of the traffic
    they actually hit.
    """
    plan_by_lap = cost_by_lap(deg, pit_loss, total_laps, set(pit_laps),
                              sc_laps, red_laps)
    real_by_lap = cost_by_lap(deg, pit_loss, total_laps, set(reference_plan),
                              sc_laps, red_laps)

    total = 0.0
    stops = sorted(pit_laps)

    for i, stop in enumerate(stops):
        # watch until the next stop, or the end of the race
        last = stops[i + 1] if i + 1 < len(stops) else total_laps

        lap = stop + 1
        while lap <= last:
            if lap not in field_time or driver not in field_time[lap]:
                lap += 1
                continue

            # where we would be with this plan, plus whatever traffic has
            # already cost us
            mine_now = (field_time[lap][driver]
                        + plan_by_lap[lap] - real_by_lap[lap] + total)

            ahead = [x for d, x in field_time[lap].items()
                     if d != driver and x < mine_now]
            if not ahead:
                lap += 1
                continue

            per_lap = dirty_air_cost(mine_now - max(ahead))
            if per_lap == 0:
                lap += 1
                continue

            # caught someone, stuck here for a while
            stuck_for = min(laps_stuck, last - lap + 1)
            total += per_lap * stuck_for
            lap += int(stuck_for) + 1

    return total
