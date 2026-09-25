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

  // Kit editor: add by dragging, change quantities, remove, or load an existing kit to edit or duplicate.
  let kit = [];
  function renderKit() {
    const list = document.getElementById("kit-list");
    if (!list) return;
    document.getElementById("kit-items").value = kit.map(k => k.id + ":" + k.qty).join(",");
    list.innerHTML = kit.length ? "" : '<li class="muted small">Nenhum item ainda.</li>';
    kit.forEach((k, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<img src="/icone/${k.id}.png" class="mini" alt=""><span class="grow"></span>
        <input type="number" min="1" max="1000" value="${k.qty}" aria-label="Quantidade">
        <button type="button" class="outline small danger" title="Tirar do kit">✕</button>`;
      li.querySelector(".grow").textContent = k.name;
      li.querySelector("input").addEventListener("change", e => { k.qty = Math.min(1000, Math.max(1, parseInt(e.target.value, 10) || 1)); renderKit(); });
      li.querySelector("button").addEventListener("click", () => { kit.splice(i, 1); renderKit(); });
      list.appendChild(li);
    });
  }
  function addToKit(id, title) {
    if (!id) return;
    const found = kit.find(k => k.id == id);
    if (found) found.qty = Math.min(1000, found.qty + qty());
    else kit.push({ id, qty: qty(), name: title });
    renderKit();
  }
  function loadKit(data) {
    const form = document.getElementById("kit-form");
    form.elements.id.value = data.id;
    form.elements.nome.value = data.name;
    kit = data.items.map(([id, q, name]) => ({ id, qty: q, name }));
    document.getElementById("kit-title").textContent = data.id ? "Editando: " + data.name : "Novo kit";
    document.getElementById("kit-save").textContent = data.id ? "Salvar alterações" : "Salvar kit";
    document.getElementById("kit-cancel").hidden = false;
    renderKit();
    document.getElementById("kit-editor").scrollIntoView({ behavior: "smooth" });
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-edit-kit]");
    if (b) return loadKit(JSON.parse(b.dataset.editKit));
    if (e.target.id === "kit-cancel") loadKit({ id: "", name: "", items: [] }), (e.target.hidden = true);
  });
  document.addEventListener("DOMContentLoaded", renderKit);

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
  function loadJob(d) {
    const form = document.getElementById("job-form");
    form.reset();
    form.elements.id.value = d.id || "";
    ["nome", "acao", "alvo", "texto", "tipo", "minutos", "hora"].forEach(k => { if (d[k] !== undefined && d[k] !== "") form.elements[k].value = d[k]; });
    form.querySelectorAll("[name=arg1]").forEach(el => (el.value = d.arg1 || el.value));
    if (d.arg2) form.querySelector("[name=arg2]").value = d.arg2;
    form.querySelectorAll("[name=dias]").forEach(c => (c.checked = (d.dias || "").includes(c.value)));
    document.getElementById("job-title").textContent = d.id ? "Editando: " + d.nome : "Nova tarefa";
    document.getElementById("job-save").textContent = d.id ? "Salvar alterações" : "Agendar";
    document.getElementById("job-cancel").hidden = !d.id;
    syncJobForm();
    form.scrollIntoView({ behavior: "smooth" });
  }
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-edit-job]");
    if (b) loadJob(JSON.parse(b.dataset.editJob));
    else if (e.target.id === "job-cancel") loadJob({});
  });
  document.addEventListener("DOMContentLoaded", syncJobForm);

  document.addEventListener("htmx:load", e => init(e.detail.elt));
  document.addEventListener("htmx:afterSwap", e => {
    if (e.detail.target.id === "toast") setTimeout(() => (e.detail.target.innerHTML = ""), 4000);
  });
  document.addEventListener("DOMContentLoaded", () => init(document));
})();
