"""
How much do we actually trust each circuit's degradation number?

My professor's first question about this project was "how sure are you about
these values". Good question, and for a while I didnt have an answer.

The degradation table is a MEDIAN across every stint at a circuit. A median
tells you the middle, it tells you nothing about whether the drivers agreed.
45 stints all saying 0.13 and 45 stints scattered from -0.1 to 0.4 give the
same median and mean completely different things.

So this prints the agreement next to the number. Two ways of looking at it:

  the middle half  how spread out the stints are. narrow means they agree
  negative stints  what share of stints came out below zero, which is
                   impossible, so its a direct measure of how much noise is
                   in there

No fastf1 here, it just reads the csv step 6 already saved.
"""

import pandas as pd

stints = pd.read_csv("data/stints_2026_cleanair.csv")

by_race = stints.groupby("race")["deg_per_lap"]

table = pd.DataFrame({
    "deg": by_race.median(),
    "stints": by_race.size(),
    "p25": by_race.quantile(0.25),
    "p75": by_race.quantile(0.75),
    "pct_negative": by_race.apply(lambda s: (s < 0).mean() * 100),
})

table = table.sort_values("deg", ascending=False)

print("=" * 72)
print("HOW MUCH DO THE DRIVERS AGREE AT EACH CIRCUIT?")
print("=" * 72)
print(f"{'circuit':<12}{'deg':>8}{'stints':>8}{'middle half':>20}{'negative':>12}")
for race, row in table.iterrows():
    middle = f"{row['p25']:.3f} to {row['p75']:.3f}"
    print(f"{race:<12}{row['deg']:>8.3f}{int(row['stints']):>8}"
          f"{middle:>20}{row['pct_negative']:>11.0f}%")

# A stint coming out negative means that stint measured tyres getting FASTER
# with age. Thats impossible, so every negative stint is noise we failed to
# remove. More than about a quarter and the circuit number is not a
# measurement any more, its whatever the noise happened to average out to.
NOISE_LIMIT = 25.0

trusted = table[table["pct_negative"] < NOISE_LIMIT]
shaky = table[table["pct_negative"] >= NOISE_LIMIT]

print("\n" + "=" * 72)
print(f"VERDICT (a circuit is shaky once {NOISE_LIMIT:.0f}% of its stints go negative)")
print("=" * 72)
print(f"\ntrustworthy, {len(trusted)} circuits:")
print("  " + ", ".join(f"{r} ({v:.3f})" for r, v in trusted["deg"].items()))
print(f"\nnot really measured, {len(shaky)} circuits:")
print("  " + ", ".join(f"{r} ({v:.3f})" for r, v in shaky["deg"].items()))

print("\nso comparing Barcelona against Monza is fair, because Barcelona is")
print("solid. comparing Monza against Monaco is not, theyre both noise.")

# Madrid deserves calling out on its own. Its the widest spread of the season
# and its tempting to use in a Barcelona comparison because the medians look
# dramatic. Monza is the honest version of that argument.
if "Spanish" in table.index:
    madrid = table.loc["Spanish"]
    width = madrid["p75"] - madrid["p25"]
    print(f"\nwatch Madrid especially: middle half spans {width:.3f}, the widest")
    print(f"of the season, off {int(madrid['stints'])} stints that disagree wildly")

# Canada isnt noise in the same way. Its negative CONSISTENTLY, which means
# something real is going on rather than the median landing somewhere odd.
if "Canadian" in table.index:
    can = table.loc["Canadian"]
    print(f"\nCanada is a different problem: {can['pct_negative']:.0f}% of its "
          f"{int(can['stints'])} stints are")
    print("individually negative, so its systematic, not bad luck")
