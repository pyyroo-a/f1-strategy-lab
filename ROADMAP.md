# Where this is going

README has the method and the numbers. EXPLAINED has the same story without the
jargon. This file is the other direction: what is left to do, and where the
project is heading after that.

(Read this one when coming back to the project cold and wondering what the point
of the next bit is, *source of motivation*) 

---

## What the project is right now

Tyre degradation and pit strategy, measured from 2026 lap times.

We know how much a lap costs per lap of tyre age at each circuit, we know what a
pit stop costs at each circuit, and we can take a real race and say what the
driver should have done instead. Steps 1 to 12 are done and the website is live.

Everything so far comes from **timing data only**. No video, no telemetry. Just
when each car crossed the line.

---

## The three things left on the current project

### Step 13: track temperature

My computer vision prof asked "what if the same circuit degrades differently at
different times", and he is right. Our per circuit numbers might partly be that
day's weather rather than the track itself.

The good version of this test is inside a single race, not across circuits.
Within one race the surface, the corners and the car never change, so if hot
stints degrade more than cool stints the only thing that can explain it is the
temperature. That gives hundreds of comparisons instead of 15.

Weather data including TrackTemp does load from FastF1, so this is testable now.

The outcome is a measurement and an honest write up, same as step 6 and step 13
on traffic. We are not going to correct the model for it yet.

### Step 14: circuit shape from the speed traps

Telemetry does not load for 2026, so there is no corner map. But the laps table
does have four speed samples per lap, SpeedI1, SpeedI2, SpeedFL and SpeedST.

Hypothesis, stated before measuring so we cannot fudge it afterwards:
degradation is driven by how fast the slow parts of a lap are relative to top
speed. Fast flowing corners hurt the tyre, hairpins do not.

Dumb baseline to beat: top speed on its own. Only two ideas get tested, because
14 circuits is 14 data points and anything more is just fishing.

### Step 15: make the website interactive

Drag the pit laps around and watch the cost move, plus a ghost line showing
where the driver would have been lap by lap. It is all arithmetic we already do,
so no backend needed.

---

## After that: the computer vision direction

This is the part that is not decided yet. The end goal will get pinned down
later. What follows is the reasoning so far so we do not lose it.


### The actual idea

**The strategy lab becomes the answer key.**

We already know, from timing data, exactly how far one car was behind another on
any lap of any race. So take footage of that same lap, try to estimate the gap
from the image alone, and compare the two.

Then we can say, as a measured number in seconds, how accurate the vision model
is. I think most student CV projects cannot say that. They show a few frames with boxes
drawn on and say it looks about right. This one would have a validation section
in the same style as step 10, saying here is the error, here is where it falls
apart, here is what it cannot do.

The professor suggested estimating traffic from footage, and this is the version
of that idea with a way to mark its own homework.

### The camera problem

I raised this with him: a race broadcast does not follow one driver, it keeps
cutting between cars and angles. He agreed it is a real challenge.

Three ways round it, in the order we would try them:

1. **Use onboard footage instead of broadcast.** An onboard camera never cuts
   away, and when you are following someone the car ahead is right there in
   frame. Big when close, small when far. The camera switching problem does not
   exist because we picked a camera that does not switch.
2. **Detect the cuts.** When a broadcast changes camera nearly every pixel
   changes at once, so comparing each frame to the one before finds the cuts.
   That chops the race into shots, and then we only have to work out who is on
   screen once per shot instead of once per frame.
3. **Read the on screen graphics.** The driver name and position are burned into
   the corner of the picture almost all the time, as text on a clean background.
   Reading that tells us who we are looking at without recognising the car at
   all.

The order matters. Doing onboard first means proving the measurement works while
only having one hard problem to deal with. Going straight at broadcast footage
means two hard problems at once and no way of knowing which one broke.

### Why 2026 forces this shape

Telemetry does not load for 2026. No speed traces, no positions. So the obvious
CV project, estimating speed from video with telemetry as the answer key, cannot
be checked against 2026 data.

Gaps can, because gaps come from lap times and those are fine. That is a real
constraint we found rather than guessed, and it is what points the CV work at
traffic rather than speed.

### Boundary with the other project

Racing lines and how a driver takes a corner belong in the driver lines project,
not here. This project stays about the race: gaps, traffic, strategy.

If the CV work happens it either lives in its own repo or in a clearly separate
folder here. The two projects share the idea that one measures the truth and the
other tries to see it, and that is all they should share.

---

## Open questions

- What exactly the CV end goal is. Estimating a gap in seconds is the clearest
  target so far but it is not locked in.
- Whether onboard footage for full races is findable, or only qualifying laps.
- Whether to keep the CV work in this repo or start a new one.
- Still no idea why Canada shows negative degradation.
- Does track conditions like weather affect degradation (probably does but need to check)
- How much does the shape of the circuit factor into the degradation.
