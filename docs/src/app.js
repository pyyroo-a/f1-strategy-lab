const DATA = JSON.parse(document.getElementById("site-data").textContent);
const raceSel = document.getElementById("race");
const drvSel = document.getElementById("driver");

const fmt = (n, d = 1) => (n >= 0 ? "" : "-") + Math.abs(n).toFixed(d);
const signed = (n, d = 1) => (n >= 0 ? "+" : "-") + Math.abs(n).toFixed(d);

// ---------- pickers ----------
const ordered = [...DATA.races].sort(
  (a, b) => DATA.circuits[a].round - DATA.circuits[b].round
);
for (const r of ordered) {
  const o = document.createElement("option");
  o.value = r;
  o.textContent = "R" + String(DATA.circuits[r].round).padStart(2, "0") + "  " + r;
  raceSel.appendChild(o);
}

function fillDrivers(race) {
  drvSel.innerHTML = "";
  const entries = Object.entries(DATA.drivers[race]);
  entries.sort((a, b) => (a[1].finish ?? 99) - (b[1].finish ?? 99));
  for (const [code, d] of entries) {
    const o = document.createElement("option");
    o.value = code;
    o.textContent = (d.finish ? "P" + d.finish + "  " : "     ") + code +
                    (d.team ? "  " + d.team : "");
    drvSel.appendChild(o);
  }
}

// ---------- chart ----------
const W = 640, H = 360, M = { t: 18, r: 78, b: 46, l: 54 };
const SERIES = [
  { key: "1", label: "1 stop", varname: "--s1" },
  { key: "2", label: "2 stops", varname: "--s2" },
  { key: "3", label: "3 stops", varname: "--s3" },
];

function drawChart(race, d) {
  const svg = document.getElementById("chart");
  svg.innerHTML = "";
  const ns = "http://www.w3.org/2000/svg";
  const add = (tag, attrs, text) => {
    const el = document.createElementNS(ns, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (text != null) el.textContent = text;
    svg.appendChild(el);
    return el;
  };

  const all = SERIES.flatMap(s => d.curves[s.key] || []);
  if (!all.length) return;
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys, d.plan_cost), y1 = Math.max(...ys, d.plan_cost);
  const pad = (y1 - y0) * 0.08 || 1;
  y0 -= pad; y1 += pad;

  const X = v => M.l + ((v - x0) / (x1 - x0 || 1)) * (W - M.l - M.r);
  const Y = v => M.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - M.t - M.b);

  // safety car band, the thing that explains most of these curves
  const sc = (DATA.circuits[race].safety_car_laps || []).filter(l => l >= x0 && l <= x1);
  if (sc.length) {
    const a = Math.min(...sc), b = Math.max(...sc);
    add("rect", { x: X(a), y: M.t, width: Math.max(X(b) - X(a), 2),
                  height: H - M.t - M.b, class: "sc-band" });
    add("text", { x: X(a) + 4, y: M.t + 12, class: "sc-text" }, "SAFETY CAR");
  }

  // y grid
  const ticks = 5;
  for (let i = 0; i <= ticks; i++) {
    const v = y0 + (i / ticks) * (y1 - y0);
    add("line", { x1: M.l, x2: W - M.r, y1: Y(v), y2: Y(v), class: "grid-line" });
    add("text", { x: M.l - 8, y: Y(v) + 4, "text-anchor": "end", class: "axis-text" },
        Math.round(v));
  }
  // x ticks
  const step = Math.max(5, Math.round((x1 - x0) / 6 / 5) * 5);
  for (let v = Math.ceil(x0 / step) * step; v <= x1; v += step) {
    add("text", { x: X(v), y: H - M.b + 18, "text-anchor": "middle", class: "axis-text" }, v);
  }
  add("text", { x: M.l + (W - M.l - M.r) / 2, y: H - 8, "text-anchor": "middle",
                class: "axis-title" }, "lap of the first pit stop");
  add("text", { x: 14, y: M.t + (H - M.t - M.b) / 2, class: "axis-title",
                transform: `rotate(-90 14 ${M.t + (H - M.t - M.b) / 2})`,
                "text-anchor": "middle" }, "time lost (s)");

  // series
  for (const s of SERIES) {
    const pts = d.curves[s.key] || [];
    if (!pts.length) continue;
    const col = `var(${s.varname})`;
    add("path", {
      d: pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" "),
      class: "series", stroke: col
    });
    const last = pts[pts.length - 1];
    add("text", { x: X(last[0]) + 7, y: Y(last[1]) + 4, class: "series-label", fill: col }, s.label);
  }

  // what they actually did
  add("circle", { cx: X(d.actual_stops[0]), cy: Y(d.plan_cost), r: 5.5, class: "actual-dot" });
  const lx = X(d.actual_stops[0]), ly = Y(d.plan_cost);
  const flip = lx > W * 0.6;
  add("text", {
    x: lx + (flip ? -10 : 10), y: ly - 12,
    "text-anchor": flip ? "end" : "start", class: "actual-label"
  }, "what they did");

  // hover readout
  const hover = add("line", { x1: 0, x2: 0, y1: M.t, y2: H - M.b, class: "hover-line", opacity: 0 });
  const readout = document.getElementById("readout");
  const base = SERIES.map(s =>
    `<span><span class="swatch" style="background:var(${s.varname})"></span>${s.label}</span>`
  ).join("");
  readout.innerHTML = base;

  svg.onpointerleave = () => { hover.setAttribute("opacity", 0); readout.innerHTML = base; };
  svg.onpointermove = ev => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    if (px < M.l || px > W - M.r) return;
    const lap = Math.round(x0 + ((px - M.l) / (W - M.l - M.r)) * (x1 - x0));
    hover.setAttribute("x1", X(lap)); hover.setAttribute("x2", X(lap));
    hover.setAttribute("opacity", 1);
    readout.innerHTML = `<span><b>stop on lap ${lap}</b></span>` + SERIES.map(s => {
      const pt = (d.curves[s.key] || []).find(p => p[0] === lap);
      return pt ? `<span><span class="swatch" style="background:var(${s.varname})"></span>${s.label} <b>${fmt(pt[1])}s</b></span>` : "";
    }).join("");
  };
}

// ---------- panels ----------
function render() {
  const race = raceSel.value, code = drvSel.value;
  const d = DATA.drivers[race][code];
  const c = DATA.circuits[race];
  if (!d) return;

  document.getElementById("chart-title").textContent =
    code + " at " + race + ", " + DATA.season;

  // verdicts
  const planGood = d.gain <= 1;
  const stopsBad = d.slow_stop_cost > 1;
  const stopsGood = d.slow_stop_cost < -1;
  const v = [];

  v.push(`<div class="verdict ${planGood ? "good" : "warn"}">
    <span class="pill ${planGood ? "good" : "warn"}">The plan</span>
    <span class="headline">${planGood
      ? "They got it about right"
      : "Worth " + fmt(d.gain) + "s to stop differently"}</span>
    <span class="detail">${planGood
      ? "Nothing beat what they ran by more than a second."
      : "Best was " + d.best_stops + " stop" + (d.best_stops > 1 ? "s" : "") +
        ", on lap " + d.best_plan.join(" and ") + "."}</span>
  </div>`);

  v.push(`<div class="verdict ${stopsBad ? "warn" : stopsGood ? "good" : ""}">
    <span class="pill ${stopsBad ? "warn" : stopsGood ? "good" : ""}">The stops</span>
    <span class="headline">${stopsBad
      ? fmt(d.slow_stop_cost) + "s lost in the pit box"
      : stopsGood ? fmt(-d.slow_stop_cost) + "s gained by the crew"
      : "Normal service"}</span>
    <span class="detail">${d.pit_lane_times.map(([lap, s]) =>
      "Lap " + lap + ": " + s.toFixed(1) + "s in the pit lane").join(". ")}.
      Typical here is ${c.typical_pit_lane.toFixed(1)}s.</span>
  </div>`);

  const passed = d.would_pass || [];
  v.push(`<div class="verdict ${passed.length ? "good" : ""}">
    <span class="pill ${passed.length ? "good" : ""}">The result</span>
    <span class="headline">${passed.length
      ? "Worth " + passed.length + " place" + (passed.length > 1 ? "s" : "")
      : d.finish ? "Finished P" + d.finish : "No change"}</span>
    <span class="detail">${passed.length
      ? "The " + fmt(d.gain) + "s would have got them past " + passed.join(", ") + "."
      : d.lapped ? "Finished a lap or more down, so there was nobody close to catch."
      : "Nothing they could have done put them past the car ahead."}</span>
  </div>`);

  document.getElementById("verdicts").innerHTML = v.join("");

  // breakdown
  const rows = [
    ["Tyres and pit stops", d.tyres_and_stops, ""],
    ["Stuck behind other cars", d.traffic, "plus"],
    ["Pit crew, vs a normal stop", d.slow_stop_cost, d.slow_stop_cost >= 0 ? "plus" : "minus"],
  ];
  document.getElementById("breakdown").innerHTML =
    rows.map(([k, val, cls]) =>
      `<div class="row"><span class="k">${k}</span><span class="v ${cls}">${
        cls ? signed(val) : fmt(val)}s</span></div>`).join("") +
    `<div class="row total"><span class="k">Time lost, total</span><span class="v">${fmt(d.total)}s</span></div>` +
    `<div class="row"><span class="k">Best they could have done</span><span class="v">${fmt(d.best_cost)}s</span></div>`;

  // circuit facts
  const f = [
    ["Tyre wear", c.deg.toFixed(3) + " s/lap"],
    ["A stop costs", c.pit_loss.toFixed(1) + "s"],
    ["Stuck behind a car for", c.laps_stuck.toFixed(1) + " laps"],
    ["Race length", c.laps + " laps"],
    ["Safety car", c.safety_car_laps.length
      ? "laps " + Math.min(...c.safety_car_laps) + " to " + Math.max(...c.safety_car_laps)
      : "none"],
    ["They stopped on", "lap " + d.actual_stops.join(", ")],
  ];
  document.getElementById("facts").innerHTML = f.map(([k, val]) =>
    `<div class="fact"><span class="k">${k}</span><span class="v">${val}</span></div>`).join("");

  const flag = document.getElementById("borrowed");
  flag.hidden = !c.pit_loss_borrowed;
  if (c.pit_loss_borrowed) {
    flag.textContent = "Only " + c.stops_measured + " green flag stops survived here, " +
      "so the pit stop cost is borrowed from the season typical. Pit loss only spans " +
      "about 3 seconds across circuits, so this does not change which strategy wins.";
  }

  drawChart(race, d);
}

// ---------- season tables ----------
function tables() {
  const rows = Object.entries(DATA.circuits);

  const build = (el, header, data, fmtv, maxv) => {
    const max = Math.max(...data.map(r => Math.abs(r[1])));
    document.getElementById(el).innerHTML =
      `<thead><tr><th>Circuit</th><th>${header}</th><th></th></tr></thead><tbody>` +
      data.map(([name, val, dim]) =>
        `<tr class="${dim ? "dim" : ""}"><td>${name}</td><td class="n">${fmtv(val)}</td>` +
        `<td style="width:64px"><span class="bar" style="width:${Math.max(3, (Math.abs(val) / max) * 56)}px"></span></td></tr>`
      ).join("") + "</tbody>";
  };

  build("t-deg", "s / lap",
    rows.map(([n, c]) => [n, c.deg, false]).sort((a, b) => b[1] - a[1]),
    v => v.toFixed(3));

  build("t-pit", "seconds",
    rows.map(([n, c]) => [n, c.pit_loss, c.pit_loss_borrowed]).sort((a, b) => b[1] - a[1]),
    v => v.toFixed(1));

  build("t-ot", "laps stuck",
    rows.map(([n, c]) => [n, c.laps_stuck, false]).sort((a, b) => b[1] - a[1]),
    v => v.toFixed(1));
}

raceSel.onchange = () => { fillDrivers(raceSel.value); render(); };
drvSel.onchange = render;

// open on a race with a story in it
raceSel.value = DATA.races.includes("Azerbaijan") ? "Azerbaijan" : ordered[0];
fillDrivers(raceSel.value);
if (DATA.drivers[raceSel.value]["SAI"]) drvSel.value = "SAI";
render();
tables();
