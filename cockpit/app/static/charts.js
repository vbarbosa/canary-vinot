// Metrics history: one small uPlot chart per measure (one y-axis each), fed by /metricas/dados.
(function () {
  const INK = "#9a8f7c", GRID = "rgba(154,143,124,.15)", LINE = "#d9a441", FILL = "rgba(217,164,65,.14)";
  const PERCENT = new Set(["cpu", "mem", "disk"]);
  let period, charts = [], timer;

  const compact = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
  const fmt = (v, unit) => (v == null ? "—" : (Math.abs(v) >= 100000 ? compact.format(v) : (Math.round(v * 10) / 10).toLocaleString("pt-BR")) + unit);

  function build(el, t, y) {
    const key = el.dataset.key, unit = el.dataset.unit, box = el.querySelector(".plot");
    const opts = {
      width: box.clientWidth, height: 160,
      padding: [8, 8, 0, 0],
      cursor: { points: { size: 8, fill: LINE, stroke: "#15130f", width: 2 }, drag: { x: false, y: false } },
      legend: { show: false },
      hooks: { setCursor: [u => showAt(u, u.cursor.idx)] },
      scales: { x: { time: true }, y: PERCENT.has(key) ? { range: [0, 100] } : { range: (u, lo, hi) => [0, Math.max(hi * 1.15, key === "players" ? 5 : 1)] } },
      axes: [
        { stroke: INK, grid: { stroke: GRID, width: 1 }, ticks: { stroke: GRID }, font: "11px system-ui",
          values: (u, vals) => { const long = u.scales.x.max - u.scales.x.min > 2 * 86400;
            return vals.map(v => new Date(v * 1000).toLocaleString("pt-BR", long ? { day: "2-digit", month: "2-digit" } : { hour: "2-digit", minute: "2-digit" })); } },
        { stroke: INK, grid: { stroke: GRID, width: 1 }, ticks: { show: false }, size: 44, font: "11px system-ui",
          values: (u, vals) => vals.map(v => (Math.abs(v) >= 100000 ? compact.format(v) : v.toLocaleString("pt-BR")) + (unit === "%" ? "%" : "")) },
      ],
      series: [{}, { stroke: LINE, width: 2, fill: FILL, points: { show: false }, spanGaps: false }],
    };
    opts.hooks.init = [u => { u._el = el; }];
    return new uPlot(opts, [t, y], box);
  }

  function setNow(el, y) {
    const last = [...y].reverse().find(v => v != null);
    el._now = last == null ? "sem dados ainda" : "agora " + fmt(last, el.dataset.unit);
    el.querySelector(".now").textContent = el._now;
  }

  // Hovering a chart swaps "agora X" in its header for the value at that moment.
  function showAt(u, idx) {
    const out = u._el.querySelector(".now");
    if (idx == null) return (out.textContent = u._el._now || "");
    const when = new Date(u.data[0][idx] * 1000).toLocaleString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    out.textContent = when + " · " + fmt(u.data[1][idx], u._el.dataset.unit);
  }

  async function load() {
    const r = await fetch(document.querySelector(".charts").dataset.src + "?periodo=" + period, { credentials: "same-origin" });
    if (r.redirected || !r.ok) return;
    const data = await r.json();
    document.querySelectorAll(".chart").forEach((el, i) => {
      const g = data[el.dataset.group], y = g[el.dataset.key];
      setNow(el, y);
      if (charts[i]) charts[i].setData([g.t, y]);
      else charts[i] = build(el, g.t, y);
    });
  }

  function start() {
    if (!document.querySelector(".charts")) return;
    period = document.querySelector("#periods button.active").dataset.period;
    document.getElementById("periods").addEventListener("click", e => {
      const b = e.target.closest("button[data-period]");
      if (!b) return;
      period = b.dataset.period;
      document.querySelectorAll("#periods button").forEach(x => x.classList.toggle("active", x === b));
      load();
    });
    new ResizeObserver(() => charts.forEach(u => u.setSize({ width: u._el.querySelector(".plot").clientWidth, height: 160 })))
      .observe(document.querySelector(".charts"));
    load();
    clearInterval(timer);
    timer = setInterval(load, 60000);
  }

  document.addEventListener("DOMContentLoaded", start);
})();
