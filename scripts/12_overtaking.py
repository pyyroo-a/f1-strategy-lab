"""
Step 12: How hard is each track to overtake at?

Step 10 told me the models big weakness: it has no idea other cars exist. You
pit, come out behind someone slower, and sit there losing time for six laps.
None of that is in the model.

Before I can fix that I need to know one thing: if you end up behind somebody,
how long are you stuck there?

I dont want to model overtaking, thats a nightmare. I want to MEASURE the
outcome, same as I did with degradation, pit loss and safety cars:

    if youre within 1.5s of the car ahead this lap,
    whats the chance youre STILL behind them next lap?

Im calling it stickiness. Monaco should be near 1.0 because theres nowhere to
pass. Baku has a massive straight so I expected it to be much lower.

(It wasnt. See the note at the bottom, watching the race explained why.)

Being careful about what counts as escaping
-------------------------------------------
If the car ahead pits, you are suddenly clear, but you didnt overtake anyone.
Counting that as an escape would make every track look easy to pass at. So I
throw out any lap where either car pitted.

I also only use green flag laps, because under a safety car everyone is nose to
tail and nobody is racing.

What I do with it
-----------------
    expected laps stuck = 1 / (1 - stickiness)

If theres a 0.8 chance of still being stuck each lap, you get out after about 5
laps on average. At 0.95 its 20 laps, which at most circuits means never.

Combined with the dirty air cost I measured in step 6 (0.6s a lap when youre
within half a second), that gives the price of coming out behind someone.

Why Baku came out sticky
------------------------
I expected Baku near the bottom because of that enormous straight, and it came
out third HARDEST. Watching the race explained it. You close right up on the
straight, but by then youre at turn 1 and you have to compromise your racing
line to take the corner properly. So one chance per lap, and taking it wrecks
your exit. I watched Verstappen do exactly that chasing Russell in the last few
laps and never get it done.

The caveat this number has
--------------------------
This measures "still behind them", which mixes up COULDNT pass with DIDNT TRY.
At Baku, Hadjar sat behind Verstappen for most of the race on purpose, as a team
thing, to make sure Max got the win. That counts as stuck in here. So these
numbers overstate the difficulty a bit, probably by a similar amount everywhere,
which is what matters since Im comparing tracks to each other.
"""

import warnings
from pathlib import Path

import fastf1
import pandas as pd

warnings.filterwarnings("ignore")

# ---- settings ----
YEAR = 2026

# same 1.5s I used in step 6, thats where dirty air stops mattering
STUCK_GAP = 1.5

OUT_CSV = Path("data/overtaking_2026.csv")
# ------------------

fastf1.Cache.enable_cache("cache")
OUT_CSV.parent.mkdir(exist_ok=True)

schedule = fastf1.get_event_schedule(YEAR)
races = schedule[
    (schedule["RoundNumber"] > 0) & (schedule["EventDate"] < pd.Timestamp.now())
]

rows = []

print("Measuring how hard it is to pass...\n")

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

    laps = laps.copy().sort_values(["LapNumber", "Time"])
    laps["ts"] = laps["TrackStatus"].fillna("").astype(str)

    # who was in front of each car, and by how much.
    # shift(1) looks at the row above, which after sorting by crossing time is
    # the car directly ahead on that lap
    laps["gap"] = laps.groupby("LapNumber")["Time"].diff().dt.total_seconds()
    laps["ahead"] = laps.groupby("LapNumber")["Driver"].shift(1)

    # a quick lookup so we can ask "did this car pit on this lap?"
    pitted = set(
        zip(laps.loc[laps["PitInTime"].notna(), "Driver"],
            laps.loc[laps["PitInTime"].notna(), "LapNumber"])
    ) | set(
        zip(laps.loc[laps["PitOutTime"].notna(), "Driver"],
            laps.loc[laps["PitOutTime"].notna(), "LapNumber"])
    )

    # index it so we can jump straight to one car on one lap
    by_key = laps.set_index(["Driver", "LapNumber"])

    stuck = escaped = 0

    for (driver, lap), row in by_key.iterrows():
        # must be genuinely close behind someone, on a green flag lap
        if pd.isna(row["gap"]) or row["gap"] > STUCK_GAP:
            continue
        if row["ts"] != "1":
            continue

        victim = row["ahead"]
        if pd.isna(victim):
            continue

        # skip if anyone involved pitted this lap or next, because getting
        # clear because they pitted is not overtaking
        nxt = lap + 1
        if ((driver, lap) in pitted or (victim, lap) in pitted
                or (driver, nxt) in pitted or (victim, nxt) in pitted):
            continue

        # what happened on the next lap?
        if (driver, nxt) not in by_key.index:
            continue
        after = by_key.loc[(driver, nxt)]
        if after["ts"] != "1":
            continue

        still_behind_same_car = (
            after["ahead"] == victim
            and pd.notna(after["gap"])
            and after["gap"] <= STUCK_GAP
        )

        if still_behind_same_car:
            stuck += 1
        else:
            escaped += 1

    total = stuck + escaped
    if total < 20:
        print(f"  R{round_no:02d} {name:<12} only {total} chances, skipping")
        continue

    stickiness = stuck / total
    rows.append({
        "round": round_no,
        "race": name,
        "chances": total,
        "stuck": stuck,
        "stickiness": stickiness,
        # how many laps you stay stuck on average
        "laps_stuck": 1 / (1 - stickiness) if stickiness < 1 else float("inf"),
    })
    print(f"  R{round_no:02d} {name:<12} {total:>4} chances, "
          f"stuck {stickiness:.2f}")


overtaking = pd.DataFrame(rows)
overtaking.to_csv(OUT_CSV, index=False)
print(f"\nSaved to {OUT_CSV}\n")

print("=" * 66)
print("HOW HARD IS IT TO PASS HERE?")
print("=" * 66)
print("stickiness  chance youre still stuck behind the same car next lap")
print("laps_stuck  so how many laps you stay there on average\n")

print(overtaking.sort_values("stickiness", ascending=False)
      [["race", "chances", "stickiness", "laps_stuck"]]
      .to_string(index=False, float_format=lambda x: f"{x:.2f}"))

print()
print("Sense check: Monaco should be at the top and Monza near the bottom.")
print("Thats the famous pair for this, so if it comes out otherwise, somethings wrong.")
