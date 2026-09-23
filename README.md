# F1 Strategy Lab

Working out how fast F1 tyres wear out in the 2026 season, and using that to
figure out **what strategy a driver should have run.**

Built with [FastF1](https://github.com/theOehrly/Fast-F1).

## The question

A pit stop costs you about 20 seconds. Old tyres cost you a bit of time every
single lap.

So basically: **is the time you get back from fresh tyres worth the 20 seconds
it costs to get them, and if it is, when should you stop?**

To answer that we need two numbers:

1. **Degradation.** How many seconds a lap you lose as the tyre gets older.
2. **Pit loss.** How many seconds a stop actually costs at that circuit.

Once we have both, we can simulate strategies and see which one loses the
least time.

## Why it's hard

You can't just look at a driver's lap times and say "that's degradation". Loads
of other stuff is changing at the same time, and anything we don't take out
gets blamed on the tyre.

| What's changing | What it does to lap time | Sorted? |
| --- | --- | --- |
| Car burning fuel and getting lighter | faster | yes, step 2 |
| Some circuits are just harsher on tyres | varies | yes, step 4 |
| Track rubbering in during the race | faster | yes, step 5 |
| Being stuck behind another car | slower | yes, step 6 |
| Tyre getting older | slower | this is the one we want |

## Where it's at

- **Degradation per circuit:** working
- **Pit loss per circuit:** working (12 of 14 circuits)
- **Simulator:** working, picks the best number of stops for each circuit
- **Degradation per compound (soft vs hard):** tried it, the data can't do it. Explained below
- **Monte Carlo (safety cars):** working
- **Validation:** done, and the honest answer is mixed. See step 10
- **What if tool:** working, with charts

All results below are from the first 14 rounds of 2026 (up to Spain).

## Results

### Degradation per circuit

Seconds lost per lap of tyre age, clean air only:

| Circuit | Degradation | Makes sense? |
| --- | --- | --- |
| Barcelona | 0.139 | rough surface, long fast corners, known for destroying tyres |
| Hungary | 0.088 | corner after corner, the tyre never gets a break |
| Austria | 0.081 | short lap with loads of hard acceleration |
| Japan | 0.064 | fast flowing corners, lots of load |
| Netherlands | 0.063 | banked corners push the tyres hard |
| Britain | 0.059 | high speed corners |
| Belgium | 0.054 | long lap but plenty of straights to cool down |
| Australia | 0.047 | smooth track |
| China | 0.027 | |
| Monaco | 0.024 | really slow, hardly any load on the tyres |
| Miami | 0.022 | |
| Italy | 0.013 | Monza is basically all straights, gentlest track of the season |
| Spain | 0.011 | barely wears the tyres at all |
| Canada | **-0.017** | **impossible, still weird and we don't know why yet** |

How to read it: at Barcelona a tyre that's 20 laps old is about **2.8 seconds
a lap** slower than a new one. At Monaco the same tyre is only about **half a
second** slower.

The cool thing is we never told the code anything about the tracks, only lap
times. It worked out by itself that Barcelona is the harshest, Monaco is gentle
and Monza is the gentlest, which is exactly what anyone in F1 would tell you.

### Pit loss per circuit

| Circuit | Pit loss (s) | Spread | Stops used |
| --- | --- | --- | --- |
| Canada | 27.8 | 7.2 | 14 |
| Spain | 26.8 | 2.3 | 14 |
| Australia | 24.5 | 7.7 | 9 |
| Barcelona | 23.8 | 1.8 | 40 |
| Japan | 22.9 | 2.5 | 13 |
| Hungary | 22.1 | 1.9 | 34 |
| Monaco | 21.9 | 3.5 | 19 |
| Britain | 21.5 | 5.2 | 22 |
| Austria | 21.4 | 1.2 | 33 |
| Belgium | 20.8 | 4.5 | 9 |
| Miami | 19.5 | 1.6 | 19 |
| Netherlands | 19.4 | 2.1 | 37 |
| China | not trusted | | only 4 |
| Italy | not trusted | | only 2 |

Typical pit loss is **22.0 seconds**, which is right where real F1 pit loss
sits (roughly 16 to 30 depending on the track).

Spread is how much the drivers disagree with each other. At Barcelona 40 stops
all agree within 1.8 seconds, so that number is solid. Canada and Spain are the
two most expensive places to stop, but Canada's drivers disagree by 7.2s and
Spain's only by 2.3s, so Spain's number is the better measurement even though
it's the lower one.

### Best number of stops (the simulator)

| Circuit | Our model says | Real field actually did | |
| --- | --- | --- | --- |
| Austria | 2 | 2 | ✅ |
| Barcelona | 3 | 3 (split between 2 and 3) | ✅ |
| Belgium | 1 | 1 | ✅ |
| Hungary | 2 | 2 | ✅ |
| Japan | 1 | 1 | ✅ |
| Miami | 1 | 1 | ✅ |
| **Spain** | **1** | **1** (14 of 18 finishers) | ✅ |
| Australia | 1 | 2 | one off |
| Britain | 1 | 2 | one off |
| Netherlands | 2 | 3 | one off |
| Monaco | 1 | 5 | way off |

**7 out of 11 exactly right, and 3 more only off by one.**

### Spain was a real out of sample test

Every other circuit in that table was already in the data when the model was
built. Spain wasn't. It's round 14, the model was built on the first 13, and we
didn't change a single setting for it.

The model said **1 stop**, and **14 of the 18 finishers did 1 stop**.

It makes sense from the two numbers too. Spain has expensive stops (26.8s) and
tyres that barely wear (0.011), so paying 27 seconds for tyres that were fine
anyway is a waste. You stop once because the rules make you and thats it.

The interesting bit is every time it's wrong, the real teams stopped **more**
than the model said, never less. When we split out the stops made under a
safety car, the extra ones were basically all safety car stops:

| Circuit | Model | Real, green flag stops only |
| --- | --- | --- |
| Australia | 1 | 0 |
| Britain | 1 | 1 |
| Netherlands | 2 | 2 |
| Monaco | 1 | 1 |

That makes sense. When a safety car comes out everyone is driving slow, so a
stop is suddenly cheap and teams grab fresh tyres. **The model plans a clean
race and doesn't know safety cars exist yet**, which is exactly what Monte
Carlo is going to fix.

## How we got here, step by step

### Step 1: look at the data

Plot lap time vs tyre age for one driver, one line per stint, and fit a straight
line through each. The slope is the degradation.

We only use "clean" laps: green flag, not going in or out of the pits, and
FastF1 thinks the timing is accurate.

**Result:** slopes were way too small (0.007 to 0.087) and the stints were 3
seconds apart from each other. Something was hiding the degradation.

### Step 2: fuel

A 2026 car starts with around 72 kg of fuel and ends near empty. Lighter is
faster, about 0.03 seconds per kg. So the car gets faster all race for reasons
that have nothing to do with tyres.

```
corrected time = raw time - (laps remaining) x kg per lap x 0.03
```

**Result:** slopes roughly doubled and the gap between stints went from 2.5s
to 0.8s.

We also tried 70, 72 and 75 kg to see if the guess mattered. The answer moved
by less than 0.005 s/lap, so it doesn't really matter which one we pick.

### Step 3: every driver in one race

4 stints from one driver doesn't prove anything, so we did all 22 drivers at
Hungary.

**Result:** hards looked like they degraded **faster** than softs, which is
backwards. At Hungary mediums were only used at the start, hards in the middle
and softs at the end, so we couldn't tell "which tyre" apart from "when in the
race".

### Step 4: every race

Pool all the races together so each tyre shows up at different points in a
race.

**Result:** still backwards. Then we found out why. Teams pick hards
**because** the track is harsh:

```
             SOFT  MEDIUM  HARD
Canada         19      22     2     <- one of the easiest tracks on tyres
Barcelona       9      18    34     <- the harshest
```

So the hard pile was mostly Barcelona and the soft pile was mostly Canada. We
were comparing tracks, not tyres.

When we compared each stint only against other stints **at the same race**, all
three tyres came out at zero. The backwards result was about tracks the whole
time.

### Step 5: track evolution

Cars lay rubber down so the track gets grippier and lap times drop. Canada and
China even showed **negative** degradation (tyre getting faster with age),
which can't happen, so something was missing.

We can't look this one up like fuel so we measure it. The trick is that
**drivers pit at different times.** On lap 30 one driver might be on 18 lap old
tyres and another on 5 lap old tyres. Same track at the same moment, so any gap
between them has to be the tyres.

**Result:** the track gives back about **1 to 2 seconds** over a race, which is
normal for F1. China got fixed, Canada is still negative. Miami and Monaco
actually got **slower**, probably heat at Miami.

It couldn't fix soft vs hard though. The track is the same for everyone so it
shifts every stint in a race by the same amount, and that can't change the
order.

### Step 6: traffic

Following another car means driving in its dirty air, less grip and a slower
lap. Our fit was blaming that on the tyre.

FastF1 doesn't have a "gap to the car ahead" column so we built it. Sort the
cars by when they crossed the line, take away the time of the car in front, and
that's the gap. Under 1.5 seconds counts as dirty air and the lap gets thrown
out.

**How much does dirty air actually cost?** We went back and measured it properly,
seconds lost per lap compared to being in clean air:

```
gap to car ahead    season median
< 0.5s                   +0.615
0.5 - 1.0s               +0.289
1.0 - 1.5s               +0.071
1.5 - 2.0s               +0.015
2.0 - 3.0s               -0.053
```

So it fades out by about 1 to 1.5 seconds, which means our 1.5s cutoff is safely
past the point where it matters. Monaco is the worst at **+2.1 seconds a lap**
when youre within half a second, because theres nowhere to pass so you just sit
there.

Worth knowing for 2026: being within 1 second gets you overtake mode from the new
battery system, so you should get some time back on the straights. The data says
it helps but doesnt cancel dirty air out, because the 0.5 to 1.0 band still costs
+0.29 a lap.

**Result:** the circuit numbers got better, but soft vs hard still didn't move:

```
             stints  negative  soft_hard   SOFT   MEDIUM   HARD
no filter       496         1        6/9  -0.000  +0.002  -0.001
>= 1.5s         379         1        4/9  -0.001  +0.003  -0.000
>= 3.0s         288         1        4/9  -0.007  +0.002  -0.000
```

### Step 7: pit loss

A pit stop wrecks two laps, the in lap and the out lap:

```
pit loss = (in lap + out lap) - (2 x normal lap)
```

The normal lap is the driver's own median pace around the stop.

We throw out:
- **Red flag stops.** Tyres get changed for free on the grid. At Monza, Leclerc
  crashed on lap 3 and 21 of the 32 stops were from that red flag
- **Safety car and VSC stops.** Everyone's slow so the stop is cheap
- **Circuits with less than 8 stops.** Not enough to trust (China and Italy)

We originally only dropped the red flag stops by accident, because FastF1
leaves their lap times empty. Now the code checks for red flags on purpose.

### Step 8: the simulator

Fuel, track evolution and car speed are the same whatever strategy you pick,
so they cancel out. Only two things change between strategies:

```
time lost = deg x (tyre age added up over every lap) + stops x pit loss
```

We built a function that goes lap by lap, adds up what the tyre costs, and adds
the pit loss whenever you stop.

Some things we found at Barcelona:

- **The best single stop is right in the middle (lap 34).** Stopping early or
  late are both bad because one of the tyres ends up really old. Stopping on
  lap 50 was even worse than lap 20
- **So stints should always be evenly split**, which means we don't need to try
  millions of combinations
- **There's a sweet spot for how many stops:**

```
1 stop     171.0 s lost
2 stops    144.2
3 stops    142.8   <- best
4 stops    151.4
5 stops    165.1
```

Too few stops and the tyres get ancient. Too many and you keep paying for tyres
that weren't even worn yet.

At Barcelona 2 and 3 stops are only 1.4 seconds apart, basically a tie. And the
real field split exactly 7 and 7 between them.

### Step 9: Monte Carlo, adding randomness

Step 8 plans a perfectly clean race, which is why it kept saying fewer stops than
the real teams did. Real races have safety cars, and a safety car makes a stop
way cheaper because everyone else is crawling.

We measured how often they actually happen instead of guessing:

```
full safety car :  7 periods / 855 laps = 0.0082 per lap
SC + VSC        : 28 periods / 855 laps = 0.0327 per lap
```

We count **periods**, not laps. Monaco had 1 safety car that stayed out for 14
laps, thats one event not fourteen. Using laps would spawn new safety cars over
and over.

Version 1 uses full safety cars only (0.82% chance per lap, lasting about 7 laps)
and assumes a stop under one costs half as much.

Then we run the same strategy 10,000 times, rolling fresh safety cars each time,
and average it.

**Finding 1: more stops benefit more from safety cars.**

```
stops   clean race   with safety cars   saved
1            171.0              170.3     0.7
2            144.2              142.8     1.4
3            142.8              140.8     2.0
```

About 0.7s per stop. Each stop is basically a lottery ticket on a safety car
landing at the right moment.

**Finding 2: reacting to a safety car only helps if it comes close to when you
were going to stop anyway.**

```
react window   avg time lost
           0          140.89     ignore safety cars
           4          140.04     best
          30          153.01     always pit under safety car
```

Always pitting under a safety car is **12 seconds worse than never reacting**.
Pit 15 laps early and you save 12s on the stop but wreck your stint balance, so
one tyre ends up ancient. Thats why you sometimes see a team leave a driver out
under a safety car while everyone at home screams at the telly.

The whole thing runs 30,000 simulated races in 0.43 seconds, so we never needed
numpy for it. Good thing we measured before optimising.

### Step 10: validation, how wrong is it?

Everything before this checked the model against things we already knew. This
is the first time we put a number on how wrong it is.

**The idea.** Nobody has an answer key for "what was the best strategy". But we
do have one for "how far apart did two drivers finish". So we take **teammates**
who ran different strategies, feed their real pit laps into the model, and see
if the gap it predicts matches the gap that really happened.

Teammates because they share the same car, so most of what is left between them
is the strategy. And we use the **change** in the gap from the end of lap 1 to
the flag, so starting position doesnt count.

**First attempt: failed.** Assuming teammates are identical was wrong, one of
them is usually just quicker on the day, and that swamped everything.

```
                     correlation   direction right   median error
strategy only            0.28         26 of 43          13.3s
say nothing               -               -              9.3s
```

Worse than useless. Guessing "no difference at all" beat it.

**Second attempt: add how quick each driver actually was.** Measured from the
step 5 fit, on clean air laps only, with tyre age taken out. Clean air only
matters: if we used every lap then a driver stuck in traffic would look slow and
we would be feeding the answer back into the question.

```
                     correlation   direction right   median error
strategy + pace          0.71         33 of 43          12.5s
```

The model now knows **which** teammate gained from their strategy 77% of the
time. But it still got the **size** wrong, always the same way: it predicted
about twice as much as really happened.

**Third: correct the size, honestly.** A consistent error can be corrected, but
if you work out the correction on all the races and then report how good it is
on those same races, of course it looks good. So we split the season in half,
worked out the correction on one half, and tested it on races the correction had
never seen. Then swapped and did it again.

```
  pairs tested            43
  say nothing             9.3s
  our model, uncorrected  12.5s
  our model, corrected     8.2s
  within 10 seconds       25 of 43
```

**The honest verdict.** It beats guessing, but only just, and the correction
itself wasnt stable (one half wanted x0.35 and the other x0.80). So:

- **Picking a strategy: works.** 7 of 11 circuits matched the real field, it got
  Spain right on a race it had never seen, and it picks the better teammate
  strategy 77% of the time.
- **Predicting a gap in seconds: not really.** Typical error about 8 seconds
  against gaps that are typically 9, and no stable correction factor.

Why: the model has no idea other cars exist. Rejoin behind a slower car and you
lose 10 seconds, and it cant see any of that. Same reason we couldnt measure
compounds back in step 6, the thing we want is smaller than the noise around it.

### Step 11: the what if tool

Take a driver's real race, try what they could have done instead, and say what
each option would have been worth.

1. Pull their real pit laps out of the data and cost them with the model
2. Try every alternative. 1, 2 and 3 stops at every lap
3. Best alternative minus what they did = seconds left on the table
4. Turn those seconds into positions using the real gaps around them

It uses the REAL safety cars from that race, not random ones like step 9, so
the alternatives get judged in the same conditions the driver actually had.

**Example: Norris, Spain 2026.**

```
safety car on laps: [13, 14, 15]
he stopped on lap:  [15]                model says 24.2s

best 1 stop: [15]           24.2s      +0.0s
best 2 stop: [13, 15]       37.4s     -13.1s
best 3 stop: [14, 28, 44]   71.1s     -46.9s
```

**The model says he ran the single best strategy available.** Not a good one, the
best one. Out of every combination it tried, nothing beat what he actually did.

He finished 3rd, 0.7 seconds behind Verstappen.

![what if chart](outputs/11_2026_Spanish_NOR_whatif.png)

You can see it on the chart. The dip in all three lines around laps 13 to 15 is
the safety car, where a stop is half price. Norris is the black dot, sitting
right at the bottom of it.

**So why did he lose the position?** Not the strategy. The stop itself:

```
driver  lap  time in the pit lane
NOR      15        35.0        <- P3
ANT      14        31.8        <- P1
VER      14        31.1        <- P2
median    -        31.6
```

He was **3.2 seconds slower than his teammate in the pit lane**, and lost P2 by
0.7. That one stop was the whole race.

**And the tool cant see any of it**, because it charges everyone the circuit's
typical pit loss. Perfect strategy, ruined in the pit box, and the model says
everything was fine.

Thats the clearest example of what step 10 measured. Fixing it is next: use each
driver's real stop times instead of the circuit average.


## What didn't work

**We can't tell which tyre compound degrades faster.** We tried for 4 steps and
stopped.

The reason in two numbers:

- two drivers, same race, same tyre, their numbers disagree by about **0.043 s/lap**
- the soft vs hard difference we're looking for is about **0.004 s/lap**

The noise is **10 times bigger** than the thing we're trying to find. It's like
trying to hear someone whisper at a concert.

On top of that some races only have 1 or 2 soft stints, and teams drive
different tyres differently on purpose (hards get nursed, softs get pushed), so
no filter can separate that out.

So this measures **circuits** well but can't measure **compounds**, and that's
fine to say.

### Tested but couldn't tell

Monaco and Miami both showed the track getting slower. The idea was traffic at
Monaco and heat at Miami. After filtering traffic, Monaco moved 0.016 to 0.024
but Miami moved more (0.009 to 0.022). Too small to call either way.

## Known problems

- **Canada still has negative degradation**, which is impossible. Don't know why yet
- **Degradation is a straight line.** Real tyres sometimes hit a "cliff" where
  they're fine and then suddenly fall apart
- **The simulator has no safety cars**, so it always plans a clean race
- **Gaps are only measured at the finish line.** Two cars 2s apart at the line
  could be right behind each other in a corner
- **Lapped cars are handled badly.** A lapped car right behind the leader looks
  like clean air
- **Track evolution is a straight line too**, really it improves fast early on and then flattens
- **No wet races**

## What's next

**Better predictions.** Step 10 showed the weak spot is traffic. Ideas:
- model where you rejoin after a stop, so the model knows other cars exist
- use the dirty air table from step 6 to charge time for laps spent behind someone

**Later ideas:**
- add VSC as well as full safety cars
- test the 0.5 safety car pit loss assumption instead of assuming it
- work out why Canada still has negative degradation
- publish the dirty air table, nobody has measured that for 2026

## Scripts

Run them in order, each one saves what the next one needs.

| Script | What it does |
| --- | --- |
| `scripts/01_first_look.py` | Lap time vs tyre age for one driver |
| `scripts/02_fuel_correction.py` | Same thing with fuel taken out |
| `scripts/03_all_drivers.py` | Every driver in one race |
| `scripts/04_all_races.py` | Every race. Saves `data/stints_2026.csv` |
| `scripts/05_track_evolution.py` | Measures and removes track evolution |
| `scripts/06_clean_air.py` | Removes laps in traffic. Saves `data/stints_2026_cleanair.csv` |
| `scripts/07_pit_loss.py` | Measures pit loss. Saves `data/pit_stops_2026.csv` |
| `scripts/08_simulator.py` | Finds the best number of stops for every circuit |
| `scripts/09_monte_carlo.py` | Adds random safety cars and tests reacting to them |
| `scripts/10_validation.py` | Checks the model against real teammate battles |
| `scripts/11_what_if.py` | What could a driver have done instead, with charts |
| `scripts/strategy.py` | Shared bits used by more than one script |

## Running

Run from the project folder:

```bash
python scripts/08_simulator.py
```

When a new race happens just re-run 04, 06, 07 and 08. They pick up new races
by themselves.

## Setup

```bash
pip install fastf1 pandas matplotlib numpy
```

## Notes

- Built with help from Claude (Anthropic). The direction, the questions and the
  decisions are mine, and I can explain any line in here. The step by step
  writeups above are the actual record of how it went, dead ends included.
- `cache/` is where FastF1 saves downloaded races. It's not in git. First run
  of a race is slow, after that it's instant
- 2026 is a brand new set of rules with new cars, so we can't use data from
  older seasons, and nobody has a public degradation model for these cars yet
