# The whole thing, in plain English

The README has all the numbers and the method. This one is just the story, no
jargon. If you only read one file, read this one.

---

## What this project is

**A pit stop costs you about 20 seconds. Old tyres cost you a bit of time every
lap.**

So: is fresh rubber worth the 20 seconds it takes to go and get it, and if it
is, when should you stop?

That is the entire project. Everything else is working out those two numbers
properly and then using them.

---

## Why it is harder than it sounds

You might think you can just time a driver's laps, watch them get slower, and
call that tyre wear.

You cannot, because loads of other things are changing at the same time:

- the car is **burning fuel**, getting lighter, getting faster
- the **track is getting grippier** as cars lay rubber down
- the driver might be **stuck behind someone**, losing time to their dirty air
- some **tracks are just harsher** on tyres than others

Anything we fail to remove gets blamed on the tyre. So most of this project is
peeling those things off one at a time.

---

## How we did it, step by step

### 1. Look at the data

Plot one driver's lap times against how old their tyres are. Fit a straight line
through it. The slope of that line is tyre wear.

**Result:** the numbers were way too small. Something was hiding them.

### 2. Remove the fuel

A car starts with about 72 kg of fuel and ends near empty. Lighter is faster, so
the car quietly speeds up all race for reasons that have nothing to do with
tyres. We work out how much and subtract it.

**Result:** the numbers roughly doubled. That was the missing piece.

We also checked whether the exact fuel number mattered. Tried 70, 72 and 75 kg
and the answer barely moved, so guessing it is fine.

### 3 and 4. Do it for everyone, in every race

One driver proves nothing. So: all 22 drivers, then all the races.

**Result:** hard tyres looked like they wore out FASTER than soft ones, which is
backwards.

**Why:** teams pick the hard tyre *because* the track is harsh on tyres. So the
"hard tyre" pile was full of Barcelona and the "soft tyre" pile was full of
Canada. We were comparing tracks, not tyres.

### 5. Remove the track getting faster

Cars lay rubber down and the track gets grippier through the race. Two races
were showing tyres getting FASTER with age, which is impossible, so we knew
something was missing.

The clever bit: **drivers pit at different times.** So on lap 30, one car is on
18 lap old tyres and another is on 5 lap old tyres, both on the same track at
the same moment. Any gap between them has to be the tyres, not the track. That
is what lets you separate the two.

**Result:** about 1 to 2 seconds a race comes from the track improving.

### 6. Throw out laps spent in traffic

Following another car means driving in its messy air. Less grip, slower lap.

FastF1 doesn't tell you the gap to the car ahead, so we built it: line every car
up by when they crossed the line, and the difference between neighbours is the
gap.

We also measured, for the first time publicly as far as we know, **how much
dirty air actually costs in the 2026 rules**:

```
within 0.5s of the car ahead   costs 0.61s a lap
0.5 to 1.0s                    costs 0.29s a lap
1.0 to 1.5s                    costs 0.07s a lap
beyond that                    nothing
```

Monaco is the worst at over 2 seconds a lap when you are right behind someone.

### The thing we tried and could not do

**We cannot tell which tyre compound wears fastest.** We chased it for four
steps and then stopped.

The reason, in two numbers: two drivers in the same race on the same tyre
disagree with each other by about **0.043 seconds a lap**. The soft versus hard
difference we are hunting is about **0.004**.

The noise is ten times bigger than the thing we want. Like trying to hear a
whisper at a concert.

So this project measures **circuits** well and **cannot** measure compounds.
Saying that out loud is better than pretending.

### 7. How much does a pit stop really cost?

When you pit, two laps get wrecked: the one where you slow down to come in, and
the one where you go back out on cold tyres. Compare those two against what the
driver was lapping just before and after, and the difference is the cost.

**Result:** about 22 seconds, which is right where real F1 sits.

Most of that is not the tyre change, which takes about 2 seconds. It is the pit
lane, where the limit is 80 km/h and cars race that same ground at 250.

We throw out stops under a red flag (tyres get changed for free on the grid) and
under a safety car (everyone is crawling so it is cheap). And if a circuit has
fewer than 8 usable stops left, we refuse to give a number at all rather than
make one up.

### 8. The simulator

Here is the trick that makes this simple: **fuel, track evolution and how fast
your car is are the same whatever strategy you pick**, so they cancel out. Only
two things change between strategies:

```
time lost = tyre wear x (how old your tyres were on every lap)
          + number of stops x what a stop costs
```

That is the whole simulator.

What it found:

- **the best single stop is right in the middle of the race.** Stop too early or
  too late and one set of tyres ends up ancient
- so stints should be **evenly spaced**
- and there is a **sweet spot** for how many stops. Too few and your tyres die,
  too many and you keep paying 22 seconds for tyres that were fine

It picked the same number of stops as the real field at most circuits.

### 9. Adding randomness

Real races have safety cars, and a stop under one is half price because everyone
else is crawling.

We measured how often they actually happen (0.82% chance per lap, lasting about
7 laps) and then simulated each race **thousands of times**, rolling the dice
each run.

Two findings:

**More stops benefit more.** Each stop is a lottery ticket on a safety car
turning up at the right moment.

**Reacting to a safety car only helps if it comes near your planned stop.**
Always pitting under a safety car is 12 seconds WORSE than never reacting,
because diving in 15 laps early wrecks your stint balance. That is why you
sometimes see a team leave a driver out while everyone at home screams.

And the right rule changes by track. High wear tracks: be picky. Low wear
tracks: grab any safety car going.

### 10. How wrong is it?

Everything above was checking the model against things we already knew. This is
where we put a number on it.

**The test:** take two **teammates** who ran different strategies. Same car, so
most of what is left between them is the strategy. Does the model predict the
gap that really happened?

**First try: total failure.** Worse than guessing "no difference at all".
Because teammates are not identical, one of them is usually just quicker.

**Second try: add how quick each one was.** Big improvement. The model now
correctly picks **which** teammate gained from their strategy about 8 times out
of 10. But it kept exaggerating the size, always in the same direction, roughly
double.

**Third try: correct the exaggeration, honestly.** Work out the correction using
half the season, then test it on the other half that the correction never saw.
Otherwise you are just marking your own homework.

**The result:** about 8 seconds of error against gaps that are typically 9. It
beats guessing, but only just.

### The Baku bug

I watched the Azerbaijan race and took notes, and it was obviously a one stop.
Then the data said most drivers stopped twice, six laps apart, some of them soft
to soft. Nobody does that, so I went looking.

Turned out Albon crashed and the whole field was sent **through** the pit lane
without stopping. FastF1 records that as a pit stop. **15 of Baku's 36 stops
never happened.**

The fix: a stop only counts if the tyre actually changed, either a different
compound afterwards or the tyre age resetting.

It cleaned up other races too. Monaco had **44** pit lane trips with no tyre
change.

### 12 and 13. Chasing traffic, and finding out it was not the problem

Step 10 said the model's weakness was traffic, so we went after it.

First we measured **how hard each track is to overtake at**: if you are within
1.5 seconds of someone, what is the chance you are still stuck next lap?

Monaco came out hardest (stuck for 6 laps), Monza easiest (2.5 laps). That is
the most famous pair in F1 for exactly this, and the code worked it out from lap
times alone.

Baku surprised me by coming out near the hard end despite that huge straight.
Watching it back explained why: you close up on the straight but then you are at
turn 1 and have to compromise your line, so one chance a lap and taking it
wrecks your exit.

Then we put it in the model. And re-ran the validation.

**It barely moved.**

So we checked whether traffic even matters, by measuring the real thing instead
of estimating it. A driver spends about 15 laps stuck behind someone, and it
costs them about **4 seconds** across a whole race. The gaps we are failing to
explain are 10 to 30 seconds.

**Traffic was not the problem.** We were wrong.

### So what IS the problem?

We broke the gap between teammates into pieces and measured each:

```
pace          16.1s   <- the biggest by far
strategy       8.1s
traffic        2.9s
mistakes       0.9s
ACTUAL GAP     9.3s
```

**The pace estimate is bigger than the gap it is trying to predict.** It swamps
everything else.

Why: we measure pace from clean air laps, and those are a biased sample. When a
slow driver is finally alone they are often cruising with nothing to race, while
a quick driver's clean laps are more often laps where they are pushing. That
exaggerates the difference, and then it gets multiplied by 70 laps.

That is the next thing to fix.

### 11. The what if tool

Take a real driver's race, try everything they could have done instead, and say
what each one was worth. With charts.

It splits a race into **two separate questions**: was the plan good, and was the
stop good?

**Norris at Spain 2026** is the example. The model says he ran the single best
strategy available, out of every combination it tried. He still finished third.

Why? His pit stop took **3.4 seconds longer than normal**, and he lost second
place by 0.7 seconds. I noticed it watching the race, and the data backed it up
to the tenth.

Perfect plan, lost in the pit box. Which is the same conclusion anyone watching
the race would reach.

---

## What it can and cannot do

**Good at:**

- measuring how harsh each circuit is on tyres
- measuring what a stop costs at each circuit
- measuring how hard each track is to pass at
- picking the right number of stops
- ranking which strategy was better, about 8 times out of 10

**Not good at:**

- telling you which tyre compound wears faster (the noise is 10x the signal)
- predicting a gap in seconds reliably (the pace estimate is roughly double)

**Still broken:**

- Canada shows tyres getting faster with age, which is impossible, and we still
  do not know why

---

## The thing worth taking away

Almost every real finding in here came from **a number looking stupid**.

Tyres getting faster with age led to the track evolution work. Hard tyres
looking worse than softs led to two confounds. A 2100 second pit stop led to the
red flag bug. "That was a one stop, wasn't it" led to 15 fake pit stops.

And twice I was proved wrong by my own data. Traffic was supposed to be the big
problem, and it was not.

Being able to say exactly which half of your model works is worth more than a
model that claims both and quietly gets caught out later.
