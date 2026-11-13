"use strict";
// TESL Forge web app: talks only to the local API (tesl serve). No build step, no external code.

const $ = (sel, root = document) => root.querySelector(sel);
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
};
const ATTRS = ["Strength", "Intelligence", "Willpower", "Agility", "Endurance"];
const EMOTES = ["Hello", "GoodGame", "ThankYou", "NicePlay", "Taunt", "Implore", "Oops", "Sorry"];
const EMOTE_LABEL = { Hello: "Hello", GoodGame: "Good game", ThankYou: "Thank you", NicePlay: "Nice play", Taunt: "Taunt", Implore: "Hurry up", Oops: "Oops", Sorry: "Sorry" };
const state = { mods: [], mod: null, view: null, detail: null };

async function api(path, opts = {}) {
  const res = await fetch(path, { method: opts.method || "GET", headers: opts.body ? { "Content-Type": "application/json" } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok || data.error) throw new Error(data.error || res.statusText);
  if (opts.method && opts.method !== "GET") Drafts.saved();
  return data;
}

// ---- Drafts: unsaved form text survives a reload or a server restart (kept in this browser only) ---------------------
const Drafts = {
  key() { return `forge.draft.${state.mod || "_"}.${state.view || "_"}`; },
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } },
  put(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  drop(k) { try { localStorage.removeItem(k); } catch (e) {} },
  fields(main) { return [...main.querySelectorAll("input:not([type=file]):not([type=checkbox]):not([type=range]), textarea, select")]
    .filter(el => !el.closest("#modal") && !el.closest(".prefs")); },
  // form pages: remember every field (by its place on the page) as it is typed
  watch(main) {
    const k = this.key();
    let timer = null;
    main.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => {
      const values = this.fields(main).map(el => el.value);
      if (values.some(v => v)) this.put(k, { time: new Date().toLocaleString(), count: values.length, values });
    }, 600); });
    const d = this.get(k);
    if (!d || !d.values || !d.values.some(v => v)) return;
    const bar = h("div", { class: "msg warn", style: "display:flex;gap:10px;align-items:center" },
      h("span", { style: "flex:1" }, `Unsaved changes from ${d.time} on this page.`),
      h("button", { onclick: () => { const els = this.fields(main); if (els.length === d.count) els.forEach((el, i) => { el.value = d.values[i]; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); });
        else toast("The page changed since; the draft could not be placed.", true); bar.remove(); } }, "Restore"),
      h("button", { onclick: () => { this.drop(k); bar.remove(); } }, "Discard"));
    main.prepend(bar);
  },
  saved() { if (state.view !== "stories") this.drop(this.key()); },
};
async function upload(file) {
  const res = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": file.name }, body: file });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || "upload failed");
  return data.path;
}
function toast(text, err = false) {
  const t = h("div", { class: err ? "err" : "" }, text);
  $("#toast").append(t);
  setTimeout(() => t.remove(), err ? 7000 : 3500);
}
async function act(fn, okText) {
  try { const r = await fn(); if (okText) toast(okText); return r; }
  catch (e) { toast(e.message, true); throw e; }
}
const artUrl = (c, size = "thumb") => c.art || `/api/cards/${c.id}/art?size=${size}`;
const attrsOf = c => (c.subtypes || []).filter(s => ATTRS.includes(s));
const dots = c => { const a = attrsOf(c); return (a.length ? a : ["Neutral"]).map(x => h("span", { class: "attr " + x, title: x })); };

// ---- shell -----------------------------------------------------------------------------------------------------------
// A card without exported art shows a neutral tile instead of a broken image.
document.addEventListener("error", e => { const t = e.target; if (t.tagName === "IMG" && !t.dataset.fallback) { t.dataset.fallback = "1";
  t.src = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#1b181f"/><text x="5" y="6.2" font-size="3" text-anchor="middle" fill="#5d5566">no art</text></svg>'); } }, true);

// Theme and text size (sidebar), saved per computer.
function initPrefs() {
  const theme = $("#pref-theme"), size = $("#pref-size");
  if (!theme || !size) return;
  theme.value = document.documentElement.dataset.theme || "dark";
  const z = parseFloat(document.documentElement.style.fontSize) / 14 || 1;
  size.value = String([0.85, 1, 1.15, 1.3, 1.5].reduce((a, b) => Math.abs(b - z) < Math.abs(a - z) ? b : a));
  const keep = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
  theme.onchange = () => { document.documentElement.dataset.theme = theme.value; keep("forge.theme", theme.value); };
  size.onchange = () => { document.documentElement.style.fontSize = (14 * parseFloat(size.value)) + "px"; keep("forge.textScale", size.value); };
}

async function boot() {
  initPrefs(); initHelp();
  const info = await api("/api/info");
  $("#version").textContent = "v" + info.version;
  $("#game-path").textContent = "Game: " + info.game;
  if (!$("#support")) {
    const foot = $("#game-path");
    foot.parentNode.insertBefore(h("div", { id: "support", class: "support" }, h("span", {}, "Support TESL Forge"),
      h("a", { href: "https://ko-fi.com/archangelaries", target: "_blank", rel: "noopener" }, "Ko-fi"),
      h("a", { href: "https://www.patreon.com/c/ArchAngelAries", target: "_blank", rel: "noopener" }, "Patreon")), foot);
  }
  $("#new-mod-btn").onclick = newModDialog;
  document.querySelectorAll("#sidebar nav a").forEach(a => a.onclick = () => go(a.dataset.global ? null : state.mod, a.dataset.view));
  window.onhashchange = route;
  await loadMods();
  route();
}
async function loadMods() {
  state.mods = (await api("/api/mods")).mods;
  const list = $("#mod-list");
  list.innerHTML = "";
  if (!state.mods.length) list.append(h("div", { class: "sub", style: "padding:4px 10px" }, "No mods yet."));
  for (const m of state.mods)
    list.append(h("div", { class: "mod-item" + (m.id === state.mod ? " active" : ""), onclick: () => go(m.id, "overview"), title: m.id },
      h("span", { class: "dot" + (m.enabled ? " on" : "") }), h("span", {}, m.name || m.id)));
}
function go(mod, view) { location.hash = (mod ? "mod/" + encodeURIComponent(mod) + "/" : "") + view; }
let routeToken = 0;
async function route() {
  const token = ++routeToken;   // a slower, older navigation never overwrites a newer one
  const parts = location.hash.replace(/^#/, "").split("/").map(decodeURIComponent);
  let mod = null, view = parts[0] || "";
  if (parts[0] === "mod") { mod = parts[1]; view = parts[2] || "overview"; }
  state.mod = mod; state.view = view;
  await loadMods();
  if (token !== routeToken) return;
  $("#mod-nav").classList.toggle("hidden", !mod);
  if (mod) $("#mod-nav-title").textContent = (state.mods.find(m => m.id === mod) || {}).name || mod;
  document.querySelectorAll("#sidebar nav a").forEach(a => a.classList.toggle("active", a.dataset.view === view && (!!a.dataset.global) === !mod));
  const main = $("#main");
  main.innerHTML = "";
  main.append(h("div", { class: "sub" }, h("span", { class: "spinner" }), " Loading…"));
  try {
    const detail = mod ? await api("/api/mods/" + encodeURIComponent(mod)) : null;
    if (token !== routeToken) return;
    state.detail = detail;
    const view_fn = VIEWS[view] || VIEWS.welcome;
    main.innerHTML = "";
    await view_fn(main);
    if (token === routeToken && mod && view !== "overview") pageIssues(main, view);
    if (token === routeToken && state.view !== "stories") Drafts.watch(main);
  } catch (e) { main.innerHTML = ""; main.append(h("div", { class: "msg error" }, e.message)); }
}
const refresh = () => route();

function newModDialog() {
  const id = h("input", { placeholder: "my-skyrim-mod" }), name = h("input", { placeholder: "My Skyrim Mod" });
  const author = h("input", { placeholder: "you" }), desc = h("textarea", { placeholder: "What the mod adds" });
  name.oninput = () => { if (!id.dataset.touched) id.value = name.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); };
  id.oninput = () => id.dataset.touched = "1";
  const starter = h("select", {}, h("option", { value: "blank" }, "Empty mod"));
  const source = h("select", {}), sourceField = field("Copy of", source, "The copy gets its own ids, so both can be enabled together.");
  api("/api/starters").then(r => {
    starter.innerHTML = ""; r.kinds.forEach(k => starter.append(h("option", { value: k.kind }, k.label)));
    r.mods.forEach(m => source.append(h("option", { value: m }, (state.mods.find(x => x.id === m) || {}).name || m)));
  }).catch(() => {});
  const sync = () => { sourceField.style.display = starter.value === "copy" ? "" : "none"; };
  starter.onchange = sync; sync();
  modal(h("div", {}, h("h1", {}, "New mod"), h("p", { class: "sub" }, "A mod is a folder in the suite. It never changes game files."),
    field("Name", name), field("Folder id (letters, digits, dashes)", id), field("Author", author), field("Description", desc),
    field("Start with", starter), sourceField,
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { onclick: closeModal }, "Cancel"),
      h("button", { class: "primary", onclick: async () => {
        const r = await act(() => api("/api/mods", { method: "POST", body: { id: id.value, name: name.value, author: author.value, description: desc.value,
          starter: starter.value, source: starter.value === "copy" ? source.value : null } }), "Mod created");
        if (r && r.note) toast(r.note, true);
        await loadMods();
        const firstView = { card: "cards", story: "stories", mode: "modes", opponent: "opponents" }[starter.value] || "overview";
        closeModal(); go(id.value, firstView); } }, "Create"))));
}
let modalReturn = null;
function modal(content) {
  modalReturn = document.activeElement;
  $("#modal-body").innerHTML = ""; $("#modal-body").append(content); $("#modal").classList.remove("hidden");
  const t = content.querySelector("h1, h2"); if (t) $("#modal").setAttribute("aria-label", t.textContent);
  const first = content.querySelector("input, select, textarea, button"); if (first) first.focus();
}
function closeModal() { $("#modal").classList.add("hidden"); if (modalReturn && modalReturn.focus) modalReturn.focus(); modalReturn = null; }

// Edit an existing item in place (its id and slug stay). fields: [key, label, type, value, options]
// types: text, textarea, number, select, checkbox, file (image/audio upload), contexts (music moments)
function editDialog(kind, item, title, fields) {
  const inputs = {};
  const rows = fields.map(([key, label, type, value, options]) => {
    let el;
    if (type === "textarea") el = h("textarea", { rows: 4 }, value ?? "");
    else if (type === "select") { el = h("select", {}, (options || []).map(o => h("option", { value: o[0] }, o[1]))); el.value = value ?? ""; }
    else if (type === "checkbox") { el = h("input", { type: "checkbox" }); el.checked = !!value; }
    else if (type === "file") {
      let path = null;
      el = dropZone(label + " (optional: keeps the current one)", options || "image/*", p => { path = p; });
      el._get = () => path;
    } else if (type === "contexts") {
      const set = new Set(value || []);
      el = h("div", { style: "max-height:180px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px" },
        (options || []).map(c => { const cb = h("input", { type: "checkbox" }); cb.checked = set.has(c.context); cb.onchange = () => cb.checked ? set.add(c.context) : set.delete(c.context);
          return h("label", { style: "display:flex;gap:6px;align-items:center;color:var(--text)" }, cb, c.label); }));
      el._get = () => [...set];
    } else el = h("input", { type: type === "number" ? "number" : "text", value: value ?? "" });
    inputs[key] = { el, type, value };
    return field(label, el);
  });
  modal(h("div", {}, h("h2", { style: "margin-top:0" }, title), h("p", { class: "sub" }, "Only what you change is saved. The item keeps its id, so decks, stories and collections that use it keep working. Undo with Ctrl+Z."),
    ...rows,
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { onclick: closeModal }, "Cancel"),
      h("button", { class: "primary", onclick: async () => {
        const body = {};
        for (const [key, { el, type, value }] of Object.entries(inputs)) {
          const v = el._get ? el._get() : type === "checkbox" ? el.checked : type === "number" ? (el.value === "" ? null : +el.value) : el.value;
          if (v === null || v === undefined || (type === "file" && !v)) continue;
          if (JSON.stringify(v) !== JSON.stringify(value)) body[key] = v;
        }
        if (!Object.keys(body).length) return closeModal();
        await act(() => api(`/api/mods/${encodeURIComponent(state.mod)}/edit/${kind}/${encodeURIComponent(item)}`, { method: "POST", body }), "Saved");
        closeModal(); refresh();
      } }, "Save changes"))));
}

$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
let fieldSeq = 0;
const field = (label, input, hint) => {
  const lab = h("label", {}, label);
  if (input && /^(INPUT|SELECT|TEXTAREA)$/.test(input.tagName || "")) { if (!input.id) input.id = "f" + (++fieldSeq); lab.htmlFor = input.id; }
  else if (input && input.setAttribute && !input.getAttribute("aria-label")) input.setAttribute("aria-label", label);
  return h("div", { class: "field" }, lab, input, hint ? h("small", { class: "sub" }, hint) : null);
};

// ---- reusable pieces -------------------------------------------------------------------------------------------------
function dropZone(text, accept, onFile) {
  const input = h("input", { type: "file", accept, class: "hidden" });
  const zone = h("div", { class: "drop" }, h("div", {}, text));
  const take = async file => {
    if (!file) return;
    zone.innerHTML = "";
    if (file.type.startsWith("image/")) zone.append(h("img", { src: URL.createObjectURL(file) }));
    zone.append(h("div", {}, h("span", { class: "spinner" }), " ", file.name));
    try {
      const path = await upload(file);
      zone.lastChild.textContent = file.name + " ✓";
      onFile(path, URL.createObjectURL(file), file);
    } catch (e) { zone.lastChild.textContent = e.message; toast(e.message, true); }
  };
  zone.onclick = () => input.click();
  zone.tabIndex = 0; zone.setAttribute("role", "button"); zone.setAttribute("aria-label", text);
  zone.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  input.onchange = () => take(input.files[0]);
  zone.ondragover = e => { e.preventDefault(); zone.classList.add("over"); };
  zone.ondragleave = () => zone.classList.remove("over");
  zone.ondrop = e => { e.preventDefault(); zone.classList.remove("over"); take(e.dataTransfer.files[0]); };
  return h("div", {}, zone, input);
}

function cardPicker(onPick, opts = {}) {
  const box = h("div", {});
  const q = h("input", { placeholder: opts.placeholder || "Search cards by name or text…" });
  const attr = h("select", {}, h("option", { value: "" }, "Any attribute"), [...ATTRS, "Neutral"].map(x => h("option", { value: x }, x)));
  const cost = h("select", {}, h("option", { value: "" }, "Any cost"), [0, 1, 2, 3, 4, 5, 6, 7].map(n => h("option", { value: n }, n === 7 ? "7+" : n)));
  const list = h("div", { class: "picker" });
  let timer = null;
  const extra = opts.extra || (() => []);
  const run = async () => {
    const text = q.value.trim();
    const want = attr.value, wantCost = cost.value;
    const fits = c => (!want || (want === "Neutral" ? !attrsOf(c).length : attrsOf(c).includes(want)))
      && (wantCost === "" || (+wantCost === 7 ? (c.cost || 0) >= 7 : (c.cost || 0) === +wantCost));
    const local = extra().filter(c => (!text || (c.name || "").toLowerCase().includes(text.toLowerCase())) && fits(c));
    const res = await api(`/api/cards?collectible=${opts.all ? 0 : 1}&art=1&limit=60&q=${encodeURIComponent(text)}&attribute=${want === "Neutral" ? "" : want}&cost=${wantCost}`);
    if (want === "Neutral") res.cards = res.cards.filter(fits);
    list.innerHTML = "";
    for (const c of [...local, ...res.cards])
      list.append(h("div", { class: "pick", onclick: () => { list.querySelectorAll(".pick").forEach(x => x.classList.remove("selected")); list.lastChild; onPick(c); } },
        h("img", { src: artUrl(c), loading: "lazy" }),
        h("div", { class: "meta" }, h("b", {}, c.name, c.mod ? " (mod)" : ""), h("small", {}, dots(c), ` ${c.type || ""} · ${c.set || ""} · ${c.text ? c.text.replace(/<[^>]+>/g, "") : "no text"}`)),
        h("span", { class: "num" }, c.cost ?? "")));
  };
  q.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 220); };
  attr.onchange = run; cost.onchange = run;
  box.append(h("div", { class: "toolbar", style: "margin:0 0 6px" }, h("div", { class: "grow" }, q), attr, cost), list);
  run();
  return box;
}

function cardPreview(c, artSrc) {
  const stats = c.type === "Creature";
  return h("div", { class: "cardpreview" },
    h("img", { class: "art", src: artSrc || "" }),
    h("div", { class: "gem" }, c.cost ?? "?"),
    h("div", { class: "name" }, c.name || "New card"),
    h("div", { class: "text", html: (c.text || "").replace(/<color=[^>]+>|<\/color>|<\/?nobr>/g, "") || "&nbsp;" }),
    stats ? h("div", { class: "pa" }, c.attack ?? "?") : null, stats ? h("div", { class: "ph" }, c.health ?? "?") : null);
}

function cropPreviews(src) {
  // The game shows the same square art three ways: full card (deck builder), top band (in hand), centred portrait (board).
  return h("div", { class: "crops" },
    h("figure", {}, h("div", { class: "c", style: `width:120px;height:120px;background-image:url(${src})` }), "Full art"),
    h("figure", {}, h("div", { class: "c", style: `width:120px;height:60px;background-image:url(${src});background-position:center 20%` }), "In hand (top)"),
    h("figure", {}, h("div", { class: "c", style: `width:78px;height:78px;border-radius:50%;background-image:url(${src})` }), "On board"));
}

// ---- views -----------------------------------------------------------------------------------------------------------
const VIEWS = {};
VIEWS.welcome = async main => {
  main.append(h("div", { class: "empty-state" }, h("h1", {}, "TESL Forge"),
    h("p", {}, "Make new cards, decks, avatars, emotes and card backs, or remaster the game's art. No code needed."),
    h("p", {}, state.mods.length ? "Pick a mod on the left." : "Start by creating a mod with ＋."),
    h("button", { class: "primary", onclick: newModDialog }, "Create a mod")));
};

VIEWS.overview = async main => {
  const d = state.detail, v = d.validation;
  const toggle = h("input", { type: "checkbox", checked: d.enabled });
  toggle.onchange = async () => {
    const on = toggle.checked;
    try {
      await api(`/api/mods/${state.mod}/${on ? "enable" : "disable"}`, { method: "POST", body: {} });
      toast(on ? "Enabled: TESL: Everlasting loads it at its next start." : "Disabled.");
    } catch (e) {   // refused (the game would skip it): say why, offer to enable anyway
      if (on && confirm(e.message + "\n\nEnable anyway? The game will skip what cannot load.")) {
        await act(() => api(`/api/mods/${state.mod}/enable`, { method: "POST", body: { force: true } }), "Enabled.");
      } else { toggle.checked = !on; if (!on) toast(e.message, true); }
    }
    loadMods();
  };
  main.append(h("div", {},
    h("h1", {}, d.mod.name || d.mod.id), h("p", { class: "sub" }, d.mod.description || "No description.", " · ", h("code", {}, d.mod.id), d.mod.author ? " · by " + d.mod.author : ""),
    h("label", { class: "switch" }, toggle, h("span", { class: "knob" }), h("span", {}, "Active in TESL: Everlasting")),
    h("div", { class: "stats" },
      [["Cards", d.cards.length, "cards"], ["Decks", d.decks.length, "decks"], ["Avatars", d.avatars.length, "avatars"],
       ["Card backs", d.cardbacks.length, "cardbacks"], ["Remastered images", d.replacements.length, "remaster"]]
        .map(([label, n, view]) => h("div", { class: "stat", style: "cursor:pointer", onclick: () => go(state.mod, view) }, h("b", {}, n), h("span", {}, label)))),
    playtestPanel(),
    detailsPanel(),
    h("h2", {}, "Check ", h("span", { class: "badge " + (v.valid ? "ok" : "bad") }, v.valid ? "ready to play" : "needs fixes")),
    v.errors.length || v.warnings.length ? null : h("p", { class: "sub" }, "No problems found."),
    ...(v.issues || []).map(issueRow),
    h("h2", {}, "How it works"),
    h("p", { class: "sub" }, "Everything you make lives in this mod's folder. Turn the mod on above, then start the offline game: new cards and decks are in your collection, avatars in the avatar picker, card backs in Collection > card backs (or the store), remastered art everywhere it appears.")));
  main.append(h("h2", {}, "History"), historyPanel(state.mod));
};

// Recent changes of a mod with Undo / Redo (also Ctrl+Z / Ctrl+Y anywhere outside a text field).
function historyPanel(mod) {
  const box = h("div", { class: "panel" });
  const draw = async () => {
    const hist = await api(`/api/mods/${encodeURIComponent(mod)}/history`);
    box.innerHTML = "";
    box.append(h("div", { class: "toolbar", style: "margin-top:0" },
      h("button", { disabled: !hist.undo.length, onclick: () => step("undo") }, "↶ Undo"),
      h("button", { disabled: !hist.redo.length, onclick: () => step("redo") }, "↷ Redo"),
      h("small", { class: "sub", style: "margin:0" }, "Every change made in TESL Forge, by the command line or by an agent can be undone. Deleted files come back from the suite's trash.")));
    if (!hist.undo.length) box.append(h("p", { class: "sub" }, "No changes recorded yet."));
    for (const x of hist.undo.slice(0, 12)) box.append(h("div", { class: "row", style: "grid-template-columns:auto 1fr auto;gap:10px;padding:4px 0;border-bottom:1px solid var(--row-line)" },
      h("small", { class: "sub", style: "margin:0" }, x.time.replace("T", " ")), h("span", {}, x.label), h("small", { class: "sub", style: "margin:0" }, `${x.files} file${x.files === 1 ? "" : "s"}`)));
  };
  const step = async kind => { const r = await act(() => api(`/api/mods/${encodeURIComponent(mod)}/${kind}`, { method: "POST", body: {} })); toast(`${kind === "undo" ? "Undid" : "Redid"}: ${r.undone || r.redone}`); refresh(); };
  draw();
  return box;
}

// ---- Help, first-run tour and keyboard shortcuts ------------------------------------------------------------------------
const SHORTCUTS = [["?", "This help"], ["Ctrl+K or /", "Search all mods"], ["Ctrl+S", "Save (the main button of the form you are in)"],
  ["Ctrl+Z / Ctrl+Y", "Undo / redo the last change to this mod"], ["Esc", "Close a dialog"], ["Alt+1 … Alt+9", "Jump to the mod's pages, in sidebar order"],
  ["Tab / Shift+Tab", "Move between controls; Enter or Space presses buttons and drop areas"]];
const TOUR = [
  ["Welcome to TESL Forge", "Forge makes mods for TESL: Everlasting, the offline version of The Elder Scrolls: Legends. It never changes game files: every mod is a folder here, and you turn mods on and off."],
  ["Make a mod", "Press ＋ next to Mods. A mod can start empty, as a copy of another mod (the sample mod is a full starter pack), or with a first card, story, mode or AI opponent."],
  ["Add anything", "The pages under your mod add or replace content: cards, decks, avatars, card backs, boards, music, sounds, game modes, stories, AI opponents, card packs, translations and remastered art. Bulk import brings in many at once."],
  ["Check and play", "Overview shows problems, each linked to the item it is about. Play test enables the mod, starts the game and shows what the game loaded. Every change can be undone with Ctrl+Z."],
  ["Share", "Set the version and what your mod needs on Overview > Details, record releases, and export a .zip from Load order. Others install it there too. Multiplayer only allows art, sound and other local changes unless everyone has the same mods."],
];
function helpDialog() {
  modal(h("div", {}, h("h1", {}, "Help & shortcuts"),
    h("table", { class: "shortcuts" }, SHORTCUTS.map(([k, t]) => h("tr", {}, h("td", {}, h("kbd", {}, k)), h("td", {}, t)))),
    h("p", { class: "sub" }, "Every page starts with a short explanation. Problems in a mod show on the page of the item they are about."),
    h("div", { class: "toolbar" }, h("button", { onclick: () => { closeModal(); tour(0); } }, "Take the tour"), h("span", { class: "grow" }), h("button", { class: "primary", onclick: closeModal }, "Close"))));
}
function tour(i = 0) {
  const [title, text] = TOUR[i];
  modal(h("div", {}, h("small", { class: "sub" }, `${i + 1} of ${TOUR.length}`), h("h1", {}, title), h("p", {}, text),
    h("div", { class: "toolbar" }, h("button", { onclick: () => { try { localStorage.setItem("forge.tourDone", "1"); } catch (e) {} closeModal(); } }, i < TOUR.length - 1 ? "Skip" : "Close"),
      h("span", { class: "grow" }), i > 0 ? h("button", { onclick: () => tour(i - 1) }, "Back") : null,
      i < TOUR.length - 1 ? h("button", { class: "primary", onclick: () => tour(i + 1) }, "Next")
        : h("button", { class: "primary", onclick: () => { try { localStorage.setItem("forge.tourDone", "1"); } catch (e) {} closeModal(); } }, "Start making mods"))));
}
function initHelp() {
  const hb = $("#help-btn"), tb = $("#tour-btn");
  if (hb) hb.onclick = helpDialog;
  if (tb) tb.onclick = () => tour(0);
  // Sidebar links work from the keyboard too.
  document.querySelectorAll("#sidebar nav a").forEach(a => { a.tabIndex = 0; a.setAttribute("role", "link");
    a.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); a.click(); } }); });
  let seen = false;
  try { seen = localStorage.getItem("forge.tourDone") === "1"; } catch (e) { seen = true; }
  if (!seen) setTimeout(() => { if ($("#modal").classList.contains("hidden")) tour(0); }, 600);
}
document.addEventListener("keydown", e => {
  const t = e.target, typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  const modalOpen = !$("#modal").classList.contains("hidden");
  if (e.key === "Escape" && modalOpen) { e.preventDefault(); closeModal(); return; }
  if (modalOpen) return;
  if (!typing && e.key === "?") { e.preventDefault(); helpDialog(); return; }
  if ((!typing && e.key === "/") || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) { e.preventDefault(); go(null, "search"); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    const scope = (t && t.closest && t.closest(".panel")) || $("#main");
    const btn = [...scope.querySelectorAll("button.primary")].find(b => b.offsetParent !== null) || [...$("#main").querySelectorAll("button.primary")].find(b => b.offsetParent !== null);
    if (btn) btn.click(); else toast("Nothing to save on this page.");
    return;
  }
  if (e.altKey && !e.ctrlKey && /^[1-9]$/.test(e.key) && state.mod) {
    const links = [...document.querySelectorAll("#mod-nav a")];
    const a = links[+e.key - 1];
    if (a) { e.preventDefault(); a.click(); }
  }
});

document.addEventListener("keydown", async e => {
  if (!state.mod || !(e.ctrlKey || e.metaKey) || e.altKey) return;
  const t = e.target, typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  const key = e.key.toLowerCase();
  if (typing || !(key === "z" || key === "y")) return;
  e.preventDefault();
  const kind = key === "y" || e.shiftKey ? "redo" : "undo";
  try { const r = await api(`/api/mods/${encodeURIComponent(state.mod)}/${kind}`, { method: "POST", body: {} }); toast(`${kind === "undo" ? "Undid" : "Redid"}: ${r.undone || r.redone}`); refresh(); }
  catch (err) { toast(err.message, true); }
});

// "Make game previews": the game, hidden in the background, draws the mod's cards, card backs, deck banners and boards.
// kinds: which of them this page asks for (all when omitted); note: the line shown beside the button.
function gamePreviewBar(note, kinds) {
  const msg = h("span", { class: "sub" }, note);
  const btn = h("button", { title: "Starts the game hidden (close it first); takes about half a minute plus a few seconds per item", onclick: async () => {
    const r = await act(() => api(`/api/mods/${state.mod}/previews`, { method: "POST", body: kinds ? { kinds } : {} }), null);
    if (!r) return;
    btn.disabled = true;
    const poll = setInterval(async () => {
      const s = await api(`/api/mods/${state.mod}/previews`).catch(() => null);
      if (!s) return;
      msg.textContent = s.message || "";
      if (s.state !== "running") { clearInterval(poll); btn.disabled = false; toast(s.message, s.state === "failed"); (s.problems || []).forEach(p => toast(p, true)); if (s.state === "done") refresh(); }
    }, 2000);
  } }, "Make game previews");
  return h("div", { class: "toolbar" }, btn, msg);
}

VIEWS.cards = async main => {
  const d = state.detail;
  const kwDefs = (await api("/api/keywords")).keywords;
  main.append(h("h1", {}, "Cards"), h("p", { class: "sub" }, "A new card starts from a template card (its frame, type and sounds). Its rules are its keywords plus abilities you take from any cards, with their numbers and summoned cards changed as you like."));
  const grid = h("div", { class: "grid" });
  // Game previews: the cards as the game draws them (it runs hidden in the background).
  if (d.cards.length) main.append(gamePreviewBar(d.cards.some(c => c.preview) ? (d.cards.some(c => c.preview_stale) ? "Some cards changed since their game preview." : "Showing the game's own drawing of each card.") : "Cards show their art until you make game previews.", ["cards"]));
  for (const c of d.cards) grid.append(h("div", { class: "tile" + (c.preview ? " game-preview" : ""), title: (c.text || "").replace(/<[^>]+>/g, "") }, h("img", { src: c.preview || c.art || "", alt: c.name }), c.preview ? null : h("div", { class: "cost" }, c.cost ?? ""),
    h("div", { class: "cap" }, h("b", {}, c.name), h("small", {}, dots(c), ` ${c.type}${c.type === "Creature" ? ` ${c.attack}/${c.health}` : ""}`)),
    h("button", { style: "margin:0 10px 10px", onclick: e => { e.stopPropagation(); editDialog("card", c.slug, "Edit " + c.name, [
      ["name", "Name", "text", c.name], ["cost", "Cost", "number", c.cost], ["attack", "Power", "number", c.attack], ["health", "Health", "number", c.health],
      ["rarity", "Rarity", "select", c.rarity, [["Common", "Common"], ["Rare", "Rare"], ["Epic", "Epic"], ["Legendary", "Legendary"]]],
      ["text", "Card text", "textarea", (c.text || "")], ["art", "New art", "file", null, "image/*"]]); } }, "Edit")));
  if (!d.cards.length) grid.append(h("p", { class: "sub" }, "No cards yet."));
  main.append(grid, h("h2", {}, "New card"));

  const f = { name: h("input", { placeholder: "Card name" }), cost: h("input", { type: "number", min: 0 }), attack: h("input", { type: "number", min: 0 }),
    health: h("input", { type: "number", min: 0 }), rarity: h("select", {}, ["", "Common", "Rare", "Epic", "Legendary"].map(r => h("option", { value: r }, r || "(template's)"))),
    text: h("textarea", { placeholder: "Leave empty to use the abilities' own text" }), unique: h("input", { type: "checkbox" }) };
  // rules: null = the template's own rules untouched; otherwise the list of abilities below (and keywords) define them.
  const sel = { template: null, art: null, artSrc: null, rules: null, keywords: {}, keywordsTouched: false };
  const previewBox = h("div", {}), cropsBox = h("div", {}), rulesBox = h("div", {}), notesBox = h("div", {});
  const tLabel = h("div", { class: "sub" }, "Pick a template card →");
  const autoText = () => {
    const parts = [];
    const kws = Object.entries(sel.keywords).filter(([, v]) => v).map(([k, v]) => v === true ? k : `${k} ${v}`);
    if (kws.length) parts.push(kws.join(", "));
    (sel.rules || []).forEach(r => parts.push(r.text));
    return parts.join("\n");
  };
  const draw = () => {
    const t = sel.template || {};
    const text = f.text.value || (sel.rules || sel.keywordsTouched ? autoText() : t.text);
    const shown = { name: f.name.value, cost: f.cost.value || t.cost, attack: f.attack.value || t.attack, health: f.health.value || t.health, type: t.type, text };
    previewBox.innerHTML = ""; previewBox.append(cardPreview(shown, sel.artSrc || (sel.template ? artUrl(sel.template) : "")));
    cropsBox.innerHTML = ""; if (sel.artSrc) cropsBox.append(cropPreviews(sel.artSrc));
  };
  const addAbilities = async (card, only) => {
    const info = await api(`/api/cards/${card.id}/abilities`);
    sel.rules = sel.rules || [];
    for (const ab of info.abilities) if (!only || only === ab.id)
      sel.rules.push({ card: info.id, cardName: info.name, ability: ab.id, label: ab.label, text: (info.text || "").replace(/<[^>]+>/g, "").replace(info.name, f.name.value || info.name),
        params: ab.params.map(p => ({ ...p, key: p.path.join("."), now: p.value })) });
    drawRules(); draw();
  };
  const drawRules = () => {
    rulesBox.innerHTML = "";
    if (sel.rules === null) { rulesBox.append(h("p", { class: "sub" }, "Using the template's own rules. Add an ability or keyword to build your own.")); return; }
    if (!sel.rules.length) rulesBox.append(h("p", { class: "sub" }, "No abilities: a vanilla card (keywords only)."));
    sel.rules.forEach((r, i) => {
      const textEl = h("div", { class: "sub", style: "margin:4px 0 8px" }, r.text);
      const inputs = r.params.map(p => {
        if (p.type === "card") {
          const name = h("small", { class: "sub" }, " card " + p.now);
          api(`/api/cards?collectible=0&q=${p.now}&limit=1`).then(res => { if (res.cards[0]) name.textContent = " " + res.cards[0].name; });
          return h("div", { class: "field" }, h("label", {}, p.label), h("div", { style: "display:flex;gap:6px;align-items:center" },
            h("button", { onclick: () => modal(h("div", {}, h("h1", {}, "Pick the card"), cardPicker(c => { p.now = c.id; name.textContent = " " + c.name; closeModal(); }, { all: true }))) }, "Change…"), name));
        }
        const inp = h("input", { type: "number", value: p.now, style: "width:90px" });
        inp.oninput = () => {
          const before = p.now; p.now = inp.value === "" ? p.value : +inp.value;
          // keep the ability's text in step when the old number appears exactly once in it (the server does the same on save)
          const pat = new RegExp("(?<![\\d\\w/])" + Math.abs(before) + "(?![\\d\\w/])", "g");
          if (before !== p.now && (r.text.match(pat) || []).length === 1) { r.text = r.text.replace(pat, String(Math.abs(p.now))); textEl.textContent = r.text; }
          draw(); };
        return h("div", { class: "field" }, h("label", {}, p.label), inp);
      });
      rulesBox.append(h("div", { class: "panel", style: "margin-bottom:10px;padding:12px" },
        h("div", { style: "display:flex;gap:8px;align-items:center" }, h("b", { style: "flex:1" }, r.label, h("span", { class: "sub" }, " — from " + r.cardName)),
          h("button", { title: "Remove", onclick: () => { sel.rules.splice(i, 1); drawRules(); draw(); } }, "✕")),
        textEl,
        inputs.length ? h("div", { class: "row" }, inputs) : h("small", { class: "sub" }, "No adjustable numbers.")));
    });
  };
  const kwBox = h("div", { style: "display:flex;flex-wrap:wrap;gap:10px 18px" }, kwDefs.map(k => {
    if (k.kind === "int") {
      const n = h("input", { type: "number", min: 0, value: 0, style: "width:64px" });
      n.oninput = () => { sel.keywords[k.label] = +n.value || 0; sel.keywordsTouched = true; draw(); };
      return h("label", { style: "display:flex;gap:6px;align-items:center;color:var(--text)" }, k.label, n);
    }
    const cb = h("input", { type: "checkbox" });
    cb.onchange = () => { sel.keywords[k.label] = cb.checked; sel.keywordsTouched = true; draw(); };
    return h("label", { class: "switch" }, cb, h("span", { class: "knob" }), h("span", {}, k.label));
  }));
  Object.values(f).forEach(i => i.oninput = draw);
  const addPanel = h("div", { class: "hidden" });
  const donorBox = h("div", {});
  addPanel.append(h("b", {}, "Pick a card, then the ability to take"), cardPicker(async c => {
    const info = await api(`/api/cards/${c.id}/abilities`);
    donorBox.innerHTML = "";
    donorBox.append(h("div", { class: "sub", style: "margin:8px 0" }, (info.text || "").replace(/<[^>]+>/g, "")));
    if (!info.abilities.length) donorBox.append(h("p", { class: "sub" }, "This card has no abilities (keywords only)."));
    info.abilities.forEach(ab => donorBox.append(h("button", { style: "margin:0 6px 6px 0", onclick: () => addAbilities(c, ab.id) }, "Add: " + ab.label)));
  }, { all: true, placeholder: "Search a card with the ability you want…" }), donorBox);
  const rulesPanel = h("div", { class: "panel", style: "margin-top:14px" }, h("h2", { style: "margin-top:0" }, "Rules"),
    h("label", {}, "Keywords"), kwBox, h("h2", {}, "Abilities"), rulesBox,
    h("div", { class: "toolbar" },
      h("button", { onclick: () => addPanel.classList.toggle("hidden") }, "＋ Add an ability from a card"),
      h("button", { onclick: async () => { if (!sel.template) return toast("Pick a template card first.", true); sel.rules = []; await addAbilities(sel.template); } }, "Start from the template's rules"),
      h("button", { onclick: () => { sel.rules = null; drawRules(); draw(); } }, "Use the template's rules as they are")),
    addPanel, notesBox);
  const form = h("div", { class: "panel" },
    field("Name", f.name), h("div", { class: "row" }, field("Cost", f.cost), field("Power", f.attack), field("Health", f.health), field("Rarity", f.rarity)),
    field("Card text (optional: written for you from the rules)", f.text),
    h("div", { class: "field" }, h("label", {}, "Art (square, painted; the game shows the top band in hand and a centred circle on the board)"),
      dropZone("Drop an image or click to choose", "image/*", (path, src) => { sel.art = path; sel.artSrc = src; draw(); }), cropsBox),
    h("label", { class: "switch" }, f.unique, h("span", { class: "knob" }), h("span", {}, "Unique (one copy per deck)")),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!sel.template) return toast("Pick a template card first.", true);
      const body = { name: f.name.value, template: String(sel.template.id), cost: f.cost.value, attack: f.attack.value, health: f.health.value,
        rarity: f.rarity.value, text: f.text.value, art: sel.art, unique: f.unique.checked || null };
      if (sel.rules !== null) body.abilities = sel.rules.map(r => ({ card: String(r.card), ability: r.ability,
        params: Object.fromEntries(r.params.filter(p => p.now !== p.value).map(p => [p.key, p.now])) }));
      if (sel.keywordsTouched) body.keywords = sel.keywords;
      const res = await act(() => api(`/api/mods/${state.mod}/cards`, { method: "POST", body }), "Card created");
      (res.card.notes || []).forEach(n => toast("Check: " + n));
      refresh(); } }, "Create card")));
  const right = h("div", {},
    h("div", { class: "panel" }, h("b", {}, "Template card"), tLabel, cardPicker(c => { sel.template = c; tLabel.textContent = "Template: " + c.name; draw(); }, { all: true })),
    rulesPanel);
  main.append(h("div", { class: "split" }, h("div", {}, form, h("h2", {}, "Preview"), previewBox, h("p", { class: "sub" }, "Approximate: the game draws the real frame, gems and text from the card data.")), right));
  drawRules(); draw();
};

VIEWS.decks = async main => {
  const d = state.detail;
  const modCards = d.cards.map(c => ({ ...c, mod: true }));
  main.append(h("h1", {}, "Decks"), h("p", { class: "sub" }, "Premade decks appear in the deck list. The game's rules: 50–70 cards with one or two attributes, 75–100 with three (plus a three-attribute card), at most 3 copies."));
  if (d.decks.length) main.append(gamePreviewBar(d.decks.some(k => k.preview) ? "Showing each deck's banner as the game draws it in the deck list." : "Banners show their art until you make game previews.", ["decks"]));
  const grid = h("div", { class: "grid wide" });
  for (const k of d.decks) grid.append(h("div", { class: "tile" + (k.preview ? " game-preview" : "") }, k.preview ? h("img", { src: k.preview, style: "aspect-ratio:4/1;object-fit:contain", alt: k.name + " (game preview)" })
    : k.banner ? h("img", { src: k.banner, style: "aspect-ratio:4/1" }) : null,
    h("div", { class: "cap" }, h("b", {}, k.name), h("small", {}, `${k.total} cards`)),
    h("button", { style: "margin:0 10px 10px", onclick: () => editDialog("deck", k.slug, "Edit " + k.name, [
      ["name", "Name", "text", k.name], ["cards_spec", "Cards (one per line: Name x3)", "textarea", (k.cards || []).map(e => `${e.name} x${e.count}`).join("\n")],
      ["art_card", "Banner card (name)", "text", ""]]) }, "Edit")));
  if (!d.decks.length) grid.append(h("p", { class: "sub" }, "No decks yet."));
  main.append(grid, h("h2", {}, "Build a deck"));
  const deck = new Map();
  const name = h("input", { placeholder: "Deck name" }), desc = h("input", { placeholder: "Optional description" });
  let artCard = null;
  const listBox = h("div", { class: "decklist" }), info = h("div", {}), curve = h("div", { class: "curve" });
  const draw = () => {
    listBox.innerHTML = "";
    const rows = [...deck.values()].sort((a, b) => (a.c.cost || 0) - (b.c.cost || 0) || a.c.name.localeCompare(b.c.name));
    for (const r of rows) listBox.append(h("div", { class: "line" }, h("span", { class: "n" }, r.n), dots(r.c), h("span", { class: "nm" }, r.c.name, r.c.mod ? " (mod)" : ""),
      h("span", { class: "sub" }, r.c.cost ?? ""), h("button", { onclick: () => { r.n++; draw(); } }, "+"),
      h("button", { onclick: () => { if (--r.n <= 0) deck.delete(r.c.id); draw(); } }, "−"),
      h("button", { title: "Use for deck art", onclick: () => { artCard = r.c; draw(); } }, artCard && artCard.id === r.c.id ? "★" : "☆")));
    const total = rows.reduce((s, r) => s + r.n, 0), attrs = new Set(rows.flatMap(r => attrsOf(r.c)));
    const probs = [];
    if (attrs.size > 3) probs.push(`${attrs.size} attributes (at most 3)`);
    else if (attrs.size === 3) { if (total < 75 || total > 100) probs.push("three attributes need 75–100 cards"); }
    else if (total < 50 || total > 70) probs.push("needs 50–70 cards");
    rows.filter(r => r.n > 3).forEach(r => probs.push(`${r.c.name}: more than 3 copies`));
    info.innerHTML = "";
    info.append(h("p", {}, h("b", {}, total), " cards · ", [...attrs].map(a => h("span", {}, h("span", { class: "attr " + a }), a + " ")), artCard ? ` · art: ${artCard.name}` : ""),
      ...(probs.length ? probs.map(p => h("div", { class: "msg warn" }, p)) : [h("div", { class: "badge ok" }, "follows the deck rules")]));
    curve.innerHTML = "";
    const buckets = [0, 0, 0, 0, 0, 0, 0, 0];
    rows.forEach(r => buckets[Math.min(7, r.c.cost || 0)] += r.n);
    const max = Math.max(1, ...buckets);
    buckets.forEach((n, i) => curve.append(h("div", { style: `height:${(n / max) * 100}%`, title: `${n} cards` }, h("span", {}, i === 7 ? "7+" : i))));
  };
  const add = c => { const r = deck.get(c.id) || { c, n: 0 }; r.n = Math.min(r.n + 1, 3); deck.set(c.id, r); draw(); };
  main.append(h("div", { class: "split" },
    h("div", { class: "panel" }, field("Name", name), field("Description", desc), info, h("label", {}, "Magicka curve"), curve, h("div", { style: "height:20px" }), listBox,
      h("div", { class: "toolbar" }, h("button", { onclick: () => { deck.clear(); draw(); } }, "Clear"), h("span", { class: "grow" }),
        h("button", { class: "primary", onclick: async () => {
          await act(() => api(`/api/mods/${state.mod}/decks`, { method: "POST", body: { name: name.value, description: desc.value,
            art_card: artCard ? String(artCard.id) : null, cards: [...deck.values()].map(r => ({ id: r.c.id, count: r.n })) } }), "Deck saved");
          refresh(); } }, "Save deck"))),
    h("div", { class: "panel" }, h("b", {}, "Add cards (click to add one copy)"), cardPicker(add, { extra: () => modCards }))));
  draw();
};

VIEWS.avatars = async main => {
  const d = state.detail;
  const voices = (await api("/api/voices")).voices;
  main.append(h("h1", {}, "Avatars & emotes"), h("p", { class: "sub" }, "Your avatars get their own page in the game's avatar picker (four per page). Each has eight emote lines; the AI opponent uses them too when it plays that avatar."));
  const page = h("input", { value: d.avatar_page.name || d.mod.name || "" }), pageDesc = h("input", { value: d.avatar_page.description || "" });
  main.append(h("div", { class: "panel" }, h("div", { class: "row" }, field("Picker page name", page), field("Page description", pageDesc)),
    h("button", { onclick: () => act(() => api(`/api/mods/${state.mod}/avatar-page`, { method: "POST", body: { name: page.value, description: pageDesc.value } }), "Page saved") }, "Save page")));
  const grid = h("div", { class: "grid", style: "margin-top:16px" });
  for (const a of d.avatars) grid.append(h("div", { class: "tile portrait", onclick: () => emoteDialog(a) }, h("img", { src: a.image_url }),
    h("div", { class: "cap" }, h("b", {}, a.name), h("small", {}, `${Object.keys(a.emotes || {}).length}/8 own emote lines · voice ${a.voice || "default"}`)),
    h("button", { style: "margin:0 10px 10px", onclick: e => { e.stopPropagation(); editDialog("avatar", a.slug, "Edit " + a.name, [
      ["name", "Name", "text", a.name], ["voice", "Voice (original avatar)", "select", a.voice || "", [["", "(default voice)"], ...voices.map(v => [v.unique_name, v.unique_name])]],
      ["image", "New portrait", "file", null, "image/*"]]); } }, "Edit")));
  if (!d.avatars.length) grid.append(h("p", { class: "sub" }, "No avatars yet."));
  main.append(grid, h("h2", {}, "New avatar"));
  const name = h("input", { placeholder: "Avatar name" }), voice = h("select", {}, h("option", { value: "" }, "(default voice)"), voices.map(v => h("option", { value: v.unique_name }, `${v.unique_name} · ${v.race}`)));
  const head = h("input", { type: "range", min: 0.05, max: 0.6, step: 0.01, value: 0.22 });
  let img = null, src = null;
  const prev = h("div", { class: "crops" });
  const draw = () => {
    prev.innerHTML = "";
    if (!src) return;
    prev.append(h("figure", {}, h("div", { class: "c", style: `width:114px;height:204px;background-image:url(${src});background-position:center top` }), "Picker portrait"),
      h("figure", {}, h("div", { class: "c", style: `width:110px;height:110px;border-radius:50%;background-image:url(${src});background-size:110px auto;background-position:center ${(+head.value * 100).toFixed(0)}%` }), "Round (profile, match)"));
  };
  head.oninput = draw;
  main.append(h("div", { class: "split" }, h("div", { class: "panel" }, field("Name", name), field("Emote voice", voice, "An original avatar whose voice lines it borrows; set its own lines after creating it."),
    h("div", { class: "field" }, h("label", {}, "Portrait (tall, full body works best)"), dropZone("Drop an image or click", "image/*", (p, s) => { img = p; src = s; draw(); })),
    field("Round crop height", head), prev,
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!img) return toast("Choose an image first.", true);
      await act(() => api(`/api/mods/${state.mod}/avatars`, { method: "POST", body: { name: name.value, image: img, voice: voice.value, head: head.value } }), "Avatar added");
      refresh(); } }, "Add avatar")))));
  extraEmotesSection(main, d);
};

const playUrl = url => new Audio(url).play().catch(e => toast("Can't play: " + e.message, true));

function extraEmotesSection(main, d) {
  const ex = d.extra_emotes || { all_avatars: [], avatars: {} };
  main.append(h("h2", {}, "Extra emotes"), h("p", { class: "sub" }, "Emotes beyond the game's eight. In a match, \"More...\" in the emote panel pages to them. Give them to one of your avatars or to every avatar (the game's own included). \"Works like\" lets the AI use one as a variant of that emote, and it answers yours the same way."));
  const list = h("div", { class: "panel" });
  const row = (x, who, avatar, folder) => list.append(h("div", { class: "row", style: "align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid var(--line)" },
    h("div", { style: "flex:1;min-width:0" }, h("b", {}, x.label), " ", h("span", { class: "sub" }, `"${x.text}"`), h("br"),
      h("small", { class: "sub" }, `${who}${x.like ? " · works like " + EMOTE_LABEL[x.like] : ""}${x.audio ? " · voiced" : ""}`)),
    x.audio ? h("button", { title: "Play", onclick: () => playUrl(`/mod-file/${encodeURIComponent(state.mod)}/${folder}/${encodeURIComponent(x.audio)}`) }, "▶") : null,
    h("button", { class: "danger", onclick: async () => {
      await act(() => api(`/api/mods/${state.mod}/extra-emotes?emote=${encodeURIComponent(x.slug)}${avatar ? "&avatar=" + encodeURIComponent(avatar) : ""}`, { method: "DELETE" }), "Removed"); refresh(); } }, "Remove")));
  for (const x of ex.all_avatars) row(x, "every avatar", null, "emotes");
  for (const [slug, xs] of Object.entries(ex.avatars)) for (const x of xs) row(x, (d.avatars.find(a => a.slug === slug) || { name: slug }).name, slug, "avatars");
  if (!list.children.length) list.append(h("p", { class: "sub" }, "No extra emotes yet."));
  const who = h("select", {}, h("option", { value: "" }, "Every avatar"), d.avatars.map(a => h("option", { value: a.slug }, a.name)));
  const label = h("input", { placeholder: "Button text (short)", maxlength: 24 }), text = h("input", { placeholder: "What the speech bubble says" });
  const like = h("select", {}, h("option", { value: "" }, "(nothing: the AI never says it)"), (d.emote_types || EMOTES).map(k => h("option", { value: k }, EMOTE_LABEL[k] || k)));
  let audio = null;
  main.append(list, h("div", { class: "panel", style: "margin-top:12px" }, h("div", { class: "row" }, field("For", who), field("Works like", like)),
    h("div", { class: "row" }, field("Button", label), field("Line", text)),
    h("div", { class: "field" }, h("label", {}, "Voice clip (optional: WAV, MP3, OGG...)"), dropZone("Drop an audio file or click", "audio/*", p => { audio = p; })),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!text.value && !audio) return toast("Write the line or add a voice clip.", true);
      await act(() => api(`/api/mods/${state.mod}/extra-emotes`, { method: "POST", body: { avatar: who.value, label: label.value, text: text.value, like: like.value, audio } }), "Extra emote added");
      refresh(); } }, "Add extra emote"))));
}

// Listening to the game's own sounds needs FMOD, which TESL Forge may not ship (its licence): fetched once on request.
async function audioSupportBar(main) {
  const s = await api("/api/audio-support").catch(() => null);
  if (!s || s.available) return;
  const msg = h("span", { class: "sub" }, "Listening to the game's own sounds needs game-audio support: the free FMOD library (Firelight Technologies), downloaded once from PyPI (about 2 MB) onto this computer. Your own sound files work without it.");
  const btn = h("button", { class: "primary", onclick: async () => {
    btn.disabled = true;
    const r = await act(() => api("/api/audio-support/install", { method: "POST", body: {} }), "Game-audio support added");
    btn.disabled = false;
    if (r && r.available) refresh();
  } }, "Get game-audio support");
  main.append(h("div", { class: "panel toolbar" }, btn, msg));
}

// One line per dropped file: what it replaced, or why it could not be matched.
function soundReport(box, r, names) {
  box.innerHTML = "";
  const ok = new Map(r.rows.map(x => [x.file, x.action])), bad = new Map(r.failed.map(x => [x.file, x.error]));
  box.append(h("div", { class: "msg " + (r.failed.length ? "warn" : "ok") }, `${r.imported} of ${names.length} file${names.length > 1 ? "s" : ""} used${r.failed.length ? `, ${r.failed.length} could not be matched` : ""}. Changes apply at the game's next start.`));
  for (const n of names) box.append(bad.has(n) ? h("div", { class: "msg error" }, `${n} - ${bad.get(n)}`) : h("div", { class: "msg ok" }, `${n} - ${ok.get(n) || "done"}`));
}

VIEWS.sounds = async main => {
  const d = state.detail;
  main.append(h("h1", {}, "Sounds & voices"), h("p", { class: "sub" }, "Give your cards their own voice lines, and replace any of the game's sounds: card voices and effects, emote lines, story dialogue, the arena announcer, interface sounds. Files of any common format are stored as OGG."));
  await audioSupportBar(main);
  // mod card voices
  main.append(h("h2", {}, "Your cards' voice lines"));
  const cards = h("div", { class: "panel" });
  for (const c of d.card_voices || []) {
    const lines = h("div", { style: "display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:6px" });
    for (const [slot, what] of Object.entries(d.voice_slots || {})) {
      if (slot.startsWith("Shout") && !c.shout) continue;   // shout levels only on shout cards
      const own = c.lines[slot];
      const cell = h("div", { style: "display:flex;gap:6px;align-items:center" }, h("span", { style: "min-width:74px" }, h("b", {}, slot), h("br"), h("small", { class: "sub" }, what)));
      if (own) cell.append(h("button", { title: "Play", onclick: () => playUrl(c.line_urls[slot]) }, "▶"),
        h("button", { class: "danger", title: "Back to the borrowed voice", onclick: async () => {
          await act(() => api(`/api/mods/${state.mod}/card-voice?card=${encodeURIComponent(c.slug)}&line=${slot}`, { method: "DELETE" }), "Line removed"); refresh(); } }, "✕"));
      else cell.append(h("small", { class: "sub" }, c.voice_of ? "borrowed" : "—"));
      cell.append(dropZone(own ? "replace" : "add", "audio/*", async p => {
        await act(() => api(`/api/mods/${state.mod}/card-voice`, { method: "POST", body: { card: c.slug, line: slot, file: p } }), `${c.card}: ${slot} line set`); refresh(); }));
      lines.append(cell);
    }
    cards.append(h("div", { style: "padding:8px 0;border-bottom:1px solid var(--line)" }, h("b", {}, c.card), " ",
      h("small", { class: "sub" }, c.voice_of ? `lines it doesn't set use ${c.voice_of}'s voice` : ""), lines));
  }
  if (!(d.card_voices || []).length) cards.append(h("p", { class: "sub" }, "This mod has no cards yet."));
  main.append(cards);
  // replaced sounds
  main.append(h("h2", {}, "Game sounds this mod replaces"));
  const reps = h("div", { class: "panel" });
  for (const s of d.sounds || []) reps.append(h("div", { class: "row", style: "align-items:center;gap:10px;padding:5px 0;border-bottom:1px solid var(--line)" },
    h("div", { style: "flex:1;min-width:0" }, h("b", {}, s.label), h("br"), h("small", { class: "sub" }, `${s.targets.length} take(s) · ${s.files.length} file(s), picked at random`)),
    s.audio_urls.map(u => h("button", { title: "Play yours", onclick: () => playUrl(u) }, "▶")),
    h("button", { class: "danger", onclick: async () => {
      await act(() => api(`/api/mods/${state.mod}/sounds?sound=${encodeURIComponent(s.sound)}`, { method: "DELETE" }), "Original sound restored"); refresh(); } }, "Restore original")));
  if (!(d.sounds || []).length) reps.append(h("p", { class: "sub" }, "None yet: find a sound below."));
  main.append(reps);
  // many sounds at once, matched by file name
  main.append(h("h2", {}, "Replace many sounds at once"));
  const manyOut = h("div", {});
  main.append(h("div", { class: "panel" },
    h("p", { class: "sub", style: "margin-top:0" }, "Drop several audio files. Each is matched to a game sound by its file name (\"Arena End.wav\", or the name of one of its original clips such as \"arena_end_resign.ogg\"), or to one of your cards' voice lines (\"Whiterun Wolfcaller Play.wav\", with Play, Attack, Death, Hit, Success or Failure). Files that match the same sound become its takes. Every file gets its own result line; one Ctrl+Z undoes the whole drop."),
    multiDrop("Drop audio files named after sounds", "audio/*", async files => {
      if (!Object.keys(files).length) return;
      const r = await act(() => api(`/api/mods/${state.mod}/bulk/sounds`, { method: "POST", body: { files } }), null);
      if (r) soundReport(manyOut, r, Object.keys(files)); }), manyOut));
  // search
  main.append(h("h2", {}, "Find a game sound"));
  const q = h("input", { placeholder: "e.g. fiery imp, taunt, sheogorath, click" });
  const cat = h("select", {}, h("option", { value: "" }, "All kinds"));
  const results = h("div", { class: "panel" });
  const run = async () => {
    const r = await api(`/api/sounds?q=${encodeURIComponent(q.value)}&category=${encodeURIComponent(cat.value)}&limit=60`);
    if (cat.options.length === 1) for (const c of r.categories) cat.append(h("option", { value: c.id }, c.label));
    results.innerHTML = "";
    results.append(h("p", { class: "sub" }, `${r.total} sounds${r.total > r.sounds.length ? ", showing " + r.sounds.length : ""}`));
    for (const s of r.sounds) {
      const box = h("div", { style: "display:none;margin-top:6px" });
      box.append(multiDrop("Drop your replacement (one or more files: several are picked at random)", "audio/*", async files => {
        const paths = Object.values(files);
        if (!paths.length) return;
        await act(() => api(`/api/mods/${state.mod}/sounds`, { method: "POST", body: { sound: s.id, files: paths } }), `${s.label} replaced (${paths.length} file${paths.length > 1 ? "s" : ""})`); refresh(); }));
      results.append(h("div", { style: "padding:6px 0;border-bottom:1px solid var(--line)" },
        h("div", { class: "row", style: "align-items:center;gap:10px" },
          h("div", { style: "flex:1;min-width:0" }, h("b", {}, s.label), h("br"), h("small", { class: "sub" }, `${s.category_label} · ${s.clips.length} take(s)` +
            (s.shares_with ? " · shares its name with " + s.shares_with.length + " other sound(s), which change too" : ""))),
          h("button", { title: "Play the original", onclick: () => playUrl(`/api/sounds/preview?path=${encodeURIComponent(s.preview)}`) }, "▶ Original"),
          h("button", { onclick: () => { box.style.display = box.style.display === "none" ? "block" : "none"; } }, "Replace...")), box));
    }
  };
  q.onkeydown = e => { if (e.key === "Enter") run(); };
  cat.onchange = run;
  main.append(h("div", { class: "toolbar" }, q, cat, h("button", { class: "primary", onclick: run }, "Search")), results);
  run();
};

function emoteDialog(a) {
  const rows = EMOTES.map(kind => {
    const line = (a.emotes || {})[kind] || {};
    const text = h("input", { value: line.text || "", placeholder: "(borrowed voice's line)" });
    let audio = null;
    let pending = null;
    const audioZone = dropZone(line.audio ? "voice ✓ (replace)" : "voice clip", "audio/*", (p, src) => { audio = p; pending = src; });
    const play = h("button", { title: "Play", onclick: () => {
      const src = pending || (line.audio ? `/mod-file/${encodeURIComponent(state.mod)}/avatars/${encodeURIComponent(line.audio)}` : null);
      if (!src) return toast("No voice clip for this emote yet.", true);
      new Audio(src).play().catch(e => toast("Can't play: " + e.message, true)); } }, "▶");
    return { kind, text, getAudio: () => audio, el: h("div", { class: "emote-row" }, h("b", {}, EMOTE_LABEL[kind]), text, h("div", { style: "display:flex;gap:6px;align-items:center" }, play, audioZone)) };
  });
  modal(h("div", {}, h("h1", {}, a.name), h("p", { class: "sub" }, "Own lines for each emote. Empty lines keep the borrowed voice. Voice clips: WAV, MP3 or OGG."),
    rows.map(r => r.el),
    h("div", { class: "toolbar" }, h("button", { class: "danger", onclick: async () => {
      if (!confirm(`Remove avatar ${a.name}?`)) return;
      await act(() => api(`/api/mods/${state.mod}/avatars/${a.slug}`, { method: "DELETE" }), "Avatar removed"); closeModal(); refresh(); } }, "Remove avatar"),
      h("span", { class: "grow" }), h("button", { onclick: closeModal }, "Close"),
      h("button", { class: "primary", onclick: async () => {
        for (const r of rows) {
          const before = ((a.emotes || {})[r.kind] || {}).text || "";
          if (r.text.value === before && !r.getAudio()) continue;
          await act(() => api(`/api/mods/${state.mod}/avatars/${a.slug}/emotes`, { method: "POST", body: { emote: r.kind, text: r.text.value, audio: r.getAudio() } }));
        }
        toast("Emotes saved"); closeModal(); refresh(); } }, "Save emotes"))));
}

VIEWS.cardbacks = async main => {
  const d = state.detail;
  main.append(h("h1", {}, "Card backs"), h("p", { class: "sub" }, "Selectable in Collection > card backs. Free ones are available to everyone with the mod; priced ones are sold for gold in the offline store (Special Offers)."));
  if (d.cardbacks.length) main.append(gamePreviewBar(d.cardbacks.some(c => c.preview) ? "Showing each card back as the game draws it on a card." : "Card backs show their image until you make game previews.", ["backs"]));
  const grid = h("div", { class: "grid" });
  for (const c of d.cardbacks) grid.append(h("div", { class: "tile back" + (c.preview ? " game-preview" : "") }, h("img", { src: c.preview || c.image_url, alt: c.name }),
    h("div", { class: "cap" }, h("b", {}, c.name), h("small", {}, c.price ? `${c.price} gold` : "free")),
    h("div", { class: "toolbar", style: "margin:0 10px 10px" },
      h("button", { onclick: () => editDialog("cardback", c.slug, "Edit " + c.name, [["name", "Name", "text", c.name], ["price", "Price in gold (0 = free)", "number", c.price || 0],
        ["image", "New image", "file", null, "image/*"]]) }, "Edit"),
      h("button", { class: "danger", onclick: async e => { e.stopPropagation();
        await act(() => api(`/api/mods/${state.mod}/cardbacks/${c.slug}`, { method: "DELETE" }), "Removed"); refresh(); } }, "Remove"))));
  if (!d.cardbacks.length) grid.append(h("p", { class: "sub" }, "No card backs yet."));
  main.append(grid, h("h2", {}, "New card back"));
  const name = h("input", { placeholder: "Card back name" }), price = h("input", { type: "number", min: 0, value: 0 }), unlock = h("input", { placeholder: "How to get it (optional)" });
  const size = h("select", {}, h("option", { value: 1024 }, "1024 (original)"), h("option", { value: 2048 }, "2048 (sharper)"));
  let img = null;
  const prev = h("div", {});
  main.append(h("div", { class: "split" }, h("div", { class: "panel" }, field("Name", name), h("div", { class: "row" }, field("Price in gold (0 = free)", price), field("Texture size", size)), field("Unlock text", unlock),
    h("div", { class: "field" }, h("label", {}, "Image (cropped to the card's shape, about 4:7)"), dropZone("Drop an image or click", "image/*", (p, s) => { img = p; prev.innerHTML = "";
      prev.append(h("div", { class: "c", style: `width:150px;height:264px;border-radius:10px;border:3px solid #a8884a;background:center/cover url(${s})` })); })),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!img) return toast("Choose an image first.", true);
      await act(() => api(`/api/mods/${state.mod}/cardbacks`, { method: "POST", body: { name: name.value, image: img, price: price.value, unlock: unlock.value, size: size.value } }), "Card back added");
      refresh(); } }, "Add card back"))), h("div", {}, h("label", {}, "Preview"), prev)));
};

// Problems found by the mod check, shown on the page of the item they are about (kept current: every change reloads them).
function issueRow(x) {
  return h("div", { class: "msg " + (x.severity === "error" ? "error" : "warn"), style: "display:flex;gap:10px;align-items:center" },
    h("span", { style: "flex:1;min-width:0;overflow-wrap:anywhere" }, x.text),
    x.view !== state.view && x.view !== "overview" ? h("button", { onclick: () => { state.focusItem = x.item; go(state.mod, x.view); } }, "Open") : null);
}
function pageIssues(main, view) {
  const list = ((state.detail || {}).validation || {}).issues || [];
  const mine = list.filter(x => x.view === view);
  if (!mine.length) return;
  const box = h("div", { class: "panel", style: "margin-bottom:12px" }, h("h3", { style: "margin-top:0" }, `${mine.length} problem${mine.length > 1 ? "s" : ""} on this page`), ...mine.map(issueRow));
  const h1 = main.querySelector("h1");
  if (h1 && h1.nextSibling) h1.parentNode.insertBefore(box, h1.nextSibling.nextSibling || null); else main.prepend(box);
  if (state.focusItem) {   // bring the item named in the problem into view
    const want = String(state.focusItem).toLowerCase();
    state.focusItem = null;
    const el = [...main.querySelectorAll(".tile, .row, .panel")].find(e => e !== box && !box.contains(e) && e.textContent.toLowerCase().includes(want));
    if (el) { el.scrollIntoView({ block: "center" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 2500); }
  }
}

// Details: version, what the mod needs or clashes with, load-order hints, changelog and preview (carried by exports).
function detailsPanel() {
  const box = h("div", {});
  const panel = h("details", { class: "panel", style: "margin:12px 0" }, h("summary", { style: "cursor:pointer;font-weight:600" }, "Details, version and requirements"), box);
  const draw = async () => {
    const d = await api(`/api/mods/${encodeURIComponent(state.mod)}/details`);
    const others = (state.mods || []).filter(m => m.id !== state.mod);
    box.innerHTML = "";
    const name = h("input", { value: d.name }), author = h("input", { value: d.author }), website = h("input", { value: d.website, placeholder: "https://… (optional)" });
    const desc = h("textarea", { rows: 3 }, d.description), version = h("input", { value: d.version, style: "width:110px" });
    const depRows = h("div", {});
    const addDep = (dep = { id: "", version: "*" }) => {
      const id = h("input", { value: dep.id, list: "forge-mod-ids", placeholder: "mod id" }), ver = h("input", { value: dep.version, style: "width:110px", placeholder: "* or >=1.2" });
      const row = h("div", { class: "row", style: "gap:6px;align-items:center;margin:4px 0" }, id, ver, h("button", { onclick: () => row.remove() }, "Remove"));
      row._get = () => ({ id: id.value.trim(), version: ver.value.trim() || "*" });
      depRows.append(row);
    };
    d.dependencies.forEach(addDep);
    const ids = v => h("input", { value: v.join(" "), placeholder: "mod ids, space separated", list: "forge-mod-ids" });
    const conflicts = ids(d.conflicts), after = ids(d.load_after), before = ids(d.load_before);
    const notes = h("textarea", { rows: 3, placeholder: "What changed in this release" });
    const part = h("select", {}, [["patch", "Fix (x.y.Z)"], ["minor", "Additions (x.Y.0)"], ["major", "Big change (X.0.0)"]].map(([v, t]) => h("option", { value: v }, t))); part.value = "minor";
    let previewPath = null;
    box.append(h("datalist", { id: "forge-mod-ids" }, others.map(m => h("option", { value: m.id }, m.name))),
      h("div", { class: "editor-2col" },
        h("div", {}, h("div", { class: "row" }, field("Name", name), field("Version", version)), field("Author", author), field("Description", desc), field("Website", website)),
        h("div", {}, h("div", { class: "field" }, h("label", {}, "Needs these mods (and versions)"), depRows, h("button", { onclick: () => addDep() }, "Add a needed mod")),
          field("Does not work with", conflicts), h("div", { class: "row" }, field("Load after", after), field("Load before", before)),
          field("Preview picture (shown with exported packages)", dropZone(d.preview_url ? "Replace the preview picture" : "Drop a preview picture", "image/*", p => { previewPath = p; })),
          d.preview_url ? h("img", { src: d.preview_url + "?t=" + Date.now(), style: "max-width:240px;border-radius:8px" }) : null)),
      h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
        const split = el => el.value.split(/[\s,]+/).filter(Boolean);
        await act(() => api(`/api/mods/${encodeURIComponent(state.mod)}/details`, { method: "POST", body: { name: name.value, author: author.value, description: desc.value,
          website: website.value, version: version.value, dependencies: [...depRows.children].map(r => r._get()).filter(x => x.id),
          conflicts: split(conflicts), load_after: split(after), load_before: split(before) } }), "Details saved");
        if (previewPath) await act(() => api(`/api/mods/${encodeURIComponent(state.mod)}/details/preview`, { method: "POST", body: { image: previewPath } }), "Preview saved");
        await loadMods(); draw(); } }, "Save details")),
      h("h3", {}, "Release"), h("div", { class: "row", style: "align-items:flex-end" }, field("Notes", notes), field("Version step", part),
        h("button", { onclick: async () => {
          const r = await act(() => api(`/api/mods/${encodeURIComponent(state.mod)}/details/release`, { method: "POST", body: { notes: notes.value, part: part.value } }), null);
          if (r) { toast(`Now version ${r.version}`); draw(); } } }, "Record release")),
      d.changelog.length ? h("div", {}, d.changelog.slice(0, 10).map(e => h("div", { style: "padding:4px 0;border-bottom:1px solid var(--line)" }, h("b", {}, e.version), h("small", { class: "sub" }, "  " + (e.date || "")), h("div", { style: "white-space:pre-wrap" }, e.notes))))
        : h("p", { class: "sub" }, "No releases recorded yet. Exports carry the changelog as CHANGELOG.md, plus README.md and the preview."));
  };
  panel.addEventListener("toggle", () => { if (panel.open && !box.firstChild) draw().catch(e => box.append(h("div", { class: "msg error" }, e.message))); });
  return panel;
}

// Play test: start the game with this mod and show what the game itself loaded (skipped mods, missing files ...).
function playtestPanel() {
  const out = h("div", {});
  const show = async () => {
    const r = await api(`/api/mods/${encodeURIComponent(state.mod)}/report`);
    out.innerHTML = "";
    if (!r.available) return out.append(h("p", { class: "sub" }, r.note));
    const age = r.age_seconds < 120 ? `${r.age_seconds} s` : r.age_seconds < 7200 ? `${Math.round(r.age_seconds / 60)} min` : `${Math.round(r.age_seconds / 3600)} h`;
    out.append(h("p", { class: "sub" }, `Last game start ${age} ago: `, r.loaded_this ? h("span", { class: "badge ok" }, "this mod loaded") : h("span", { class: "badge bad" }, "this mod was not loaded"),
      ` · ${(r.loaded || []).length} mods in load order${r.counts ? ` · ${Object.entries(r.counts).filter(([, n]) => n).map(([k, n]) => `${n} ${k}`).join(", ")}` : ""}${r.running ? " · the game is running" : ""}`));
    if (!r.problems.length) out.append(h("p", { class: "sub" }, "The game reported no problems with this mod."));
    for (const x of r.problems) out.append(h("div", { class: "msg warn" }, x));
  };
  const panel = h("div", { class: "panel", style: "margin:12px 0" }, h("div", { class: "row", style: "align-items:center;gap:10px" },
    h("h3", { style: "margin:0;flex:1" }, "Play test"),
    h("button", { onclick: show }, "Refresh report"),
    h("button", { class: "primary", onclick: async () => {
      const r = await act(() => api(`/api/mods/${encodeURIComponent(state.mod)}/playtest`, { method: "POST", body: { enable: true } }), null);
      if (!r) return;
      r.notes.forEach(n => toast(n));
      if (r.started) { let tries = 0; const t = setInterval(async () => {
        const rep = await api(`/api/mods/${encodeURIComponent(state.mod)}/report`).catch(() => null);
        if ((rep && rep.available && rep.age_seconds < 60 && !(tries === 0 && rep.age_seconds > 5)) || ++tries > 60) { clearInterval(t); show(); }
      }, 5000); }
    } }, "Play test in TESL: Everlasting")),
    h("p", { class: "sub", style: "margin:6px 0" }, "Enables this mod and starts the game offline. The game then reports what it loaded; anything it skipped shows here with the reason."), out);
  show().catch(() => {});
  return panel;
}

// Many files at once: uploads each, then calls onDone({file name: uploaded path}).
function multiDrop(text, accept, onDone) {
  const input = h("input", { type: "file", accept, multiple: true, class: "hidden" });
  const zone = h("div", { class: "drop" }, h("div", {}, text));
  const take = async list => {
    const fileList = [...list];
    if (!fileList.length) return;
    zone.innerHTML = "";
    const status = h("div", {}, h("span", { class: "spinner" }), ` Uploading ${fileList.length} files…`);
    zone.append(status);
    const files = {};
    for (const [i, f] of fileList.entries()) {
      try { files[f.name] = await upload(f); status.lastChild.textContent = ` Uploaded ${i + 1} of ${fileList.length}`; }
      catch (e) { toast(`${f.name}: ${e.message}`, true); }
    }
    status.textContent = `${Object.keys(files).length} files ready`;
    onDone(files, fileList);
  };
  zone.onclick = () => input.click();
  zone.tabIndex = 0; zone.setAttribute("role", "button"); zone.setAttribute("aria-label", text);
  zone.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  input.onchange = () => take(input.files);
  zone.ondragover = e => { e.preventDefault(); zone.classList.add("over"); };
  zone.ondragleave = () => zone.classList.remove("over");
  zone.ondrop = e => { e.preventDefault(); zone.classList.remove("over"); take(e.dataTransfer.files); };
  return h("div", {}, zone, input);
}

function bulkReport(box, r) {
  box.innerHTML = "";
  box.append(h("div", { class: "msg " + (r.failed.length ? "warn" : "ok") }, `${r.imported} imported${r.failed.length ? `, ${r.failed.length} could not be` : ""}. One Ctrl+Z undoes the whole import.`),
    ...r.failed.map(f => h("div", { class: "msg error" }, `${f.row ? "Row " + f.row + ": " : ""}${f.card || f.file || ""} – ${f.error}`)));
}

VIEWS.bulk = async main => {
  const d = state.detail;
  main.append(h("h1", {}, "Bulk import"), h("p", { class: "sub" }, "Bring in many items at once. Rows or files that have a problem are listed; the rest still import, and one Ctrl+Z undoes the whole import."));
  // Cards from a spreadsheet
  const cardsOut = h("div", {});
  let csvFile = null, artFiles = {};
  main.append(h("div", { class: "panel" }, h("h3", { style: "margin-top:0" }, "Cards from a spreadsheet"),
    h("p", { class: "sub" }, "A CSV with one card per row. Columns: name, template (an original card whose rules it copies), cost, power, health, rarity, text, art (a picture file name), unique. Cards that already exist in this mod are updated. ",
      h("a", { href: "/api/bulk-template.csv", download: "cards-template.csv" }, "Download a template")),
    h("div", { class: "split" }, dropZone("Drop the CSV", ".csv,text/csv", (p, u, f) => { csvFile = f; }),
      multiDrop("Drop the art pictures (optional)", "image/*", files => { artFiles = files; })),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!csvFile) return toast("Drop a CSV first.", true);
      const text = await csvFile.text();
      const r = await act(() => api(`/api/mods/${state.mod}/bulk/cards`, { method: "POST", body: { text, files: artFiles } }), null);
      if (r) bulkReport(cardsOut, r); } }, "Import cards")), cardsOut));
  // Art by file name
  const artOut = h("div", {});
  main.append(h("div", { class: "panel", style: "margin-top:12px" }, h("h3", { style: "margin-top:0" }, "Card art by file name"),
    h("p", { class: "sub" }, "Name each picture after its card (\"Whiterun Wolfcaller.png\"). This mod's cards get it as their art; original cards get a remastered replacement."),
    multiDrop("Drop pictures named after cards", "image/*", async files => {
      const r = await act(() => api(`/api/mods/${state.mod}/bulk/art`, { method: "POST", body: { files } }), null);
      if (r) bulkReport(artOut, r); }), artOut));
  // Music
  const musicOut = h("div", {});
  const ctx = new Set();
  const ctxBox = h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:4px;max-height:200px;overflow:auto" },
    (d.music_contexts || []).map(c => { const cb = h("input", { type: "checkbox" }); cb.onchange = () => cb.checked ? ctx.add(c.context) : ctx.delete(c.context);
      return h("label", { style: "display:flex;gap:6px;align-items:center;color:var(--text)" }, cb, c.label); }));
  const mode = h("select", {}, h("option", { value: "rotation" }, "Join the game's music"), h("option", { value: "replace" }, "Replace the game's music"));
  main.append(h("div", { class: "panel", style: "margin-top:12px" }, h("h3", { style: "margin-top:0" }, "Soundtrack tracks"),
    field("Plays at", ctxBox), field("Mode", mode),
    multiDrop("Drop audio files (OGG, WAV, MP3, FLAC)", "audio/*", async files => {
      if (!ctx.size) return toast("Choose where the tracks play first.", true);
      const r = await act(() => api(`/api/mods/${state.mod}/bulk/music`, { method: "POST", body: { files, contexts: [...ctx], mode: mode.value } }), null);
      if (r) bulkReport(musicOut, r); }), musicOut));
};

VIEWS.settings = async main => {
  const st = await api("/api/settings");
  main.append(h("h1", {}, "Settings"), h("p", { class: "sub" }, "Settings of this computer, kept in the Forge folder (workspace/settings.json) and never shared with a mod. Leave a path empty and TESL Forge finds the program by itself."));
  const dirs = h("textarea", { rows: 3, placeholder: "One folder per line" }, (st.game_dirs || []).join("\n"));
  const steam = h("textarea", { rows: 2, placeholder: "One folder per line (optional)" }, (st.steam_dirs || []).join("\n"));
  const blender = h("input", { value: st.blender || "", placeholder: st.blender_found ? "found: " + st.blender_found : "not found: only needed for FBX, .blend, DAE, 3DS, STL, PLY and USD models" });
  const ffmpeg = h("input", { value: st.ffmpeg || "", placeholder: st.ffmpeg_found ? "found: " + st.ffmpeg_found : "not found: needed to convert MP3, FLAC and M4A" });
  const lines = t => t.value.split("\n").map(x => x.trim()).filter(Boolean);
  main.append(h("div", { class: "panel" },
    field("Extra game folders", dirs, "More installs of The Elder Scrolls Legends (a second copy, a Bethesda.net install). The one next to TESL Forge and your Steam libraries are found automatically."),
    field("Extra Steam folders", steam, "Only if Steam keeps your games somewhere TESL Forge does not look."),
    field("Blender (blender.exe)", blender), field("ffmpeg", ffmpeg),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      const r = await act(() => api("/api/settings", { method: "POST", body: { game_dirs: lines(dirs), steam_dirs: lines(steam), blender: blender.value.trim(), ffmpeg: ffmpeg.value.trim() } }), "Settings saved");
      if (r) route(); } }, "Save"))));
};

VIEWS.translations = async main => {
  const info = await api(`/api/mods/${state.mod}/translations`);
  main.append(h("h1", {}, "Translations"), h("p", { class: "sub" }, `Write this mod's text in English; add a language to translate it. The game shows the translation when it runs in that language, and English for anything not translated yet. Keep formatting tags such as <b>…</b> and <color=…> as they are. ${info.total} texts in this mod.`));
  const pick = h("select", {}, info.known.map(l => h("option", { value: l.language }, l.label + " (" + l.language + ")")));
  if (state.trLang) pick.value = state.trLang;
  const list = h("div", { class: "row", style: "gap:8px;flex-wrap:wrap;margin:8px 0" }, info.languages.map(l =>
    h("button", { onclick: () => { state.trLang = l.language; pick.value = l.language; draw(); } }, `${l.label}: ${l.done}/${l.total}`)));
  const area = h("div", {});
  const draw = async () => {
    state.trLang = pick.value;
    const t = await api(`/api/mods/${state.mod}/translations/${pick.value}`);
    area.innerHTML = "";
    const inputs = t.rows.map(r => { const el = h("textarea", { rows: r.english.length > 80 ? 3 : 1, style: "width:100%" }, r.translation); el._en = r.english; el._old = r.translation; return el; });
    const done = () => inputs.filter(i => i.value.trim()).length;
    const counter = h("span", { class: "sub" }, `${done()} of ${inputs.length} translated`);
    inputs.forEach(i => i.oninput = () => counter.textContent = `${done()} of ${inputs.length} translated`);
    let csvText = null;
    area.append(h("div", { class: "toolbar" }, counter, h("span", { class: "grow" }),
        h("a", { class: "button", href: `/api/mods/${encodeURIComponent(state.mod)}/translations/${pick.value}.csv`, download: `${state.mod}-${pick.value}.csv`, style: "padding:6px 10px;border:1px solid var(--line);border-radius:8px" }, "Export CSV"),
        dropZone("Import a translated CSV", ".csv,text/csv", async (p, u, f) => {
          const text = await f.text();
          const r = await act(() => api(`/api/mods/${state.mod}/translations/${pick.value}/csv`, { method: "POST", body: { text } }), null);
          if (r) { toast(`${r.imported} rows imported`); draw(); } }),
        h("button", { class: "primary", onclick: async () => {
          const values = Object.fromEntries(inputs.filter(i => i.value !== i._old).map(i => [i._en, i.value]));
          if (!Object.keys(values).length) return toast("Nothing changed.");
          await act(() => api(`/api/mods/${state.mod}/translations/${pick.value}`, { method: "POST", body: { values } }), "Translations saved");
          draw(); } }, "Save")),
      h("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;align-items:start" },
        h("b", {}, "English"), h("b", {}, (info.known.find(l => l.language === pick.value) || {}).label || pick.value),
        ...t.rows.flatMap((r, i) => [h("div", { style: "white-space:pre-wrap;padding-top:4px" }, r.english), inputs[i]])),
      t.unused.length ? h("p", { class: "sub" }, `${t.unused.length} saved translations are for text the mod no longer has; they are kept but unused.`) : null);
  };
  pick.onchange = draw;
  main.append(h("div", { class: "panel" }, field("Language", pick), list, area));
  draw();
};

VIEWS.packs = async main => {
  const d = state.detail;
  const opt = await api(`/api/mods/${state.mod}/pack-options`);
  main.append(h("h1", {}, "Card packs"), h("p", { class: "sub" }, "Packs sold for gold in TESL: Everlasting's offline store and opened with the game's own pack screen. Each pack has its own drop table: rarity chances per slot from this mod's cards, all cards or chosen card sets, or a hand-picked list of cards with weights."));
  const grid = h("div", { class: "grid" }), form = h("div", {});
  for (const p of d.packs || []) grid.append(h("div", { class: "tile back" }, p.image_url ? h("img", { src: p.image_url }) : h("div", { class: "c", style: "height:200px" }),
    h("div", { class: "cap" }, h("b", {}, p.name), h("small", {}, `${p.price} gold · ${p.cards} cards · ${p.cards_list ? "hand-picked cards" : Array.isArray(p.pool) ? p.pool.map(s => (opt.sets.find(x => x.set === s) || {}).label || s).join(", ") : p.pool === "all" ? "all cards" : "this mod's cards"}`)),
    h("div", { class: "toolbar", style: "margin:0 10px 10px" }, h("button", { onclick: () => packForm(form, opt, p) }, "Edit"),
      h("button", { class: "danger", onclick: async () => { if (!confirm(`Remove ${p.name}?`)) return; await act(() => api(`/api/mods/${state.mod}/packs/${p.slug}`, { method: "DELETE" }), "Removed"); refresh(); } }, "Remove"))));
  if (!(d.packs || []).length) grid.append(h("p", { class: "sub" }, "No packs yet."));
  main.append(grid, form);
  packForm(form, opt, null);
};

function packForm(form, opt, p) {
  form.innerHTML = "";
  p = p || {};
  const name = h("input", { value: p.name || "", placeholder: "Pack name" }), desc = h("input", { value: p.description || "", placeholder: "Store text" });
  const price = h("input", { type: "number", min: 0, value: p.price ?? 100, style: "width:100px" }), count = h("input", { type: "number", min: 1, max: 12, value: p.cards ?? 6, style: "width:80px" });
  const premium = h("input", { type: "number", min: 0, max: 100, step: 0.5, value: p.premium ?? 5, style: "width:80px" });
  const how = h("select", {}, h("option", { value: "slots" }, "Rarity slots from a pool of cards"), h("option", { value: "list" }, "Hand-picked cards with weights"));
  how.value = p.cards_list ? "list" : "slots";
  const pool = h("select", {}, h("option", { value: "mod" }, "This mod's cards"), h("option", { value: "all" }, "Every collectible card"), h("option", { value: "sets" }, "Chosen card sets"));
  pool.value = Array.isArray(p.pool) ? "sets" : p.pool || "mod";
  const chosen = new Set(Array.isArray(p.pool) ? p.pool : []);
  const sets = h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:4px" }, opt.sets.map(s => {
    const cb = h("input", { type: "checkbox" }); cb.checked = chosen.has(s.set); cb.onchange = () => cb.checked ? chosen.add(s.set) : chosen.delete(s.set);
    return h("label", { style: "display:flex;gap:6px;align-items:center;color:var(--text)" }, cb, s.label); }));
  const oddsRow = (vals, title) => {
    const ins = Object.fromEntries(opt.rarities.map(r => [r, h("input", { type: "number", min: 0, step: 0.5, value: (vals || {})[r] ?? 0, style: "width:80px" })]));
    const el = h("div", { class: "field" }, h("label", {}, title), h("div", { class: "row", style: "gap:8px" }, opt.rarities.map(r => h("label", { style: "display:flex;flex-direction:column;font-size:.85rem" }, r[0].toUpperCase() + r.slice(1), ins[r]))));
    el._get = () => Object.fromEntries(opt.rarities.map(r => [r, +ins[r].value || 0]));
    return el;
  };
  const odds = oddsRow(p.odds || opt.odds, "Chances for each card (any numbers; they are compared with each other)"), last = oddsRow(p.last_slot || opt.last_slot, "Chances for the last card (the guaranteed slot)");
  const dl = "pack-cards-" + Math.random().toString(36).slice(2);
  const list = h("textarea", { rows: 6, placeholder: "One card per line: Name, or Name = weight\nWhiterun Wolfcaller = 6\nJarl's Housecarl = 1" },
    (p.cards_list || []).map(c => `${c.card}${c.weight && c.weight !== 1 ? " = " + c.weight : ""}`).join("\n"));
  let img = null;
  const prev = h("div", {}, p.image_url ? h("img", { src: p.image_url, style: "max-height:200px;border-radius:8px" }) : null);
  const slotsBox = h("div", {}, field("Pool", pool), sets, odds, last), listBox = h("div", {}, field("Cards and weights", list), h("datalist", { id: dl }, (opt.cards || []).slice(0, 5000).map(n => h("option", { value: n }))));
  const sync = () => { slotsBox.style.display = how.value === "slots" ? "" : "none"; listBox.style.display = how.value === "list" ? "" : "none"; sets.style.display = pool.value === "sets" ? "" : "none"; };
  how.onchange = pool.onchange = sync; sync();
  form.append(h("div", { class: "panel", style: "margin-top:12px" }, h("h3", {}, p.slug ? "Edit " + p.name : "New pack"),
    h("div", { class: "editor-2col" },
      h("div", {}, h("div", { class: "row" }, field("Name", name), field("Price (gold)", price), field("Cards per pack", count)), field("Store text", desc),
        field("Drop table", how), slotsBox, listBox, field("Premium chance (%)", premium)),
      h("div", {}, h("label", {}, "Store art (cropped to the pack shape)"), dropZone("Drop a picture or click", "image/*", (path, s) => { img = path; prev.innerHTML = ""; prev.append(h("img", { src: s, style: "max-height:200px;border-radius:8px" })); }), prev)),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), p.slug ? h("button", { onclick: () => packForm(form, opt, null) }, "Cancel") : null,
      h("button", { class: "primary", onclick: async () => {
        if (!name.value.trim()) return toast("Name the pack.", true);
        const fields = { name: name.value.trim(), description: desc.value, price: +price.value || 0, cards: +count.value || 6, premium: +premium.value || 0 };
        if (p.slug) fields.slug = p.slug;
        if (how.value === "list") fields.cards_list = list.value.split("\n").map(l => l.trim()).filter(Boolean).map(l => { const m = l.split("="); return { card: m[0].trim(), weight: m[1] ? +m[1] : 1 }; });
        else { fields.cards_list = []; fields.pool = pool.value === "sets" ? [...chosen] : pool.value; fields.odds = odds._get(); fields.last_slot = last._get(); }
        await act(() => api(`/api/mods/${state.mod}/packs`, { method: "POST", body: { fields, image: img } }), p.slug ? "Pack saved" : "Pack added");
        refresh(); } }, p.slug ? "Save changes" : "Add pack"))));
}

VIEWS.opponents = async main => {
  const d = state.detail;
  const opt = await api(`/api/mods/${state.mod}/opponent-options`);
  main.append(h("h1", {}, "AI opponents"), h("p", { class: "sub" }, "In-game AI characters for TESL: Everlasting (offline, against the game's AI only). Each has a portrait, a deck, a difficulty and an emote personality. "
    + "Players pick one in the game's F10 menu (Practice opponent), or allow mod opponents to turn up in random Practice. Game modes and story battles can name one as their AI opponent."));
  const grid = h("div", { class: "grid" });
  const form = h("div", {});
  for (const o of d.opponents || []) grid.append(h("div", { class: "tile" }, o.image_url ? h("img", { src: o.image_url }) : h("div", { class: "c", style: "height:200px" }),
    h("div", { class: "cap" }, h("b", {}, o.name), h("small", {}, `${o.title || ""}${o.title ? " · " : ""}${o.difficulty === "chosen" ? "player's difficulty" : o.difficulty} · ${o.temperament || "auto personality"}${o.practice === false ? " · named only" : ""}`)),
    h("div", { class: "toolbar", style: "margin:0 10px 10px" },
      h("button", { onclick: () => opponentForm(form, opt, o) }, "Edit"),
      h("button", { class: "danger", onclick: async () => { if (!confirm(`Remove ${o.name}?`)) return;
        await act(() => api(`/api/mods/${state.mod}/opponents/${o.slug}`, { method: "DELETE" }), "Removed"); refresh(); } }, "Remove"))));
  if (!(d.opponents || []).length) grid.append(h("p", { class: "sub" }, "No AI opponents yet."));
  main.append(grid, form);
  opponentForm(form, opt, null);
};

function opponentForm(form, opt, o) {
  form.innerHTML = "";
  o = o || {};
  const name = h("input", { value: o.name || "", placeholder: "Name, e.g. Greybeard Elder" }), title = h("input", { value: o.title || "", placeholder: "Title line (optional)" });
  const deck = h("select", {}, opt.decks.map(x => h("option", { value: x.deck }, x.label)));
  if (o.deck && !opt.decks.some(x => x.deck === o.deck)) deck.append(h("option", { value: o.deck }, o.deck));
  deck.value = o.deck || "practice";
  const size = h("input", { type: "number", min: 10, max: 100, value: o.random_size || 30, style: "width:90px" });
  const diff = h("select", {}, opt.difficulties.map(v => h("option", { value: v }, v === "chosen" ? "What the player picks" : v))); diff.value = o.difficulty || "chosen";
  const temper = h("select", {}, opt.temperaments.map(v => h("option", { value: v }, v || "Decided by the name"))); temper.value = o.temperament || "";
  const practice = h("input", { type: "checkbox" }); practice.checked = o.practice !== false;
  const source = h("select", {}, h("option", { value: "image" }, "A picture (cropped square around the head)"), opt.avatars.map(a => h("option", { value: "avatar:" + a.slug }, "Avatar: " + a.name)));
  const cur = o.portrait || "";
  source.value = cur.startsWith("avatar:") ? cur : "image";
  let img = null;
  const prev = h("div", {}, o.image_url ? h("img", { src: o.image_url, style: "max-height:220px;border-radius:8px" }) : null);
  const drop = dropZone("Drop a portrait picture or click", "image/*", (p, s) => { img = p; prev.innerHTML = ""; prev.append(h("img", { src: s, style: "max-height:220px;border-radius:8px" })); });
  const syncSource = () => { drop.style.display = source.value === "image" ? "" : "none"; };
  source.onchange = syncSource; syncSource();
  form.append(h("div", { class: "panel", style: "margin-top:12px" }, h("h3", {}, o.slug ? "Edit " + o.name : "New AI opponent"),
    h("div", { class: "editor-2col" },
      h("div", {}, h("div", { class: "row" }, field("Name", name), field("Title", title)),
        h("div", { class: "row" }, field("Deck", deck), field("Random deck size", size)),
        h("div", { class: "row" }, field("Difficulty", diff), field("Personality (emotes)", temper)),
        h("label", { style: "display:flex;gap:6px;align-items:center;margin:8px 0" }, practice, "Can turn up in random Practice (otherwise only where a mode or story names it)")),
      h("div", {}, field("Portrait", source), drop, prev)),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), o.slug ? h("button", { onclick: () => opponentForm(form, opt, null) }, "Cancel") : null,
      h("button", { class: "primary", onclick: async () => {
        if (!name.value.trim()) return toast("Name the opponent.", true);
        const fields = { name: name.value.trim(), title: title.value, deck: deck.value, random_size: +size.value || 30, difficulty: diff.value, temperament: temper.value, practice: practice.checked };
        if (o.slug) fields.slug = o.slug;
        if (source.value !== "image") fields.portrait = source.value;
        else if (!img && !(cur && !cur.includes(":"))) return toast("Choose a portrait picture or one of your avatars.", true);
        await act(() => api(`/api/mods/${state.mod}/opponents`, { method: "POST", body: { fields, image: source.value === "image" ? img : null } }), o.slug ? "Opponent saved" : "Opponent added");
        refresh(); } }, o.slug ? "Save changes" : "Add opponent"))));
}

VIEWS.boards = async main => {
  const d = state.detail;
  if (state.boardEdit && d.boards.find(b => b.slug === state.boardEdit)) return boardEditor(main, d, d.boards.find(b => b.slug === state.boardEdit));
  state.boardEdit = null;
  main.append(h("h1", {}, "Boards"), h("p", { class: "sub" }, "A board sits on one of the game's five boards. Give it a new table painting, and/or edit everything on it: hide, move, resize, recolour or retexture the props, change lights, effects and animations, and add your own 3D models, images, lights and particle effects. \"Rotation\" adds it to the random board choice; \"Replace\" always shows it instead of that base. Players can force a board in the offline game's F10 menu."));
  if (d.boards.length) main.append(gamePreviewBar(d.boards.some(b => b.preview) ? "Showing each board as the game draws it (an empty board, as a player sees it)." : "Boards show their table image until you make game previews.", ["boards"]));
  const grid = h("div", { class: "grid wide" });
  for (const b of d.boards) {
    const ed = b.edits || {};
    const count = Object.keys(ed.objects || {}).length + Object.keys(ed.textures || {}).length + Object.keys(ed.lights || {}).length
      + Object.keys(ed.particles || {}).length + Object.keys(ed.animators || {}).length + (ed.add || []).length + (ed.lighting ? 1 : 0);
    grid.append(h("div", { class: "tile" },
      b.preview ? h("img", { src: b.preview, style: "aspect-ratio:16/9;object-fit:cover", alt: b.name + " (game preview)" })
        : b.image_url ? h("img", { src: b.image_url, style: "aspect-ratio:2/1" }) : h("img", { src: `/api/board-maps/${b.base}/picture`, style: "aspect-ratio:16/9;object-fit:cover" }),
      h("div", { class: "cap" }, h("b", {}, b.name), h("small", { style: "display:block" }, `${b.base.replace(/([a-z])([A-Z])/g, "$1 $2")} · ${b.mode} · ${b.image_url ? "new table" : "original table"} · ${count} edit(s)`)),
      h("div", { class: "toolbar", style: "margin:0 10px 10px" }, h("button", { class: "primary", onclick: () => { state.boardEdit = b.slug; refresh(); } }, "Edit board"),
        h("button", { onclick: () => editDialog("board", b.slug, "Board settings: " + b.name, [["name", "Name", "text", b.name],
          ["base", "Base board", "select", b.base, (d.board_bases || []).map(x => [x, x.replace(/([a-z])([A-Z])/g, "$1 $2")])],
          ["mode", "Shown", "select", b.mode, [["rotation", "In rotation with the game's boards"], ["replace", "Instead of its base board"]]],
          ["image", "New table image", "file", null, "image/*"]]) }, "Settings"),
        h("button", { class: "danger", onclick: async () => {
          if (!confirm(`Remove board ${b.name} and everything added to it?`)) return;
          await act(() => api(`/api/mods/${state.mod}/boards/${b.slug}`, { method: "DELETE" }), "Board removed"); refresh(); } }, "Remove"))));
  }
  if (!d.boards.length) grid.append(h("p", { class: "sub" }, "No boards yet."));
  main.append(grid, h("h2", {}, "New board"));
  const name = h("input", { placeholder: "Board name" });
  const base = h("select", {}, d.board_bases.map(x => h("option", { value: x }, x.replace(/([a-z])([A-Z])/g, "$1 $2"))));
  const mode = h("select", {}, h("option", { value: "rotation" }, "Rotation (random choice)"), h("option", { value: "replace" }, "Replace the base board"));
  const size = h("select", {}, h("option", { value: 2048 }, "2048 × 1024 (original)"), h("option", { value: 4096 }, "4096 × 2048 (sharper)"));
  let img = null;
  const prev = h("div", {});
  main.append(h("div", { class: "split" }, h("div", { class: "panel" }, field("Name", name), h("div", { class: "row" }, field("Base board", base), field("Mode", mode), field("Size", size)),
    h("div", { class: "field" }, h("label", {}, "Table painting (optional: wide, cropped to 2:1; leave empty to keep the base's table)"),
      dropZone("Drop an image or click", "image/*", (p, s) => { img = p; prev.innerHTML = ""; prev.append(h("div", { class: "c", style: `width:100%;aspect-ratio:2/1;border-radius:8px;border:1px solid var(--line);background:center/cover url(${s})` })); })),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!name.value) return toast("Name the board first.", true);
      const r = await act(() => api(`/api/mods/${state.mod}/boards`, { method: "POST", body: { name: name.value, image: img, base: base.value, mode: mode.value, size: size.value } }), "Board added");
      if (r) state.boardEdit = r.board.slug;
      refresh(); } }, "Add board"))), h("div", {}, h("label", {}, "Preview"), prev)));
};

// ---- the board editor ---------------------------------------------------------------------------------------------------
const MARK = { object: "#e3b04b", light: "#fff27a", effect: "#5fd3e8", added: "#ff5fd2", hidden: "#888" };
function projectSpot(cam, w) {
  const m = cam.viewProjection, v = [w[0], w[1], w[2], 1];
  const c = [0, 1, 2, 3].map(r => m[r * 4] * v[0] + m[r * 4 + 1] * v[1] + m[r * 4 + 2] * v[2] + m[r * 4 + 3] * v[3]);
  if (c[3] <= 0) return null;
  return [(c[0] / c[3] + 1) / 2, 1 - (c[1] / c[3] + 1) / 2];
}
const hex = c => c ? "#" + c.slice(0, 3).map(x => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, "0")).join("") : "#ffffff";

async function boardEditor(main, d, b) {
  const map = await api(`/api/board-maps/${b.base}`);
  const ed = b.edits || {};
  const edit = async (kind, body, ok) => { const r = await act(() => api(`/api/mods/${state.mod}/board-edit`, { method: "POST", body: { ...body, action: kind, board: b.slug } }), ok || "Saved"); await refresh(); return r; };
  let pending = null;                       // {label, run(x, y)}: the next click on the picture
  const hint = h("div", { class: "sub", style: "min-height:1.4em" }, "Click a marker to edit it, or pick a tool to add something.");
  const setPending = p => { pending = p; hint.textContent = p ? `Click the board where it should go: ${p.label}  (Esc cancels)` : "Click a marker to edit it, or pick a tool to add something."; pic.style.cursor = p ? "crosshair" : "default"; };
  document.onkeydown = e => { if (e.key === "Escape") setPending(null); };
  const inspector = h("div", { class: "panel", style: "min-height:240px" }, h("p", { class: "sub" }, "Nothing selected."));

  // picture with markers
  const pic = h("div", { style: "position:relative;width:100%;border-radius:8px;overflow:hidden;border:1px solid var(--line);background:#111;aspect-ratio:16/9" });
  pic.append(map.picture ? h("img", { src: `/api/board-maps/${b.base}/picture`, style: "width:100%;height:100%;object-fit:cover;display:block" })
    : h("div", { class: "sub", style: "padding:40px;text-align:center" }, "No picture of this board on this computer yet (the offline engine's boardmap diagnostic makes them). Markers still work."));
  if (b.image_url) pic.append(h("div", { class: "sub", style: "position:absolute;left:8px;top:8px;background:#000a;padding:2px 8px;border-radius:6px;font-size:0.857rem" }, "Picture shows the base board; your table painting replaces its centre."));
  pic.onclick = e => {
    if (!pending || e.target.dataset.marker) return;
    const r = pic.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    const p = pending; setPending(null); p.run(+x.toFixed(4), +y.toFixed(4));
  };
  const marker = (spot, color, title, onclick, crossed) => {
    if (!spot || spot[0] < -0.02 || spot[0] > 1.02 || spot[1] < -0.02 || spot[1] > 1.02) return;
    const m = h("div", { title, "data-marker": "1", style: `position:absolute;left:${spot[0] * 100}%;top:${spot[1] * 100}%;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;` +
      `border:3px solid ${color};background:${crossed ? "#0008" : color + "44"};cursor:pointer;box-shadow:0 0 4px #000` });
    m.onclick = e => { e.stopPropagation(); onclick(); };
    pic.append(m);
  };
  const objEdit = path => (ed.objects || {})[path] || {};
  for (const o of map.objects.filter(o => o.depth === 1 && !map.lights.some(l => l.path === o.path)))
    marker(o.spot, objEdit(o.path).hide ? MARK.hidden : MARK.object, o.label + (objEdit(o.path).hide ? " (hidden)" : ""), () => showObject(o), objEdit(o.path).hide);
  for (const l of map.lights) if (l.light.type !== "Directional") marker(l.spot, MARK.light, "Light: " + l.label, () => showLight(l));
  const fxSeen = new Set();
  for (const f of map.effects) { const k = f.path; if (fxSeen.has(k)) continue; fxSeen.add(k); marker(f.spot, MARK.effect, "Effect: " + f.label, () => showEffect(f)); }
  for (const a of ed.add || []) marker(projectSpot(map.camera, a.pos), MARK.added, "Added: " + a.name, () => showAdded(a));

  // inspectors
  const show = (...kids) => { inspector.innerHTML = ""; inspector.append(...kids); };
  const range = (min, max, step, value, onchange) => { const r = h("input", { type: "range", min, max, step, value }); r.onchange = () => onchange(+r.value); return r; };
  const colour = (value, onchange) => { const c = h("input", { type: "color", value: hex(value) }); c.onchange = () => onchange(c.value); return c; };
  function showObject(o) {
    state.boardSel = { board: b.slug, k: "object", key: o.path };
    const e = objEdit(o.path);
    const anim = map.animations.find(a => a.path === o.path);
    const scale0 = o.scale[0] || 1, k = e.scale ? +(e.scale[0] / scale0).toFixed(2) : 1, turn = e.rot ? Math.round(e.rot[1] - o.rot[1]) : 0;
    const hide = h("input", { type: "checkbox" }); hide.checked = !!e.hide;
    hide.onchange = () => edit("object", { path: o.path, hide: hide.checked }, hide.checked ? "Hidden" : "Shown");
    show(h("h3", {}, o.label), h("small", { class: "sub", style: "word-break:break-all" }, o.path),
      h("label", { style: "display:flex;gap:6px;align-items:center;margin:10px 0" }, hide, "Hidden"),
      h("div", { class: "toolbar" }, h("button", { onclick: () => setPending({ label: "move " + o.label, run: (x, y) => edit("object", { path: o.path, x, y }, "Moved") }) }, "Move to a spot..."),
        e.offset || e.pos ? h("button", { onclick: () => edit("object", { path: o.path, offset: [0, 0, 0], pos: o.pos }, "Back in place") }, "Back in place") : null),
      field(`Size (× ${k})`, range(0.2, 3, 0.05, k, v => edit("object", { path: o.path, scale: o.scale.map(s => +(s * v).toFixed(4)) }, "Resized"))),
      field(`Turn (${turn}°)`, range(-180, 180, 5, turn, v => edit("object", { path: o.path, rot: [o.rot[0], +(o.rot[1] + v).toFixed(2), o.rot[2]] }, "Turned"))),
      h("div", { class: "row" }, field("Tint", colour(e.tint, v => edit("object", { path: o.path, tint: v }, "Tinted"))), field("Glow", colour(e.glow || [0, 0, 0], v => edit("object", { path: o.path, glow: v }, "Glow set")))),
      o.textures && o.textures.length ? h("div", { class: "field" }, h("label", {}, "New colour texture (this object only)"),
        dropZone("Drop an image or click", "image/*", p => edit("object", { path: o.path, image: p }, "Texture replaced"))) : null,
      anim ? h("div", {}, h("h4", {}, "Animation"), field(`Speed (× ${((ed.animators || {})[o.path] || {}).speed ?? 1})`, range(0, 3, 0.1, ((ed.animators || {})[o.path] || {}).speed ?? 1,
        v => edit("animation", { path: o.path, speed: v }, "Animation speed set")))) : null,
      h("div", { class: "toolbar", style: "margin-top:12px" }, h("span", { class: "grow" }),
        h("button", { class: "danger", onclick: () => edit("object", { path: o.path, reset: true }, "Object restored") }, "Restore original")));
  }
  function showLight(l) {
    state.boardSel = { board: b.slug, k: "light", key: l.path };
    const e = (ed.lights || {})[l.path] || {};
    const on = h("input", { type: "checkbox" }); on.checked = e.enabled ?? l.light.enabled;
    on.onchange = () => edit("light", { path: l.path, enabled: on.checked }, on.checked ? "Light on" : "Light off");
    show(h("h3", {}, "Light: " + l.label), h("label", { style: "display:flex;gap:6px;align-items:center;margin:10px 0" }, on, "On"),
      field("Colour", colour(e.color || l.light.color, v => edit("light", { path: l.path, color: v }, "Colour set"))),
      field(`Brightness (${e.intensity ?? l.light.intensity})`, range(0, Math.max(3, l.light.intensity * 3), 0.05, e.intensity ?? l.light.intensity, v => edit("light", { path: l.path, intensity: v }, "Brightness set"))),
      field(`Reach (${e.range ?? l.light.range})`, range(1, Math.max(60, l.light.range * 3), 1, e.range ?? l.light.range, v => edit("light", { path: l.path, range: v }, "Reach set"))),
      h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "danger", onclick: () => edit("light", { path: l.path, reset: true }, "Light restored") }, "Restore original")));
  }
  function showEffect(f) {
    state.boardSel = { board: b.slug, k: "effect", key: f.path };
    const e = (ed.particles || {})[f.path] || {};
    const on = h("input", { type: "checkbox" }); on.checked = e.enabled ?? true;
    on.onchange = () => edit("effect", { path: f.path, enabled: on.checked }, on.checked ? "Effect on" : "Effect off");
    show(h("h3", {}, "Effect: " + f.label), h("small", { class: "sub", style: "word-break:break-all" }, f.path), h("label", { style: "display:flex;gap:6px;align-items:center;margin:10px 0" }, on, "On"),
      field("Colour", colour(e.color || f.particles.color, v => edit("effect", { path: f.path, color: v }, "Colour set"))),
      field(`Speed (× ${e.speed ?? f.particles.speed})`, range(0, 3, 0.05, e.speed ?? f.particles.speed, v => edit("effect", { path: f.path, speed: v }, "Speed set"))),
      field(`Amount (× ${e.rate ?? 1})`, range(0, 4, 0.1, e.rate ?? 1, v => edit("effect", { path: f.path, rate: v }, "Amount set"))),
      field(`Size (× ${e.size ?? 1})`, range(0.2, 4, 0.1, e.size ?? 1, v => edit("effect", { path: f.path, size: v }, "Size set"))),
      h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "danger", onclick: () => edit("effect", { path: f.path, reset: true }, "Effect restored") }, "Restore original")));
  }
  const motionSel = (value, onchange) => { const s = h("select", {}, h("option", { value: "" }, "none"), map.motions.map(m => h("option", { value: m }, m))); s.value = value || ""; s.onchange = () => onchange(s.value); return s; };
  function showAdded(a) {
    state.boardSel = { board: b.slug, k: "added", key: a.slug };
    const kind = a.model ? "3D model" : a.image ? "image" : a.light ? "light" : "particle effect";
    show(h("h3", {}, a.name), h("small", { class: "sub" }, kind + (a.particles ? " · " + a.particles.preset : "")),
      h("div", { class: "toolbar", style: "margin:10px 0" }, h("button", { onclick: () => setPending({ label: "move " + a.name, run: (x, y) => edit("move", { item: a.slug, x, y }, "Moved") }) }, "Move to a spot...")),
      a.model ? field(`Size (${a.fit ?? "own scale"} board units; the table is about 100 wide)`, range(1, 40, 0.5, a.fit ?? 10, v => edit("move", { item: a.slug, fit: v }, "Resized"))) : null,
      a.model || a.image ? field(`Turn (${a.rot ? a.rot[1] : 0}°)`, range(-180, 180, 5, a.rot ? a.rot[1] : 0, v => edit("move", { item: a.slug, rot: [a.rot ? a.rot[0] : 0, v, a.rot ? a.rot[2] : 0] }, "Turned"))) : null,
      a.model || a.image ? h("div", { class: "row" }, field("Tint", colour(a.tint, v => edit("move", { item: a.slug, tint: v }, "Tinted"))), field("Glow", colour(a.glow || [0, 0, 0], v => edit("move", { item: a.slug, glow: v }, "Glow set")))) : null,
      field("Motion", motionSel(a.motion && a.motion.type, v => edit("move", { item: a.slug, motion: v }, "Motion set"))),
      h("div", { class: "toolbar", style: "margin-top:12px" }, h("span", { class: "grow" }), h("button", { class: "danger", onclick: () => edit("take", { item: a.slug }, "Removed") }, "Remove")));
  }
  // add tools
  function addTool(kind) {
    if (kind === "model" || kind === "image") {
      let file = null;
      const nm = h("input", { placeholder: kind === "model" ? "e.g. Runestone" : "e.g. Rug" });
      const size = h("input", { type: "number", value: kind === "model" ? 10 : 12, min: 0.5, step: 0.5 });
      const mot = motionSel("", () => {});
      show(h("h3", {}, kind === "model" ? "Add a 3D model" : "Add an image"),
        h("p", { class: "sub" }, kind === "model" ? "OBJ, GLB or glTF (a .zip with its textures works too). FBX, .blend, DAE, 3DS, STL, PLY and USD are converted with Blender if it is installed." : "Any PNG/JPG; transparent parts are cut away. It lies flat on the table."),
        field("Name", nm), dropZone(kind === "model" ? "Drop a model or click" : "Drop an image or click", kind === "model" ? "" : "image/*", p => { file = p; if (!nm.value) nm.value = p.split(/[\\/]/).pop().replace(/^\d+-/, "").replace(/\.[^.]+$/, ""); }),
        field(kind === "model" ? "Size (board units; the table is about 100 wide)" : "Width (board units)", size), field("Motion", mot),
        h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: () => {
          if (!file) return toast("Choose a file first.", true);
          setPending({ label: nm.value || kind, run: (x, y) => edit(kind, kind === "model"
            ? { model: file, name: nm.value, x, y, fit: +size.value, motion: mot.value || null }
            : { image: file, name: nm.value, x, y, width: +size.value, motion: mot.value || null }, "Added") });
        } }, "Place on the board...")));
    } else if (kind === "light") {
      const col = h("input", { type: "color", value: "#ffcc88" }), inten = h("input", { type: "number", value: 1.5, step: 0.1, min: 0 }), reach = h("input", { type: "number", value: 15, min: 1 });
      const kindSel = h("select", {}, h("option", { value: "point" }, "Glow all around (point)"), h("option", { value: "spot" }, "Spotlight (from above)"));
      show(h("h3", {}, "Add a light"), field("Kind", kindSel), h("div", { class: "row" }, field("Colour", col), field("Brightness", inten), field("Reach", reach)),
        h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: () =>
          setPending({ label: "light", run: (x, y) => edit("add-light", { x, y, kind: kindSel.value, color: col.value, intensity: +inten.value, range: +reach.value }, "Light added") }) }, "Place on the board...")));
    } else {
      const preset = h("select", {}, map.presets.map(p => h("option", { value: p }, p)));
      const col = h("input", { type: "color", value: "#ffffff" }), useCol = h("input", { type: "checkbox" });
      const amount = h("input", { type: "number", value: 1, step: 0.1, min: 0.1 }), area = h("input", { type: "number", value: 6, step: 1, min: 1 });
      show(h("h3", {}, "Add a particle effect"), field("Kind", preset),
        h("div", { class: "row" }, field("Amount (×)", amount), field("Area (board units)", area)),
        h("label", { style: "display:flex;gap:6px;align-items:center" }, useCol, "Own colour", col),
        h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: () =>
          setPending({ label: preset.value, run: (x, y) => edit("add-effect", { preset: preset.value, x, y, rate: +amount.value, area: +area.value, color: useCol.checked ? col.value : null }, "Effect added") }) }, "Place on the board...")));
    }
  }
  // whole board
  const lighting = ed.lighting || {};
  const texList = h("div", { style: "max-height:360px;overflow:auto" });
  for (const t of map.textures) {
    const mine = (ed.textures || {})[t.texture];
    texList.append(h("div", { class: "row", style: "align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--line)" },
      h("div", { style: "flex:1;min-width:0" }, h("b", {}, t.label), h("br"), h("small", { class: "sub" }, `${t.size[0]}×${t.size[1]} · used by ${t.used_by.length} object(s)${mine ? " · replaced" : ""}`)),
      dropZone(mine ? "replace again" : "replace", "image/*", p => edit("texture", { texture: t.texture, image: p }, "Texture replaced")),
      mine ? h("button", { class: "danger", onclick: () => edit("texture", { texture: t.texture, reset: true }, "Texture restored") }, "✕") : null));
  }
  main.append(h("div", { class: "toolbar" }, h("button", { onclick: () => { state.boardEdit = null; document.onkeydown = null; refresh(); } }, "← Boards"),
      h("h1", { style: "margin:0" }, b.name), h("span", { class: "sub" }, `on ${map.name} · ${b.mode}`)),
    h("p", { class: "sub" }, "Changes are saved at once and show in the game the next time this board loads. Markers: gold objects, yellow lights, blue effects, pink things you added (grey = hidden)."),
    h("div", { class: "toolbar" }, h("b", {}, "Add:"), ["model", "image", "light", "effect"].map(k => h("button", { onclick: () => addTool(k) }, { model: "3D model", image: "Image", light: "Light", effect: "Particle effect" }[k]))),
    hint, h("div", { style: "display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:14px;align-items:start" }, pic, inspector),
    h("h2", {}, "Whole board"), h("div", { class: "split" },
      h("div", { class: "panel" }, h("h3", {}, "Lighting"),
        field(`Brightness (× ${lighting.brightness ?? 1})`, range(0.2, 2.5, 0.05, lighting.brightness ?? 1, v => edit("lighting", { brightness: v }, "Brightness set"))),
        field("Tint", colour(lighting.tint, v => edit("lighting", { tint: v }, "Tint set"))),
        h("button", { class: "danger", onclick: () => edit("lighting", { reset: true }, "Lighting restored") }, "Restore lighting")),
      h("div", { class: "panel" }, h("h3", {}, `Textures (${map.textures.length})`), h("p", { class: "sub" }, "A new image replaces that texture everywhere on this board."), texList)));
  const sel = state.boardSel;                      // keep the selection across the re-render after a change
  if (sel && sel.board === b.slug) {
    const o = sel.k === "object" ? map.objects.find(x => x.path === sel.key) : sel.k === "light" ? map.lights.find(x => x.path === sel.key)
      : sel.k === "effect" ? map.effects.find(x => x.path === sel.key) : (ed.add || []).find(x => x.slug === sel.key);
    if (o) ({ object: showObject, light: showLight, effect: showEffect, added: showAdded })[sel.k](o);
  }
}

VIEWS.modes = async main => {
  const d = state.detail;
  const opt = await api(`/api/mods/${state.mod}/mode-options`);
  const laneInfo = Object.fromEntries(opt.lanes.map(l => [l.type, l]));
  main.append(h("h1", {}, "Game modes"), h("p", { class: "sub" }, "Custom matches against the AI: choose the lanes, each side's health, magicka, runes, deck and starting cards, turn rules, the board and a gold reward. In the game: press F10, set \"Practice mode\" to your mode, then Play > Practice."));
  const list = h("div", { class: "panel" });
  for (const m of d.modes || []) list.append(h("div", { class: "row", style: "align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--line)" },
    h("div", { style: "flex:1;min-width:0" }, h("b", {}, m.name), h("br"), h("small", { class: "sub" }, (m.description || "") + `  ·  lanes ${m.lanes.map(l => (laneInfo[l.type] || {}).label || l.type).join(" / ")}`)),
    h("button", { onclick: () => form(m) }, "Edit"),
    h("button", { class: "danger", onclick: async () => { await act(() => api(`/api/mods/${state.mod}/modes/${m.slug}`, { method: "DELETE" }), "Mode removed"); refresh(); } }, "Remove")));
  if (!(d.modes || []).length) list.append(h("p", { class: "sub" }, "No modes yet."));
  const editor = h("div", {});
  main.append(list, h("div", { class: "toolbar", style: "margin:12px 0" }, h("button", { class: "primary", onclick: () => form(null) }, "New mode")), editor);
  let cardNames = null;
  const names = async () => cardNames || (cardNames = opt.cards);

  async function form(m) {
    m = m || { name: "", description: "", lanes: [{ type: "Default", size: 4 }, { type: "Stealth", size: 4 }], player: {}, opponent: {}, first: "random", difficulty: "chosen", rules: {} };
    editor.innerHTML = "";
    const name = h("input", { value: m.name, placeholder: "Mode name" }), desc = h("input", { value: m.description || "", placeholder: "One line for the F10 menu" });
    const battle = battleEditor(m, opt, d);
    editor.append(h("h2", {}, m.slug ? "Edit " + m.name : "New mode"),
      h("div", { class: "panel" }, h("div", { class: "row" }, field("Name", name), field("Description", desc))),
      battle,
      h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { onclick: () => { editor.innerHTML = ""; } }, "Cancel"),
        h("button", { class: "primary", onclick: async () => {
          if (!name.value) return toast("Name the mode.", true);
          const body = { name: name.value, description: desc.value, ...battle._get() };
          await act(() => api(`/api/mods/${state.mod}/modes`, { method: "POST", body }), "Mode saved");
          refresh(); } }, "Save mode")));
    editor.scrollIntoView({ behavior: "smooth" });
  }
};

// A match setup (game modes and story battles): lanes, both sides, who starts, AI, board, gold, turn rules.
// opt: mode-options or story-options (lanes, decks, zones, rules, difficulties, bases, cards). Returns an element with _get().
function battleEditor(m, opt, d, extra = {}) {
  m = m || {};
  m.lanes = m.lanes && m.lanes.length ? m.lanes : [{ type: "Default", size: 4 }, { type: "Stealth", size: 4 }];
  const laneInfo = Object.fromEntries(opt.lanes.map(l => [l.type, l]));
  const listId = "cards-" + Math.random().toString(36).slice(2);
  const dl = h("datalist", { id: listId }, (opt.cards || []).map(n => h("option", { value: n })));
  const laneCount = h("select", {}, h("option", { value: 2 }, "Two lanes"), h("option", { value: 1 }, "One lane")); laneCount.value = String(m.lanes.length);
  const laneRows = h("div", {});
  const laneSel = [];
  const drawLanes = () => {
    laneRows.innerHTML = ""; laneSel.length = 0;
    for (let i = 0; i < +laneCount.value; i++) {
      const cur = m.lanes[i] || { type: i ? "Stealth" : "Default", size: 4 };
      const type = h("select", {}, opt.lanes.filter(l => l.implemented).map(l => h("option", { value: l.type }, l.label)));
      type.value = cur.type;
      const size = h("select", {}, [2, 4, 6].map(s => h("option", { value: s }, `${s} creatures`))); size.value = String(cur.size || 4);
      const info = h("small", { class: "sub", style: "display:block;min-height:1.2em" }, (laneInfo[type.value] || {}).description || "");
      type.onchange = () => { info.textContent = (laneInfo[type.value] || {}).description || ""; };
      laneSel.push({ type, size });
      laneRows.append(h("div", { class: "field" }, h("label", {}, i === 0 ? "Left lane" : "Right lane"), h("div", { class: "row" }, type, size), info));
    }
  };
  laneCount.onchange = drawLanes; drawLanes();
  const side = (title, s, isAi) => {
    s = s || {};
    const num = (k, ph) => h("input", { type: "number", value: s[k] ?? "", placeholder: ph, style: "width:90px" });
    const f = { health: num("health", "30"), magicka: num("magicka", "1"), runes: num("runes", "5"), extra_cards: num("extra_cards", "0") };
    const deck = h("select", {}, opt.decks.filter(x => isAi || x.deck !== "practice").map(x => h("option", { value: x.deck }, x.label)));
    deck.value = s.deck || (isAi ? "practice" : "own");
    const rows = h("div", {});
    const addRow = (place, card) => {
      const p = h("select", {}, Object.entries(opt.zones).map(([k, v]) => h("option", { value: k }, v))); p.value = place || "hand";
      const c = h("input", { list: listId, value: card || "", placeholder: "Card name", style: "flex:1" });
      const row = h("div", { class: "row", style: "gap:6px;margin:3px 0" }, c, p, h("button", { onclick: () => row.remove() }, "✕"));
      row._get = () => ({ place: p.value, card: c.value.trim() });
      rows.append(row);
    };
    for (const [place, cards] of Object.entries(s.cards || {})) for (const c of cards) addRow(place, c);
    const box = h("div", { class: "panel" }, h("h3", {}, title),
      h("div", { class: "row" }, field("Health", f.health), field("Magicka at start", f.magicka), field("Runes (0-5)", f.runes), field("Extra cards at start", f.extra_cards)),
      field("Deck", deck), h("label", {}, "Starting cards"), rows, h("button", { onclick: () => addRow("hand", "") }, "+ Add a card"));
    box._get = () => {
      const out = { deck: deck.value, cards: {} };
      for (const [k, el] of Object.entries(f)) if (el.value !== "") out[k] = +el.value;
      for (const r of rows.children) { const v = r._get(); if (v.card) (out.cards[v.place] = out.cards[v.place] || []).push(v.card); }
      return out;
    };
    return box;
  };
  const you = side("You", m.player, false), ai = side("The AI", m.opponent, true);
  const first = h("select", {}, [["random", "Random"], ["player", "You"], ["opponent", "The AI"]].map(([v, t]) => h("option", { value: v }, t))); first.value = m.first || "random";
  const diff = h("select", {}, opt.difficulties.map(v => h("option", { value: v }, v === "chosen" ? (extra.story ? "Adept" : "As chosen on the Practice screen") : v))); diff.value = m.difficulty || (extra.story ? "Novice" : "chosen");
  const aiName = h("input", { value: m.opponent_name || "", placeholder: "AI name (optional)" });
  const aiPick = h("select", {}, h("option", { value: "" }, "None (the game's opponent)"), (d.opponent_choices || []).map(o => h("option", { value: o.key }, o.label)));
  if (m.ai && !(d.opponent_choices || []).some(o => o.key === m.ai)) aiPick.append(h("option", { value: m.ai }, m.ai + " (mod not enabled)"));
  aiPick.value = m.ai || "";
  const rules = Object.fromEntries(Object.entries(opt.rules).map(([k]) => [k, h("input", { type: "number", min: 0, value: (m.rules || {})[k] || "", placeholder: "0", style: "width:80px" })]));
  const noMull = h("input", { type: "checkbox" }); noMull.checked = !!(m.rules || {}).no_mulligan;
  const board = h("select", {}, h("option", { value: "" }, "The game's choice"), opt.bases.map(b => h("option", { value: b }, b.replace(/([a-z])([A-Z])/g, "$1 $2"))),
    (d.boards || []).map(b => h("option", { value: `${state.mod}/${b.slug}` }, b.name + " (this mod)")));
  board.value = m.board || "";
  const gold = h("input", { type: "number", min: 0, value: m.reward_gold || 0, style: "width:100px" });
  const box = h("div", {}, dl,
    h("div", { class: "split" }, h("div", { class: "panel" }, h("h3", {}, "Lanes"), field("Lanes", laneCount), laneRows),
      h("div", { class: "panel" }, h("h3", {}, "Match"), h("div", { class: "row" }, field("Who goes first", first), field("AI difficulty", diff)), field("AI name", aiName),
        field("AI opponent", aiPick, "One of your AI opponents: its portrait, and its name, deck, difficulty and personality unless set here."),
        extra.matchExtras || null, field("Board", board), field("Gold for a win", gold))),
    h("div", { class: "split" }, you, ai),
    h("div", { class: "panel" }, h("h3", {}, "Turn rules"),
      h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px" }, Object.entries(opt.rules).map(([k, label]) => field(label[0].toUpperCase() + label.slice(1), rules[k]))),
      h("label", { style: "display:flex;gap:6px;align-items:center;margin-top:8px" }, noMull, "No mulligan")));
  box._get = () => {
    const out = { lanes: laneSel.map(l => ({ type: l.type.value, size: +l.size.value })), player: you._get(), opponent: ai._get(),
      first: first.value, difficulty: diff.value, opponent_name: aiName.value, ai: aiPick.value, board: board.value, reward_gold: +gold.value,
      rules: { ...Object.fromEntries(Object.entries(rules).map(([k, el]) => [k, el.value === "" ? 0 : +el.value])), no_mulligan: noMull.checked } };
    if (extra.story) {   // story JSON keeps only what is set
      if (!out.opponent_name) delete out.opponent_name;
      if (!out.ai) delete out.ai;
      if (!out.board) delete out.board;
      if (!out.reward_gold) delete out.reward_gold;
      if (out.difficulty === "chosen") out.difficulty = "Adept";
      out.rules = Object.fromEntries(Object.entries(out.rules).filter(([, v]) => v));
      if (!Object.keys(out.rules).length) delete out.rules;
      for (const s of [out.player, out.opponent]) if (!Object.keys(s.cards).length) delete s.cards;
    }
    return out;
  };
  return box;
}

// ---- Stories -----------------------------------------------------------------------------------------------------------
VIEWS.stories = async main => {
  const d = state.detail;
  main.append(h("h1", {}, "Stories"), h("p", { class: "sub" }, "Story campaigns played from Play > Stories in the offline game: acts, chapters (episodes) with a map, events on the map (location discs) with dialogue, choices and battles. Choices can give cards or gold and unlock other events, so a story can branch. Voice lines are optional sound files per line."));
  const list = h("div", { class: "panel" });
  for (const s of d.stories || []) list.append(h("div", { class: "row", style: "align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--line)" },
    h("div", { style: "flex:1;min-width:0" }, h("b", {}, s.name), h("br"), h("small", { class: "sub" }, `${s.description || ""}  ·  ${s.acts} acts, ${s.chapters} chapters, ${s.events} events, ${s.battles} battles`)),
    h("button", { onclick: () => storyEditor(editor, s.slug) }, "Edit"),
    h("button", { class: "danger", onclick: async () => { if (!confirm(`Delete the story "${s.name}" and its files?`)) return; await act(() => api(`/api/mods/${state.mod}/stories/${s.slug}`, { method: "DELETE" }), "Story removed"); refresh(); } }, "Remove")));
  if (!(d.stories || []).length) list.append(h("p", { class: "sub" }, "No stories yet."));
  const editor = h("div", {});
  const name = h("input", { placeholder: "Story name" }), desc = h("input", { placeholder: "One line for the story picker" });
  const template = h("select", {}, Object.entries({ DBH: "The Fall of the Dark Brotherhood", CWC: "Return to Clockwork City", IOM: "Isle of Madness" }).map(([k, v]) => h("option", { value: k }, v)));
  main.append(list, h("div", { class: "panel", style: "margin-top:12px" }, h("h3", {}, "New story"),
    h("div", { class: "row" }, field("Name", name), field("Description", desc), field("Look of", template, "Screens and default art are borrowed from this story until you add your own.")),
    h("button", { class: "primary", onclick: async () => {
      if (!name.value) return toast("Name the story.", true);
      const r = await act(() => api(`/api/mods/${state.mod}/stories`, { method: "POST", body: { new: true, name: name.value, description: desc.value, template: template.value } }), "Story created");
      state.detail.stories = (await api(`/api/mods/${state.mod}/stories`)).stories;
      storyEditor(editor, r.story.slug);
    } }, "Create story")), editor);
};

async function storyEditor(editor, slug) {
  editor.innerHTML = "";
  editor.append(h("p", {}, h("span", { class: "spinner" }), " Loading story…"));
  const [loaded, opt] = await Promise.all([api(`/api/mods/${state.mod}/stories/${slug}`), api(`/api/mods/${state.mod}/story-options`)]);
  let doc = loaded.story;
  const draftKey = `forge.draft.${state.mod}.story.${slug}`;
  const draft = Drafts.get(draftKey);
  if (draft && JSON.stringify(draft.doc) !== JSON.stringify(doc) && confirm(`This story has unsaved changes from ${draft.time}. Restore them?`)) doc = draft.doc;
  else if (draft) Drafts.drop(draftKey);
  if (editor._draftTimer) clearInterval(editor._draftTimer);
  const keepDraft = editor._draftTimer = setInterval(() => {
    if (!document.body.contains(editor) || !editor.firstChild) return clearInterval(keepDraft);
    const now = JSON.stringify(doc);
    if (now !== JSON.stringify(loaded.story)) Drafts.put(draftKey, { time: new Date().toLocaleString(), doc: JSON.parse(now) });
  }, 3000);
  let files = { images: loaded.images, voices: loaded.voices };
  const d = state.detail;
  const fileUrl = f => `/mod-file/${state.mod}/stories/${doc.slug}/${encodeURIComponent(f)}`;
  const previewOf = {};
  for (const list of [opt.maps, opt.discs, opt.portraits, opt.story_art || []]) for (const x of list) previewOf[x.asset] = `/api/assets/preview?path=${encodeURIComponent(x.preview)}`;
  const imgUrl = v => !v ? null : v.startsWith("asset:") ? previewOf[v] || null : v.startsWith("ai:") ? null : fileUrl(v);
  let sel = { kind: "story" };   // {kind, a, c, e}
  const tree = h("div", { class: "panel", style: "position:sticky;top:10px;max-height:85vh;overflow:auto" });
  const pane = h("div", {});
  editor.innerHTML = "";
  editor.append(h("h2", {}, "Edit " + doc.name),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }, h("small", { class: "sub" }, "Changes are kept here until you save. Saving checks the whole story.")),
      h("button", { onclick: () => { Drafts.drop(draftKey); storyEditor(editor, slug); } }, "Discard changes"),
      h("button", { class: "primary", onclick: async () => {
        commitPending();
        const r = await act(() => api(`/api/mods/${state.mod}/stories`, { method: "POST", body: { story: doc } }), "Story saved");
        Drafts.drop(draftKey); loaded.story = JSON.parse(JSON.stringify(doc));
        state.detail.stories = (await api(`/api/mods/${state.mod}/stories`)).stories;
        toast(`${r.summary.chapters} chapters, ${r.summary.events} events, ${r.summary.battles} battles`);
      } }, "Save story")),
    h("div", { class: "editor-2col" }, tree, pane));
  editor.scrollIntoView({ behavior: "smooth" });

  const allEvents = () => {
    const out = [];
    for (const a of doc.acts || []) for (const c of a.chapters || []) for (const e of c.events || []) out.push({ key: `${a.slug}/${c.slug}/${e.slug}`, label: `${a.name} › ${c.name} › ${e.name}`, e });
    return out;
  };
  const slugOf = (text, taken) => { let base = (text || "item").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item", s = base, n = 2; while (taken.includes(s)) s = `${base}-${n++}`; return s; };

  // An image value: a file in the story folder (pick or upload) or an installed image (asset:...).
  function imageInput(value, onChange, kinds = ["portraits", "discs"], placeholder = "none") {
    const box = h("div", { style: "display:flex;flex-wrap:wrap;align-items:center;gap:8px" });
    const pic = h("img", { style: "width:64px;height:64px;object-fit:cover;border-radius:50%;background:var(--img-bg);border:1px solid var(--line)" });
    const choice = h("select", { style: "flex:1;min-width:180px;width:auto" });
    const fill = () => {
      choice.innerHTML = "";
      choice.append(h("option", { value: "" }, `(${placeholder})`));
      if (files.images.length) choice.append(h("optgroup", { label: "This story's images" }, files.images.map(f => h("option", { value: f }, f))));
      for (const k of kinds) choice.append(h("optgroup", { label: { maps: "Game story maps", discs: "Game location discs", portraits: "Game portraits", story_art: "Game story art (tiles, banners, act and chapter pictures)" }[k] }, (opt[k] || []).map(x => h("option", { value: x.asset }, x.label))));
      if (value && ![...choice.options].some(o => o.value === value)) choice.append(h("option", { value }, value));
      choice.value = value || "";
      const u = imgUrl(choice.value); pic.src = u || ""; pic.style.visibility = u ? "visible" : "hidden";
    };
    choice.onchange = () => { value = choice.value; onChange(value || undefined); fill(); };
    const up = h("input", { type: "file", accept: ".png,.jpg,.jpeg", class: "hidden" });
    up.onchange = async () => {
      const f = up.files[0]; if (!f) return;
      const path = await act(() => upload(f));
      const r = await act(() => api(`/api/mods/${state.mod}/stories/${doc.slug}/file`, { method: "POST", body: { file: path } }), "Image added");
      if (!files.images.includes(r.file)) files.images.push(r.file);
      value = r.file; onChange(value); fill();
    };
    fill();
    box.append(pic, choice, h("button", { onclick: () => up.click() }, "Upload…"), up);
    return box;
  }

  function voiceInput(value, onChange) {
    const choice = h("select", {}, h("option", { value: "" }, "(no voice)"), files.voices.map(f => h("option", { value: f }, f)));
    choice.value = value || "";
    choice.onchange = () => onChange(choice.value || undefined);
    const up = h("input", { type: "file", accept: ".wav,.ogg,.mp3,.flac,.m4a", class: "hidden" });
    up.onchange = async () => {
      const f = up.files[0]; if (!f) return;
      const path = await act(() => upload(f));
      const r = await act(() => api(`/api/mods/${state.mod}/stories/${doc.slug}/file`, { method: "POST", body: { file: path } }), "Voice line added");
      if (!files.voices.includes(r.file)) { files.voices.push(r.file); choice.append(h("option", { value: r.file }, r.file)); }
      choice.value = r.file; onChange(r.file);
    };
    return h("div", { class: "row", style: "grid-template-columns:1fr auto auto;gap:6px" }, choice,
      h("button", { title: "Play", onclick: () => choice.value && playUrl(fileUrl(choice.value)) }, "▶"), h("button", { onclick: () => up.click() }, "Upload…"), up);
  }

  // requires: [{event, choice, when}]
  function requiresEditor(list, onChange, hint) {
    list = list || [];
    const box = h("div", {});
    const draw = () => {
      box.innerHTML = "";
      list.forEach((r, i) => {
        const ev = h("select", {}, allEvents().map(x => h("option", { value: x.key }, x.label)));
        const keyOf = v => { const all = allEvents(); const parts = (v || "").split("/"); return (all.find(x => x.key === v) || all.find(x => x.key.endsWith("/" + parts.slice(-2).join("/"))) || all.find(x => x.key.endsWith("/" + parts[parts.length - 1])) || {}).key; };
        ev.value = keyOf(r.event) || "";
        const ch = h("select", {}, h("option", { value: 0 }, "is complete"), [1, 2, 3].map(n => h("option", { value: n }, `choice ${n} was picked`))); ch.value = String(r.choice || 0);
        const when = h("select", {}, h("option", { value: "intro" }, "in its intro"), h("option", { value: "ending" }, "in its ending")); when.value = r.when || "intro";
        const upd = () => { list[i] = { event: ev.value }; if (+ch.value) { list[i].choice = +ch.value; if (when.value !== "intro") list[i].when = when.value; } onChange(list.length ? list : undefined); };
        ev.onchange = ch.onchange = when.onchange = upd;
        box.append(h("div", { class: "row", style: "grid-template-columns:2fr 1fr 1fr auto;gap:6px;margin:3px 0" }, ev, ch, when,
          h("button", { onclick: () => { list.splice(i, 1); onChange(list.length ? list : undefined); draw(); } }, "✕")));
      });
      box.append(h("button", { onclick: () => { const all = allEvents(); if (!all.length) return toast("Add an event first.", true); list.push({ event: all[0].key }); onChange(list); draw(); } }, "+ Requirement"));
      if (hint) box.append(h("small", { class: "sub", style: "display:block" }, hint));
    };
    draw();
    return box;
  }

  // Dialogue lines: speaker, text, portrait, voice, choices (max 3), end, requires.
  function linesEditor(lines, onChange, title) {
    lines = lines || [];
    const box = h("div", { class: "panel" }, h("h3", {}, title));
    const body = h("div", {});
    const draw = () => {
      body.innerHTML = "";
      lines.forEach((l, i) => {
        const speaker = h("input", { value: l.speaker || "", placeholder: "Speaker" });
        const text = h("textarea", { rows: 3, placeholder: "What they say" }, l.text || "");
        speaker.oninput = () => { l.speaker = speaker.value || undefined; };
        text.oninput = () => { l.text = text.value; };
        const end = h("input", { type: "checkbox" }); end.checked = !!l.end; end.onchange = () => { l.end = end.checked || undefined; };
        const choices = h("div", {});
        const drawChoices = () => {
          choices.innerHTML = "";
          (l.choices || []).forEach((o, k) => {
            const t = h("input", { value: o.text || "", placeholder: `Choice ${k + 1} button` });
            const ds = h("input", { value: o.description || "", placeholder: "Description (optional)" });
            const card = h("input", { list: "story-cards", value: o.card || "", placeholder: "Gives card (optional)" });
            const gold = h("input", { type: "number", min: 0, value: o.gold || "", placeholder: "Gold", style: "width:80px" });
            t.oninput = () => { o.text = t.value; }; ds.oninput = () => { o.description = ds.value || undefined; };
            card.oninput = () => { o.card = card.value || undefined; }; gold.oninput = () => { o.gold = +gold.value || undefined; };
            choices.append(h("div", { class: "row", style: "grid-template-columns:1.2fr 1.2fr 1fr 80px auto;gap:6px;margin:3px 0" }, t, ds, card, gold,
              h("button", { onclick: () => { l.choices.splice(k, 1); if (!l.choices.length) delete l.choices; drawChoices(); } }, "✕")));
          });
          if ((l.choices || []).length < 3) choices.append(h("button", { onclick: () => { (l.choices = l.choices || []).push({ text: "" }); drawChoices(); } }, "+ Choice"));
          choices.append(h("small", { class: "sub", style: "display:block" }, "No choices: the line shows a Continue button. A choice on an event's last intro line can pick its battle and unlock other events."));
        };
        drawChoices();
        const move = dir => { const j = i + dir; if (j < 0 || j >= lines.length) return; [lines[i], lines[j]] = [lines[j], lines[i]]; draw(); };
        body.append(h("div", { style: "border-top:1px solid var(--line);padding:10px 0" },
          h("div", { class: "row", style: "grid-template-columns:1fr auto auto auto;gap:6px;align-items:center" }, h("b", {}, `Line ${i + 1}`),
            h("button", { onclick: () => move(-1) }, "↑"), h("button", { onclick: () => move(1) }, "↓"),
            h("button", { class: "danger", onclick: () => { lines.splice(i, 1); onChange(lines); draw(); } }, "Remove")),
          h("div", { class: "row", style: "grid-template-columns:1fr 2fr;gap:10px" },
            h("div", {}, field("Speaker", speaker), field("Portrait", imageInput(l.portrait, v => { l.portrait = v; }, ["portraits", "discs"])),
              field("Voice", voiceInput(l.voice, v => { l.voice = v; }), "Optional sound file; VoiceVault lines can be added later.")),
            h("div", {}, field("Text", text), h("label", {}, "Choices"), choices,
              h("label", { style: "display:flex;gap:6px;align-items:center;margin-top:6px" }, end, "End the conversation after this line"),
              h("details", {}, h("summary", {}, "Only show this line if…"), requiresEditor(l.requires, v => { l.requires = v; }))))));
      });
      body.append(h("button", { onclick: () => { lines.push({ speaker: lines.length ? lines[lines.length - 1].speaker : "", text: "" }); onChange(lines); draw(); } }, "+ Add a line"));
    };
    draw();
    box.append(body);
    return box;
  }

  function rewardsEditor(list, onChange) {
    list = list || [];
    const box = h("div", {});
    const draw = () => {
      box.innerHTML = "";
      list.forEach((r, i) => {
        const kind = Object.keys(opt.rewards).find(k => k in r) || "gold";
        const k = h("select", {}, Object.entries(opt.rewards).map(([key, label]) => h("option", { value: key }, label))); k.value = kind;
        const v = kind === "card" ? h("input", { list: "story-cards", value: r.card || "", placeholder: "Card name" })
          : kind === "pack" ? h("select", {}, opt.packs.map(p => h("option", { value: p }, p))) : h("input", { type: "number", min: 1, value: r[kind] || "" });
        if (kind === "pack") v.value = r.pack || "core";
        const count = kind === "card" ? h("input", { type: "number", min: 1, max: 3, value: r.count || 1, style: "width:60px" }) : null;
        const upd = () => { const o = {}; o[k.value] = k.value === "card" || k.value === "pack" ? v.value : +v.value; if (count && +count.value > 1) o.count = +count.value; list[i] = o; onChange(list); };
        k.onchange = () => { list[i] = { [k.value]: k.value === "card" ? "" : k.value === "pack" ? "core" : 50 }; onChange(list); draw(); };
        v.oninput = v.onchange = upd; if (count) count.oninput = upd;
        box.append(h("div", { class: "row", style: "grid-template-columns:1fr 2fr auto auto;gap:6px;margin:3px 0" }, k, v, count || h("span"), h("button", { onclick: () => { list.splice(i, 1); onChange(list.length ? list : undefined); draw(); } }, "✕")));
      });
      box.append(h("button", { onclick: () => { list.push({ gold: 50 }); onChange(list); draw(); } }, "+ Reward"));
    };
    draw();
    return box;
  }

  function battlePanel(b, onRemove, variantNote) {
    const portrait = imageInput(b.opponent_portrait, v => { b.opponent_portrait = v; }, ["portraits", "discs"], "the template's opponent");
    const briefing = h("textarea", { rows: 2, placeholder: "Shown before the match (optional)" }, b.briefing || "");
    briefing.oninput = () => { b.briefing = briefing.value || undefined; };
    const setup = battleEditor(b, opt, d, { story: true, matchExtras: field("AI portrait", portrait) });
    const victory = linesEditor(b.victory_lines || [], v => { b.victory_lines = v.length ? v : undefined; }, "When the AI is beaten (lines in the match)");
    const mst = b.master || {};
    const mDiff = h("select", {}, ["Expert", "Adept", "Novice"].map(v => h("option", { value: v }, v))); mDiff.value = mst.difficulty || "Expert";
    const mHealth = h("input", { type: "number", min: 1, value: (mst.opponent || {}).health || "", placeholder: "same", style: "width:90px" });
    const mMagicka = h("input", { type: "number", min: 0, max: 12, value: (mst.opponent || {}).magicka || "", placeholder: "same", style: "width:90px" });
    const mDeck = h("select", {}, h("option", { value: "" }, "Same deck"), opt.decks.filter(x => x.deck !== "own").map(x => h("option", { value: x.deck }, x.label))); mDeck.value = (mst.opponent || {}).deck || "";
    const masterBox = h("div", { class: "panel" }, h("h3", {}, "Master difficulty"), h("p", { class: "sub" }, "The same battle on Master, with these changes."),
      h("div", { class: "row" }, field("AI difficulty", mDiff), field("AI health", mHealth), field("AI starting magicka", mMagicka), field("AI deck", mDeck)));
    const panel = h("div", { style: "border:1px solid var(--line);border-radius:10px;padding:12px;margin:10px 0" },
      variantNote || null, setup, h("div", { class: "panel" }, field("Briefing", briefing)), victory, masterBox,
      onRemove ? h("button", { class: "danger", onclick: onRemove }, "Remove this battle") : null);
    panel._commit = () => {
      const m = { ...(b.master || {}) }; const o = { ...(m.opponent || {}) };
      m.difficulty = mDiff.value; if (mDiff.value === "Expert") delete m.difficulty;
      for (const [k, el] of [["health", mHealth], ["magicka", mMagicka]]) { if (el.value !== "") o[k] = +el.value; else delete o[k]; }
      if (mDeck.value) o.deck = mDeck.value; else delete o.deck;
      if (Object.keys(o).length) m.opponent = o; else delete m.opponent;
      b.master = Object.keys(m).length ? m : undefined;
      const keep = { requires: b.requires, opponent_portrait: b.opponent_portrait, briefing: b.briefing, victory_lines: b.victory_lines, master: b.master };
      const got = setup._get(); for (const k of Object.keys(b)) delete b[k]; Object.assign(b, got); for (const [k, v] of Object.entries(keep)) if (v !== undefined) b[k] = v; };
    return panel;
  }

  // Map with the chapter's events; click to place the selected event.
  function mapView(c, current) {
    const wrap = h("div", { style: "position:relative;display:inline-block;max-width:100%;cursor:crosshair;user-select:none" });
    const url = imgUrl(c.map) || null;
    const img = h("img", { src: url || "", style: "display:block;max-width:100%;max-height:520px;border-radius:8px;background:#222;min-width:480px;min-height:270px" });
    wrap.append(img);
    (c.events || []).forEach((e, i) => {
      const x = e.x ?? (0.2 + 0.15 * (i % 5)), y = e.y ?? (0.4 + 0.2 * Math.floor(i / 5));
      const u = imgUrl(e.coin) || imgUrl(((e.intro || [])[0] || {}).portrait);
      const dot = h("div", { title: e.name, style: `position:absolute;left:${x * 100}%;top:${y * 100}%;transform:translate(-50%,-50%);width:54px;height:54px;border-radius:50%;` +
        `border:3px solid ${e === current ? "var(--gold)" : "#ddd"};background:#333 center/cover no-repeat;${u ? `background-image:url('${u}');` : ""}box-shadow:0 2px 6px #000a` });
      const tag = h("div", { style: `position:absolute;left:${x * 100}%;top:calc(${y * 100}% + 32px);transform:translateX(-50%);font-size:0.857rem;background:#000b;padding:1px 6px;border-radius:4px;white-space:nowrap` }, e.name);
      wrap.append(dot, tag);
    });
    wrap.onclick = ev => {
      if (!current) return toast("Select an event to place it.", true);
      const r = img.getBoundingClientRect();
      current.x = Math.round(Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)) * 1000) / 1000;
      current.y = Math.round(Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height)) * 1000) / 1000;
      render();
    };
    return h("div", {}, wrap, h("small", { class: "sub", style: "display:block" }, current ? `Click the map to move "${current.name}".` : "Select an event, then click the map to place it."));
  }

  let commitPending = () => {};
  function select(s) { commitPending(); commitPending = () => {}; sel = s; render(); }

  function drawTree() {
    tree.innerHTML = "";
    const item = (label, s, depth, active) => h("div", { style: `padding:4px 6px 4px ${8 + depth * 14}px;border-radius:6px;cursor:pointer;${active ? "background:var(--active-bg);color:var(--gold)" : ""}`, onclick: () => select(s) }, label);
    tree.append(item("📖 " + doc.name, { kind: "story" }, 0, sel.kind === "story"));
    (doc.acts || []).forEach(a => {
      tree.append(item("Act: " + a.name, { kind: "act", a }, 1, sel.a === a && sel.kind === "act"));
      (a.chapters || []).forEach(c => {
        tree.append(item("Chapter: " + c.name, { kind: "chapter", a, c }, 2, sel.c === c && sel.kind === "chapter"));
        (c.events || []).forEach(e => tree.append(item(((e.battle || e.battles) ? "⚔ " : "💬 ") + e.name, { kind: "event", a, c, e }, 3, sel.e === e)));
      });
    });
  }

  function render() {
    drawTree();
    pane.innerHTML = "";
    pane.append(h("datalist", { id: "story-cards" }, (opt.cards || []).map(n => h("option", { value: n }))));
    const txt = (obj, key, ph, area) => { const el = area ? h("textarea", { rows: 2, placeholder: ph }, obj[key] || "") : h("input", { value: obj[key] || "", placeholder: ph }); el.oninput = () => { obj[key] = el.value || undefined; if (key === "name") drawTree(); }; return el; };
    const order = (arr, item, label, mk) => h("div", { class: "toolbar" },
      h("button", { onclick: () => { const i = arr.indexOf(item); if (i > 0) { [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]]; render(); } } }, "Move up"),
      h("button", { onclick: () => { const i = arr.indexOf(item); if (i < arr.length - 1) { [arr[i + 1], arr[i]] = [arr[i], arr[i + 1]]; render(); } } }, "Move down"),
      mk || null, h("span", { class: "grow" }),
      h("button", { class: "danger", onclick: () => { if (!confirm(`Remove ${label}?`)) return; arr.splice(arr.indexOf(item), 1); select({ kind: "story" }); } }, `Remove ${label}`));
    if (sel.kind === "story") {
      const template = h("select", {}, Object.entries(opt.templates).map(([k, v]) => h("option", { value: k }, v))); template.value = doc.template || "DBH";
      template.onchange = () => { doc.template = template.value; };
      const skin = h("select", {}, opt.skins.map(s => h("option", { value: s }, { template: "The template's", none: "Plain", DBH: "Dark Brotherhood", CWC: "Clockwork City", IOM: "Isle of Madness" }[s] || s))); skin.value = doc.skin || "template";
      skin.onchange = () => { doc.skin = skin.value === "template" ? undefined : skin.value; };
      pane.append(h("div", { class: "panel" }, h("h3", {}, "Story"),
        h("div", { class: "row" }, field("Name", txt(doc, "name", "Story name")), field("Look of", template), field("Episode screen background", skin)),
        field("Description", txt(doc, "description", "Shown on the story picker", true)),
        (() => { const m = h("input", { type: "checkbox" }); m.checked = doc.master !== false; m.onchange = () => { doc.master = m.checked ? undefined : false; };
          return h("label", { style: "display:flex;gap:6px;align-items:center;margin-bottom:12px" }, m, "Master difficulty (unlocked after Normal; each battle gets a harder version)"); })(),
        h("div", { class: "row" },
          field("Story picker tile", imageInput(doc.icon, v => { doc.icon = v; }, ["story_art", "maps"], "the template's tile"), "A wide picture works best."),
          field("Story banner", imageInput(doc.banner, v => { doc.banner = v; }, ["story_art", "maps"], "the template's banner"), "Shown at the top of the story's screens.")),
        h("button", { onclick: () => { const a = { slug: slugOf("act " + ((doc.acts || []).length + 1), (doc.acts || []).map(x => x.slug)), name: "Act " + ((doc.acts || []).length + 1), chapters: [] }; (doc.acts = doc.acts || []).push(a); select({ kind: "act", a }); } }, "+ Add an act")));
    } else if (sel.kind === "act") {
      const a = sel.a;
      pane.append(h("div", { class: "panel" }, h("h3", {}, "Act"), order(doc.acts, a, "this act"),
        field("Name", txt(a, "name", "Act name")), field("Description", txt(a, "description", "One line", true)),
        field("Act picture", imageInput(a.icon, v => { a.icon = v; }, ["story_art", "maps"], "the template's act picture")),
        h("button", { onclick: () => { const n = (a.chapters || []).length + 1; const c = { slug: slugOf("chapter " + n, (a.chapters || []).map(x => x.slug)), name: "Chapter " + n, events: [] }; (a.chapters = a.chapters || []).push(c); select({ kind: "chapter", a, c }); } }, "+ Add a chapter")));
    } else if (sel.kind === "chapter") {
      const { a, c } = sel;
      pane.append(h("div", { class: "panel" }, h("h3", {}, "Chapter"), order(a.chapters, c, "this chapter"),
        h("div", { class: "row" }, field("Name", txt(c, "name", "Episode 1: …")), field("Subtitle", txt(c, "subtitle", "Optional"))),
        field("Rules note", txt(c, "rules", "Optional: special rules in this chapter", true)),
        h("div", { class: "row" }, field("Map", imageInput(c.map, v => { c.map = v; render(); }, ["maps", "story_art"], "the template's map")),
          field("Chapter picture", imageInput(c.icon, v => { c.icon = v; }, ["story_art", "maps"], "the template's chapter picture"), "The episode's tile on the act screen.")),
        field("Narrator disc", imageInput(c.coin, v => { c.coin = v; }, ["discs", "portraits"], "the template's disc"), "Shown for this chapter's lines that have no portrait."),
        mapView(c, null),
        h("button", { onclick: () => { const n = (c.events || []).length + 1; const e = { slug: slugOf("event " + n, (c.events || []).map(x => x.slug)), name: "Event " + n, x: 0.5, y: 0.5, intro: [{ speaker: "", text: "" }] }; (c.events = c.events || []).push(e); select({ kind: "event", a, c, e }); } }, "+ Add an event")),
        linesEditor(c.intro || [], v => { c.intro = v.length ? v : undefined; }, "Chapter intro (before the map)"),
        linesEditor(c.ending || [], v => { c.ending = v.length ? v : undefined; }, "Chapter ending"));
    } else if (sel.kind === "event") {
      const { a, c, e } = sel;
      const required = h("select", {}, h("option", { value: "" }, "Automatic (yes unless it needs a choice)"), h("option", { value: "yes" }, "Yes"), h("option", { value: "no" }, "No (optional)"));
      required.value = e.required === true ? "yes" : e.required === false ? "no" : "";
      required.onchange = () => { e.required = required.value === "" ? undefined : required.value === "yes"; };
      const hidden = h("input", { type: "checkbox" }); hidden.checked = !!e.hidden; hidden.onchange = () => { e.hidden = hidden.checked || undefined; };
      const battles = h("div", {});
      const panels = [];
      const drawBattles = () => {
        battles.innerHTML = ""; panels.length = 0;
        const list = (e.battle ? [e.battle] : []).concat(e.battles || []);
        if (!list.length) { battles.append(h("p", { class: "sub" }, "No battle: this event is dialogue only and completes when its intro is finished.")); }
        list.forEach((b, i) => {
          const note = list.length > 1 ? h("div", { class: "panel" }, h("b", {}, `Battle ${i + 1}`), h("p", { class: "sub" }, "Played when this intro choice was picked:"),
            requiresEditor(b.requires || [{ event: `${a.slug}/${c.slug}/${e.slug}`, choice: i + 1 }], v => { b.requires = v; })) : null;
          if (list.length > 1 && !b.requires) b.requires = [{ event: `${a.slug}/${c.slug}/${e.slug}`, choice: i + 1 }];
          const p = battlePanel(b, () => { p._commit = () => {}; const all = list.filter(x => x !== b); delete e.battle; e.battles = all.length ? all : undefined; if (all.length === 1) { e.battle = all[0]; delete e.battle.requires; delete e.battles; } drawBattles(); }, note);
          panels.push(p); battles.append(p);
        });
        battles.append(h("button", { onclick: () => {
          commitPending();
          const list2 = (e.battle ? [e.battle] : []).concat(e.battles || []);
          list2.push({ player: { deck: "own" }, opponent: { deck: "practice" }, difficulty: "Novice" });
          delete e.battle; if (list2.length === 1) e.battle = list2[0]; else e.battles = list2;
          drawBattles(); } }, list.length ? "+ Another battle (picked by the intro choice)" : "+ Add a battle"));
      };
      drawBattles();
      commitPending = () => panels.forEach(p => p._commit());
      pane.append(h("div", { class: "panel" }, h("h3", {}, "Event"), order(c.events, e, "this event"),
          h("div", { class: "row" }, field("Name", txt(e, "name", "Event name")), field("Counts for finishing the chapter", required)),
          field("Location disc", imageInput(e.coin, v => { e.coin = v; render(); }, ["discs", "portraits"], "first speaker's portrait")),
          h("label", { style: "display:flex;gap:6px;align-items:center" }, hidden, "Hidden from the map"),
          h("h3", {}, "Appears when…"), requiresEditor(e.requires, v => { e.requires = v; }, "No requirement: it is on the map from the start of the chapter.")),
        h("div", { class: "panel" }, h("h3", {}, "Place on the map"), mapView(c, e)),
        linesEditor(e.intro || [], v => { e.intro = v.length ? v : undefined; }, "Intro dialogue"),
        h("div", { class: "panel" }, h("h3", {}, "Battle"), battles),
        linesEditor(e.ending || [], v => { e.ending = v.length ? v : undefined; }, "Ending dialogue (after the battle is won)"),
        h("div", { class: "panel" }, h("h3", {}, "Rewards (once, when the event is completed)"), rewardsEditor(e.rewards, v => { e.rewards = v && v.length ? v : undefined; }),
          h("details", { open: !!e.master_rewards }, h("summary", {}, "Different rewards on Master (optional; otherwise the same)"),
            rewardsEditor(e.master_rewards, v => { e.master_rewards = v && v.length ? v : undefined; }))));
    }
  }
  // Commit battle forms before saving.

  render();
}

VIEWS.music = async main => {
  const d = state.detail;
  const label = Object.fromEntries(d.music_contexts.map(c => [c.context, c.label]));
  main.append(h("h1", {}, "Music"), h("p", { class: "sub" }, "Soundtracks for the game's menus, moments and boards. Pick where each track plays. \"Replace\" plays your track(s) instead of the game's music there; \"Rotation\" mixes the game's music in. A board track wins over a moment track during a match on that board. The game's music volume and mute apply."));
  const list = h("div", { class: "panel" });
  for (const t of d.music) list.append(h("div", { class: "row", style: "align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid var(--line)" },
    h("div", { style: "flex:1;min-width:0" }, h("b", {}, t.name), h("br"), h("small", { class: "sub" }, `${t.mode} · ${t.contexts.map(c => label[c] || c).join(", ")}`)),
    h("audio", { controls: true, preload: "none", src: t.audio_url, style: "height:32px;max-width:260px" }),
    h("button", { onclick: () => editDialog("track", t.slug, "Edit " + t.name, [["name", "Name", "text", t.name],
      ["mode", "Mode", "select", t.mode, [["replace", "Replace the game's music"], ["rotation", "Rotation with the game's music"]]],
      ["volume", "Volume (0-1)", "number", t.volume ?? 1], ["contexts", "Plays at", "contexts", t.contexts, d.music_contexts],
      ["file", "New audio file", "file", null, "audio/*"]]) }, "Edit"),
    h("button", { class: "danger", onclick: async () => {
      await act(() => api(`/api/mods/${state.mod}/music/${t.slug}`, { method: "DELETE" }), "Track removed"); refresh(); } }, "Remove")));
  if (!d.music.length) list.append(h("p", { class: "sub" }, "No tracks yet."));
  main.append(list, h("h2", {}, "New track"));
  const name = h("input", { placeholder: "Track name" });
  const mode = h("select", {}, h("option", { value: "replace" }, "Replace the game's music"), h("option", { value: "rotation" }, "Rotation (mixed with the game's)"));
  const volume = h("input", { type: "range", min: 0.1, max: 1, step: 0.05, value: 1 });
  const picks = new Set();
  const groups = {};
  for (const c of d.music_contexts) (groups[c.group] = groups[c.group] || []).push(c);
  const where = h("div", {});
  for (const [g, cs] of Object.entries(groups)) where.append(h("label", { style: "display:block;margin-top:8px" }, g),
    h("div", { style: "display:flex;flex-wrap:wrap;gap:4px 14px" }, cs.map(c => {
      const box = h("input", { type: "checkbox", onchange: () => box.checked ? picks.add(c.context) : picks.delete(c.context) });
      return h("label", { style: "font-weight:normal;display:flex;gap:4px;align-items:center" }, box, c.label);
    })));
  let file = null;
  const prev = h("div", {});
  main.append(h("div", { class: "split" }, h("div", { class: "panel" }, field("Name", name), h("div", { class: "row" }, field("Mode", mode), field("Volume", volume)),
    h("div", { class: "field" }, h("label", {}, "Audio (MP3, OGG, WAV, FLAC, M4A…; stored as OGG)"),
      dropZone("Drop an audio file or click", "audio/*", (p, s) => { file = p; prev.innerHTML = ""; prev.append(h("audio", { controls: true, src: s, style: "width:100%" }));
        if (!name.value) name.value = p.split(/[\\/]/).pop().replace(/\.[^.]+$/, "").replace(/[-_]+/g, " "); })),
    h("div", { class: "field" }, h("label", {}, "Where it plays"), where),
    h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
      if (!file) return toast("Choose an audio file first.", true);
      if (!picks.size) return toast("Pick at least one place for it to play.", true);
      await act(() => api(`/api/mods/${state.mod}/music`, { method: "POST", body: { name: name.value, file, contexts: [...picks], mode: mode.value, volume: volume.value } }), "Track added");
      refresh(); } }, "Add track"))), h("div", {}, h("label", {}, "Preview"), prev)));
};

VIEWS.remaster = async main => {
  const d = state.detail;
  main.append(h("h1", {}, "Remaster art"), h("p", { class: "sub" }, "Replace original card art with your own, at any resolution. The game shows it at the original size; turning the mod off restores the original."));
  const grid = h("div", { class: "grid" });
  for (const r of d.replacements) grid.append(h("div", { class: "tile" }, h("img", { src: r.image_url }),
    h("div", { class: "cap" }, h("b", {}, r.asset.split("/").pop()), h("small", {}, `${r.width}×${r.height} (original ${r.original.width}×${r.original.height})`)),
    h("button", { class: "danger", style: "margin:0 10px 10px", onclick: async () => {
      await act(() => api(`/api/mods/${state.mod}/replace?asset=${encodeURIComponent(r.asset)}`, { method: "DELETE" }), "Original restored"); refresh(); } }, "Restore original")));
  if (!d.replacements.length) grid.append(h("p", { class: "sub" }, "Nothing replaced yet."));
  main.append(grid, h("h2", {}, "Replace a card's art"));
  let card = null, img = null;
  const orig = h("img", {}), mine = h("img", {}), title = h("b", {}, "Pick a card →");
  const fit = h("select", {}, h("option", { value: "crop" }, "Crop to the original's shape"), h("option", { value: "stretch" }, "Stretch to fit"));
  main.append(h("div", { class: "split" },
    h("div", { class: "panel" }, title, h("div", { class: "compare", style: "margin:12px 0" }, h("figure", {}, orig, h("figcaption", {}, "Original")), h("figure", {}, mine, h("figcaption", {}, "Yours"))),
      dropZone("Drop your remastered image", "image/*", (p, s) => { img = p; mine.src = s; }), field("Fit", fit),
      h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
        if (!card || !img) return toast("Pick a card and an image.", true);
        await act(() => api(`/api/mods/${state.mod}/replace`, { method: "POST", body: { card: String(card.id), image: img, fit: fit.value } }), "Art replaced");
        refresh(); } }, "Replace"))),
    h("div", { class: "panel" }, cardPicker(c => { card = c; title.textContent = c.name; orig.src = artUrl(c, "full"); }, { all: true }))));
  // any other image the game loads by name: avatars, portraits, deck and story art, lane icons, interface art
  main.append(h("h2", {}, "Replace any other image"));
  let asset = null, img2 = null;
  const orig2 = h("img", {}), mine2 = h("img", {}), title2 = h("b", {}, "Pick an image →");
  const fit2 = h("select", {}, h("option", { value: "crop" }, "Crop to the original's shape"), h("option", { value: "stretch" }, "Stretch to fit"));
  const q = h("input", { placeholder: "Search, e.g. orc avatar, altar of silence, quest banner" });
  const cat = h("select", {}, h("option", { value: "" }, "All kinds"), ["avatar", "ai-portrait", "deck-art", "story", "quest", "lane", "interface"].map(c => h("option", { value: c }, c.replace("-", " "))));
  const list = h("div", { style: "max-height:520px;overflow:auto;margin-top:8px" });
  let tok = 0;
  const find = async () => {
    const mineTok = ++tok;
    const r = await api(`/api/catalog?q=${encodeURIComponent(q.value)}&category=${cat.value}&kind=texture&changeable=1&limit=80`);
    if (mineTok !== tok) return;
    list.innerHTML = "";
    for (const a of r.assets.filter(a => a.change === "remaster" && a.category !== "card-art"))
      list.append(h("div", { class: "row", style: "align-items:center;gap:8px;padding:4px;cursor:pointer;border-bottom:1px solid var(--line)", onclick: () => {
        asset = a.path; title2.textContent = a.label; orig2.src = `/api/assets/preview?path=${encodeURIComponent(a.path)}`; } },
        h("img", { src: `/api/assets/preview?path=${encodeURIComponent(a.path)}`, loading: "lazy", style: "width:48px;height:48px;object-fit:contain" }),
        h("div", { style: "min-width:0" }, h("b", {}, a.label), h("br"), h("small", { class: "sub" }, a.category_label))));
  };
  let t2;
  q.oninput = () => { clearTimeout(t2); t2 = setTimeout(find, 300); };
  cat.onchange = find;
  main.append(h("div", { class: "split" },
    h("div", { class: "panel" }, title2, h("div", { class: "compare", style: "margin:12px 0" }, h("figure", {}, orig2, h("figcaption", {}, "Original")), h("figure", {}, mine2, h("figcaption", {}, "Yours"))),
      dropZone("Drop your image", "image/*", (p, s) => { img2 = p; mine2.src = s; }), field("Fit", fit2),
      h("div", { class: "toolbar" }, h("span", { class: "grow" }), h("button", { class: "primary", onclick: async () => {
        if (!asset || !img2) return toast("Pick an image to replace and drop yours.", true);
        await act(() => api(`/api/mods/${state.mod}/replace`, { method: "POST", body: { asset, image: img2, fit: fit2.value } }), "Image replaced");
        refresh(); } }, "Replace"))),
    h("div", { class: "panel" }, h("div", { class: "toolbar" }, h("div", { class: "grow" }, q), cat), list)));
  find();
};

// ---- Load order & compatibility (all mods) ------------------------------------------------------------------------------
VIEWS.search = async main => {
  main.append(h("h1", {}, "Search all mods"), h("p", { class: "sub" }, "Find anything in any mod: cards, decks, avatars, AI opponents, card backs, boards, music, sounds, game modes, stories and replaced game images. For a replaced image it says which enabled mod's version the game shows (the later one in the load order)."));
  const q = h("input", { type: "search", placeholder: "e.g. Draugr, Skyrim, Avatars/…", style: "width:100%", value: state.searchQuery || "" });
  const out = h("div", {});
  let timer = null;
  const run = async () => {
    state.searchQuery = q.value;
    out.innerHTML = "";
    if (q.value.trim().length < 2) return;
    const r = await api(`/api/search?q=${encodeURIComponent(q.value)}`).catch(e => ({ error: e.message, results: [] }));
    if (r.error) return out.append(h("div", { class: "msg error" }, r.error));
    out.append(h("p", { class: "sub" }, `${r.total} found${r.total > r.results.length ? `, first ${r.results.length} shown` : ""}`));
    for (const x of r.results) out.append(h("div", { class: "row", style: "align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--line);cursor:pointer", onclick: () => go(x.mod, x.view) },
      h("span", { class: "badge", style: "min-width:120px;text-align:center" }, x.kind), h("b", { style: "flex:1;min-width:0;overflow-wrap:anywhere" }, x.name),
      x.note ? h("small", { class: "sub" }, x.note) : null, h("small", { class: "sub" }, (state.mods.find(m => m.id === x.mod) || {}).name || x.mod, x.enabled ? "" : " (off)")));
    if (!r.results.length) out.append(h("p", { class: "sub" }, "Nothing found."));
  };
  q.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 300); };
  main.append(q, out);
  q.focus();
  run();
};

VIEWS.loadorder = async main => {
  main.append(h("h1", {}, "Load order & compatibility"), h("p", { class: "sub" }, "Enabled mods load from top to bottom. Where two mods change the same thing (an image, a sound, a board, the music of a moment) the lower one wins. The game skips a mod that is missing a dependency, conflicts with a mod above it, or needs a newer TESL: Everlasting - and keeps running. Changes apply at the game's next start."));
  const body = h("div", {});
  main.append(body);
  const CLASS = { local: ["Local only", "Only you see or hear it (remastered art, music, sounds, board skins): fine in multiplayer."],
    cosmetic: ["Cosmetic", "Others would see it (avatars, card backs, emotes): multiplayer needs everyone to have it."],
    gameplay: ["Gameplay", "Changes play (cards, decks, rules, modes, stories): multiplayer only on servers where everyone has the same mods."] };
  const draw = async () => {
    body.innerHTML = "";
    const [rep, all] = await Promise.all([api("/api/compat"), api("/api/mods")]);
    const installed = all.mods || all;
    const enabled = rep.requested;
    const list = h("div", { class: "panel" }, h("h3", {}, "Enabled, in load order"));
    const save = async order => { await act(() => api("/api/compat/order", { method: "POST", body: { order } }), "Load order saved"); draw(); };
    if (!enabled.length) list.append(h("p", { class: "sub" }, "No mods enabled."));
    enabled.forEach((id, i) => {
      const info = rep.mods.find(m => m.id === id);
      const skipped = !rep.order.includes(id);
      const meta = installed.find(m => m.id === id) || {};
      const cls = info ? CLASS[info.class] : null;
      list.append(h("div", { class: "row", style: `grid-template-columns:32px 1fr auto auto auto auto;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);${skipped ? "opacity:.6" : ""}` },
        h("b", {}, String(i + 1)),
        h("div", {}, h("b", {}, meta.name || id), h("small", { class: "sub" }, `  ${id}  v${(info || meta).version || "?"}`), h("br"),
          skipped ? h("small", { style: "color:var(--red)" }, "Skipped by the game - see below") :
          h("small", { class: "sub", title: cls ? cls[1] : "" }, `${cls ? cls[0] : ""} · engine ${info.requires_engine} · ${info.features.join(", ")} · ${info.fingerprint}`)),
        h("button", { disabled: i === 0, onclick: () => { const o = [...enabled]; [o[i - 1], o[i]] = [o[i], o[i - 1]]; save(o); } }, "↑"),
        h("button", { disabled: i === enabled.length - 1, onclick: () => { const o = [...enabled]; [o[i + 1], o[i]] = [o[i], o[i + 1]]; save(o); } }, "↓"),
        h("button", { onclick: () => save(enabled.filter(x => x !== id)) }, "Disable"),
        h("a", { class: "button", href: `/api/mods/${encodeURIComponent(id)}/export.zip`, download: `${id}.zip`, style: "padding:6px 10px;border:1px solid var(--line);border-radius:8px" }, "Export"),
        h("button", { onclick: () => go(id, "overview") }, "Open")));
    });
    list.append(h("div", { class: "toolbar" }, h("button", { onclick: async () => { await act(() => api("/api/compat/order", { method: "POST", body: { auto: true } }), "Sorted"); draw(); } }, "Sort by dependencies"),
      h("span", { class: "grow" }), h("small", { class: "sub" }, `TESL: Everlasting level ${rep.engine_level}`)));
    const off = installed.filter(m => !enabled.includes(m.id));
    const offPanel = h("div", { class: "panel", style: "margin-top:12px" }, h("h3", {}, "Installed, not enabled"));
    if (!off.length) offPanel.append(h("p", { class: "sub" }, "None."));
    for (const m of off) offPanel.append(h("div", { class: "row", style: "grid-template-columns:1fr auto;align-items:center;padding:4px 0" },
      h("div", {}, h("b", {}, m.name || m.id), h("small", { class: "sub" }, "  " + m.id)),
      h("div", { style: "display:flex;gap:6px" },
      h("button", { onclick: async () => { if (!confirm(`Uninstall ${m.id}? It is moved to the suite's trash folder.`)) return; await act(() => api(`/api/mods/${m.id}/uninstall`, { method: "POST", body: {} }), "Uninstalled"); draw(); } }, "Uninstall"),
      h("button", { onclick: async () => {
        try { await api(`/api/mods/${m.id}/enable`, { method: "POST", body: {} }); toast("Enabled " + m.id); }
        catch (e) { if (confirm(e.message + "\n\nEnable anyway? The game will skip what cannot load.")) await act(() => api(`/api/mods/${m.id}/enable`, { method: "POST", body: { force: true } }), "Enabled"); }
        draw(); } }, "Enable"))));
    const issues = rep.problems.concat(rep.overlaps);
    const issuesPanel = h("div", { class: "panel", style: "margin-top:12px" }, h("h3", {}, issues.length ? "What the game will do" : "No problems or overlaps"));
    const colour = { error: "var(--red)", warning: "var(--warn)", info: "var(--muted)" };
    for (const x of issues) issuesPanel.append(h("div", { style: `padding:4px 0;color:${colour[x.severity] || "inherit"}` },
      h("b", {}, x.severity === "error" ? "Problem: " : x.severity === "warning" ? "Note: " : "Overlap: "), x.text));
    const link = h("input", { placeholder: "https://... link to a mod .zip" });
    const installBox = h("div", { class: "panel", style: "margin-top:12px" }, h("h3", {}, "Install a mod"),
      h("p", { class: "sub" }, "A mod .zip from another modder (made with Export). Only content files are accepted; an older installed version is kept as a backup."),
      dropZone("Drop a mod .zip here or click to choose", ".zip", async path => {
        const r = await act(() => api("/api/mods/install", { method: "POST", body: { source: path } }).catch(async e => {
          if (/already installed/.test(e.message) && confirm(e.message + "\n\nReplace it?")) return api("/api/mods/install", { method: "POST", body: { source: path, force: true } });
          throw e; }), "Installed");
        if (r && r.compatibility && r.compatibility.length) toast("Note: " + r.compatibility.join("; "), true);
        draw(); }),
      h("div", { class: "row", style: "grid-template-columns:1fr auto;margin-top:8px" }, link,
        h("button", { onclick: async () => { if (!link.value) return; await act(() => api("/api/mods/install", { method: "POST", body: { source: link.value } }), "Installed"); draw(); } }, "Install from link")));
    body.append(list, issuesPanel, installBox, offPanel);
  };
  await draw();
};

VIEWS.library = async main => {
  main.append(h("h1", {}, "Card library"), h("p", { class: "sub" }, "Every card in the game's data. Art is exported from the game files the first time you see it."));
  const q = h("input", { placeholder: "Search name, text or id" }), set = h("select", {}, h("option", { value: "" }, "All sets"));
  const type = h("select", {}, ["", "Creature", "Action", "Item", "Support"].map(t => h("option", { value: t }, t || "All types")));
  const attr = h("select", {}, h("option", { value: "" }, "All attributes"), ATTRS.map(a => h("option", { value: a }, a)));
  const cost = h("select", {}, h("option", { value: "" }, "Any cost"), [0, 1, 2, 3, 4, 5, 6, 7].map(n => h("option", { value: n }, n === 7 ? "7+" : n)));
  const coll = h("input", { type: "checkbox", checked: true });
  const grid = h("div", { class: "grid" }), more = h("button", {}, "Load more"), count = h("span", { class: "sub" });
  let offset = 0;
  const load = async reset => {
    if (reset) { offset = 0; grid.innerHTML = ""; }
    const params = new URLSearchParams({ q: q.value, set: set.value, type: type.value, attribute: attr.value, cost: cost.value, collectible: coll.checked ? 1 : 0, limit: 60, offset });
    const res = await api("/api/cards?" + params);
    if (set.options.length === 1) res.sets.forEach(s => set.append(h("option", { value: s }, s)));
    for (const c of res.cards) grid.append(h("div", { class: "tile", title: (c.text || "").replace(/<[^>]+>/g, "") }, h("img", { src: artUrl(c), loading: "lazy" }), h("div", { class: "cost" }, c.cost ?? ""),
      h("div", { class: "cap" }, h("b", {}, c.name), h("small", {}, dots(c), ` ${c.type}${c.type === "Creature" ? ` ${c.attack}/${c.health}` : ""} · ${c.id}`))));
    offset += res.cards.length;
    count.textContent = `${res.total} cards`;
    more.classList.toggle("hidden", offset >= res.total);
  };
  let timer;
  [q].forEach(i => i.oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(true), 250); });
  [set, type, attr, cost, coll].forEach(i => i.onchange = () => load(true));
  more.onclick = () => load(false);
  main.append(h("div", { class: "toolbar" }, h("div", { class: "grow" }, q), set, type, attr, cost, h("label", { class: "switch" }, coll, h("span", { class: "knob" }), h("span", {}, "Collectible only")), count), grid, h("div", { class: "toolbar" }, more));
  load(true);
};

const CHANGE_HOW = { remaster: "Replace with Remaster art (in a mod)", sounds: "Replace on Sounds & voices (in a mod)", cardback: "Add new card backs on Card backs",
  board: "Board editor (coming)", music: "Add tracks on Music (in a mod)" };
VIEWS.assets = async main => {
  main.append(h("h1", {}, "Asset browser"), h("p", { class: "sub" }, "Everything in the game's files, labelled: what each asset is, what it belongs to, and how a mod can change it. Pick a category or search by name (a card, an avatar, a board object...)."));
  await audioSupportBar(main);
  const q = h("input", { placeholder: "Search by name, e.g. brynjolf, elsweyr board, altar, sheogorath" });
  const cat = h("select", {}, h("option", { value: "" }, "All categories"));
  const kind = h("select", {}, h("option", { value: "" }, "Any type"), ["texture", "audio", "model", "material", "animation", "prefab", "shader", "font", "text", "other"].map(k => h("option", { value: k }, k)));
  const lang = h("select", { title: "Voice lines and other localized assets come in one copy per language" }, h("option", { value: "" }, "Any language"), h("option", { value: "none" }, "No language (shared)"));
  const onlyChange = h("input", { type: "checkbox" });
  const grid = h("div", { class: "grid" }), count = h("span", { class: "sub" });
  let offset = 0, token = 0;
  const more = h("button", { style: "margin:14px auto;display:none", onclick: () => load(true) }, "Show more");
  const tile = a => h("div", { class: "tile", title: a.path },
    a.kind === "texture" ? h("img", { src: `/api/assets/preview?path=${encodeURIComponent(a.path)}`, loading: "lazy" })
      : a.kind === "audio" ? h("div", { style: "padding:18px;text-align:center" }, h("button", { onclick: () => playUrl(`/api/sounds/preview?path=${encodeURIComponent(a.path)}`) }, "▶ Play"))
      : h("div", { class: "sub", style: "padding:18px;text-align:center;font-size:0.857rem" }, a.kind),
    h("div", { class: "cap" }, h("b", {}, a.label), h("small", { style: "display:block" }, a.category_label),
      a.change ? h("small", { style: "display:block;color:var(--accent)" }, CHANGE_HOW[a.change] || a.change) : null,
      h("small", { style: "display:block;word-break:break-all;opacity:.6" }, a.path.replace(/^Assets\//, ""))));
  const load = async (append = false) => {
    const mine = ++token;
    if (!append) offset = 0;
    const res = await api(`/api/catalog?q=${encodeURIComponent(q.value)}&category=${cat.value}&kind=${kind.value}&language=${lang.value}&changeable=${onlyChange.checked ? 1 : 0}&limit=120&offset=${offset}`);
    if (mine !== token) return;
    if (cat.options.length === 1) for (const c of res.categories) if (c.count) cat.append(h("option", { value: c.id }, `${c.label} (${c.count})`));
    if (lang.options.length === 2) for (const l of res.languages || []) lang.append(h("option", { value: l.id }, l.label));
    if (!append) grid.innerHTML = "";
    for (const a of res.assets) grid.append(tile(a));
    if (!append && !res.assets.length) grid.append(h("p", { class: "sub" }, q.value ? `Nothing matches "${q.value}" with these filters. Try another word, or set the category, type and language back to "All" / "Any".` : "Nothing matches these filters."));
    offset += res.assets.length;
    count.textContent = `${res.total} assets` + (res.total > offset ? `, showing ${offset}` : "");
    more.style.display = res.total > offset ? "block" : "none";
  };
  let timer;
  q.oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(), 300); };
  cat.onchange = kind.onchange = lang.onchange = onlyChange.onchange = () => load();
  main.append(h("div", { class: "toolbar" }, h("div", { class: "grow" }, q), cat, kind, lang, h("label", { style: "display:flex;gap:5px;align-items:center;white-space:nowrap" }, onlyChange, "Changeable by mods"), count), grid, more);
  cat.value = ""; q.value = ""; load();
};

boot().catch(e => { $("#main").innerHTML = ""; $("#main").append(h("div", { class: "msg error" }, "Could not reach the suite: " + e.message)); });
