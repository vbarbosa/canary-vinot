// Drag and drop from the item catalog, the outfit palette and small page helpers.
(function () {
  const csrf = () => JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRF-Token"];
  const qty = () => Math.max(1, parseInt((document.getElementById("qty") || {}).value || "1", 10));

  function send(values) {
    htmx.ajax("POST", "/acao", { values, target: "#toast", headers: { "X-CSRF-Token": csrf() } });
  }

  function onDrop(evt) {
    const el = evt.item, zone = evt.to;
    el.remove();
    if (zone.dataset.kitBuilder !== undefined) return addToKit(el.dataset.id, el.title);
    const alvo = zone.dataset.alvo;
    if (el.dataset.kit) send({ action: "give_kit", alvo, arg1: el.dataset.kit });
    else if (el.dataset.id) send({ action: "give_item", alvo, arg1: el.dataset.id, arg2: qty() });
    zone.classList.add("flash");
    setTimeout(() => zone.classList.remove("flash"), 600);
  }

  const kit = [];
  function addToKit(id, title) {
    if (!id) return;
    kit.push([id, qty(), title]);
    document.getElementById("kit-items").value = kit.map(k => k[0] + ":" + k[1]).join(",");
    document.getElementById("kit-list").innerHTML = kit.map(k => `<li><img src="/icone/${k[0]}.png" class="mini"> ${k[1]}x ${k[2]}</li>`).join("");
  }

  function init(root) {
    root.querySelectorAll("[data-source]").forEach(el => {
      if (el._sortable) return;
      el._sortable = Sortable.create(el, { group: { name: "gift", pull: "clone", put: false }, sort: false, animation: 120, delay: 80, delayOnTouchOnly: true });
    });
    root.querySelectorAll(".drop").forEach(el => {
      if (el._sortable) return;
      el._sortable = Sortable.create(el, { group: { name: "gift", pull: false, put: true }, sort: false, onAdd: onDrop });
    });
    root.querySelectorAll("[data-ts]").forEach(el => { el.textContent = new Date(el.dataset.ts * 1000).toLocaleString("pt-BR"); });
    root.querySelectorAll("[data-ago]").forEach(el => { el.textContent = ago(el.dataset.ago); });
    // Logs read bottom-up: open with the newest line in view.
    root.querySelectorAll("pre.log").forEach(el => { el.scrollTop = el.scrollHeight; });
  }

  function ago(ts) {
    const s = Date.now() / 1000 - ts;
    if (s < 3600) return "há " + Math.max(1, Math.round(s / 60)) + " min";
    if (s < 86400) return "há " + Math.round(s / 3600) + " h";
    if (s < 86400 * 60) return "há " + Math.round(s / 86400) + " dias";
    return new Date(ts * 1000).toLocaleDateString("pt-BR");
  }

  // Highlight the file picked in the log list.
  document.addEventListener("click", e => {
    const a = e.target.closest(".log-files a");
    if (!a) return;
    document.querySelectorAll(".log-files a.active").forEach(x => x.classList.remove("active"));
    a.classList.add("active");
  });

  // Outfit palette: pick a body part, then a color.
  document.addEventListener("click", e => {
    const part = e.target.closest(".part");
    if (part) {
      part.parentElement.querySelectorAll(".part").forEach(b => b.classList.remove("active"));
      part.classList.add("active");
      return;
    }
    const sw = e.target.closest(".palette b");
    if (sw) {
      const form = sw.closest("form"), active = form.querySelector(".part.active");
      form.querySelector(`input[name=${active.dataset.part}]`).value = sw.dataset.color;
      active.querySelector("i").style.background = sw.style.background;
    }
  });

  // Schedule form: show only the fields of the chosen action and kind; hidden fields are disabled so they are not sent.
  function syncJobForm() {
    const form = document.querySelector(".job-form");
    if (!form) return;
    const pick = (attr, value) => form.querySelectorAll(`[${attr}]`).forEach(el => {
      const on = el.getAttribute(attr).split(" ").includes(value);
      el.hidden = !on;
      el.querySelectorAll("input, select, textarea").forEach(i => (i.disabled = !on));
    });
    pick("data-show", form.querySelector("#job-action").value);
    pick("data-kind", form.querySelector("#job-kind").value);
  }
  document.addEventListener("change", e => { if (e.target.closest(".job-form")) syncJobForm(); });
  document.addEventListener("DOMContentLoaded", syncJobForm);

  document.addEventListener("htmx:load", e => init(e.detail.elt));
  document.addEventListener("htmx:afterSwap", e => {
    if (e.detail.target.id === "toast") setTimeout(() => (e.detail.target.innerHTML = ""), 4000);
  });
  document.addEventListener("DOMContentLoaded", () => init(document));
})();
