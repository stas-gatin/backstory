const $ = (s) => document.querySelector(s);
let chosenFile = null, chosenExample = null;

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Line icons, 24x24, drawn with the current text colour.
const PATHS = {
  cutout: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
  match: '<rect x="3" y="3" width="12" height="12" rx="2"/><rect x="9" y="9" width="12" height="12" rx="2"/>',
  frames: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  speech: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  claim: '<path d="M4 6h16M4 12h12M4 18h8"/>',
  search: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/>',
  reader: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  rule: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  judge: '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>',
  critic: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  back: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
  inconsistent: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  consistent: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  cannot_tell: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.2M12 17h.01"/>',
  link: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
};
const icon = (name, cls = "ic") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name]}</svg>`;

const TAG = { claim: "Caption", evidence: "Archive", described: "Page says" };
const LABEL = { inconsistent: "Does not fit", consistent: "Fits", cannot_tell: "Cannot verify" };
const BASIS = {
  "date rule": "Decided by the date rule: an archived copy predates the claim",
  "judge, approved by critic": "Decided by the judge, approved by the critic",
  "judge and critic disagree": "The judge and the critic did not agree, so no verdict is given",
  "no evidence": "No earlier copy of the photo was found",
};

document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });

async function init() {
  const st = await fetch("/api/status").then((r) => r.json());
  $("#mode").innerHTML = st.mode === "replay"
    ? '<i class="live off"></i>Replay · recorded answers' : '<i class="live"></i>Live';
  const ex = await fetch("/api/examples").then((r) => r.json());
  $("#examplesWrap").hidden = !ex.length;
  $("#examples").innerHTML = ex.map((e) => `
    <button type="button" class="ex" data-id="${esc(e.id)}">
      <img src="/api/examples/${encodeURIComponent(e.id)}/image" alt="">
      <div><b>${esc(e.title)}</b><span>${esc(e.caption)}</span></div>
    </button>`).join("");
  document.querySelectorAll(".ex").forEach((b) => b.addEventListener("click", () => pickExample(ex.find((e) => e.id === b.dataset.id))));
}

function pickExample(e) {
  chosenExample = e; chosenFile = null;
  document.querySelectorAll(".ex").forEach((b) => b.classList.toggle("on", b.dataset.id === e.id));
  if (e.kind === "video") showVideo(`/api/examples/${encodeURIComponent(e.id)}/video`);
  else showPreview(`/api/examples/${encodeURIComponent(e.id)}/image`);
  $("#caption").value = e.caption;
  $("#posted").value = /^\d{4}-\d\d-\d\d$/.test(e.posted_on || "") ? e.posted_on : "";
}

function showPreview(src) {
  $("#preview").src = src; $("#preview").hidden = false; $("#dropText").hidden = true;
  $("#previewVideo").hidden = true; $("#previewVideo").removeAttribute("src");
}

function showVideo(src) {
  $("#previewVideo").src = src; $("#previewVideo").hidden = false; $("#dropText").hidden = true;
  $("#preview").hidden = true;
}

function pickFile(f) {
  if (!f) return;
  chosenFile = f; chosenExample = null;
  document.querySelectorAll(".ex").forEach((b) => b.classList.remove("on"));
  const url = URL.createObjectURL(f);
  if (f.type.startsWith("video/")) showVideo(url); else showPreview(url);
}

$("#file").addEventListener("change", (e) => pickFile(e.target.files[0]));
const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); pickFile(e.dataTransfer.files[0]); });
$("#caption").addEventListener("input", () => {
  if (chosenExample && $("#caption").value !== chosenExample.caption) {
    chosenExample = null;
    document.querySelectorAll(".ex").forEach((b) => b.classList.remove("on"));
  }
});

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData();
  if (chosenExample) fd.append("example_id", chosenExample.id);
  else {
    if (!chosenFile || !$("#caption").value.trim()) {
      $("#formError").textContent = "Choose a photo or video and enter the caption it was shared with.";
      return;
    }
    fd.append("image", chosenFile);
    fd.append("caption", $("#caption").value);
    fd.append("posted_on", $("#posted").value);
  }
  $("#formError").textContent = "";
  reset();
  $("#go").disabled = true;
  $("#go").textContent = "Checking…";
  try {
    const res = await fetch("/api/check", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) { handle(JSON.parse(buf.slice(0, i))); buf = buf.slice(i + 1); }
    }
  } catch (err) {
    handle({ type: "error", text: err.message });
  }
  $("#go").disabled = false;
  $("#go").textContent = "Check the caption";
});

let t0 = 0, timer = null;
function tick() { $("#elapsed").textContent = ((performance.now() - t0) / 1000).toFixed(0) + " s"; }
function reset() {
  clearInterval(timer);
  timer = setInterval(tick, 500);
  $("#steps").innerHTML = ""; $("#stepsCard").hidden = false; $("#emptyCard").hidden = true;
  $("#result").hidden = true; $("#evidenceCard").hidden = true;
  $("#evidence tbody").innerHTML = "";
  $("#elapsed").textContent = "";
  t0 = performance.now();
}

function handle(ev) {
  if (ev.type === "result" || ev.type === "error") { clearInterval(timer); tick(); }
  if (ev.type === "step") addStep(ev);
  else if (ev.type === "evidence") addEvidence(ev.row);
  else if (ev.type === "result") showResult(ev);
  else if (ev.type === "error") {
    const li = document.createElement("li"); li.className = "err";
    li.innerHTML = `<span class="dot">${icon("alert")}</span><div><div class="head"><span class="who">Stopped</span></div>
      <div class="what error">${esc(ev.text)}</div></div>`;
    $("#steps").appendChild(li);
  }
}

function addStep(ev) {
  // A finished step replaces its own "running" line; a second round of judge/critic gets a new line.
  const open = [...$("#steps").children].reverse().find((li) => li.dataset.agent === ev.agent && li.classList.contains("running"));
  const li = ev.status === "done" && open ? open : document.createElement("li");
  li.dataset.agent = ev.agent;
  const sent = ev.status === "done" && ev.approve === false;
  li.className = ev.status === "done" ? (sent ? "sent" : "done") : "running";
  const [name, by] = ev.label.split(" · ");
  const mark = ev.status === "done" ? (sent ? "back" : "check") : ev.agent;
  li.innerHTML = `<span class="dot">${icon(mark)}</span><div><div class="head"><span class="who">${esc(name)}</span>
    <span class="chip ${/Muse|SAM/.test(by || "") ? "" : "tool"}">${esc(by || "")}</span></div><div class="what">${esc(ev.text)}</div>
    ${(ev.thumbs || []).length ? `<div class="thumbs">${ev.thumbs.map((t) => `<img src="${t}" alt="">`).join("")}</div>` : ""}</div>`;
  if (!li.parentNode) $("#steps").appendChild(li);
}

const ext = (url, text) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(text)}</a>`;

function addEvidence(r) {
  $("#evidenceCard").hidden = false;
  let tr = document.getElementById("ev-" + r.id);
  if (!tr) {
    // Rows arrive as agents finish; keep them in evidence order (E1, E2, ...).
    tr = document.createElement("tr"); tr.id = "ev-" + r.id;
    const n = +r.id.slice(1);
    const next = [...$("#evidence tbody").children].find((x) => +x.id.slice(4) > n);
    $("#evidence tbody").insertBefore(tr, next || null);
  }
  const date = (d, url) => d ? (url ? ext(url, d) : esc(d)) : '<span class="nil">–</span>';
  const says = [r.described_place, r.described_date, r.described_event].filter(Boolean).join(" · ");
  const pub = r.page_published ? esc(String(r.page_published).slice(0, 10)) : '<span class="nil">–</span>';
  tr.innerHTML = `<td class="id">${esc(r.id)}</td>
    <td><div class="src">${icon("globe", "ic sm")}${ext(r.url, r.domain)}</div>${r.fact_checker ? '<span class="fc">Fact-check</span>' : ""}</td>
    <td class="mono">${date(r.image_first, r.image_snapshot)}</td>
    <td class="mono">${date(r.page_first, r.page_snapshot)}</td>
    <td class="mono">${pub}</td>
    <td>${says ? esc(says) : `<span class="nil">${r.opened === false ? "Page did not open" : "Not stated"}</span>`}
      ${r.quote ? `<div class="quote">“${esc(r.quote)}”</div>` : ""}</td>`;
}

function fact(label, parts) {
  const v = parts.filter(Boolean);
  return `<div class="fact"><div class="k">${label}</div><div class="v">${v.length ? v.map(esc).join("<br>") : '<span class="nil">Not stated</span>'}</div></div>`;
}

function showResult(r) {
  const box = $("#result");
  box.hidden = false;
  box.className = "card result " + r.verdict;
  const c = r.claim || {}, a = r.actual || {};
  const calls = Object.values(r.cost?.calls || {}).reduce((x, y) => x + y, 0);
  const img = !$("#preview").hidden ? `<img class="thumb" src="${esc($("#preview").src)}" alt="Checked photo">`
    : !$("#previewVideo").hidden ? `<video class="thumb" src="${esc($("#previewVideo").src)}" muted></video>` : "";
  const compare = r.verdict === "inconsistent" && (a.place || a.date || a.event)
    ? `<div class="compare">${fact("The caption says", [c.place, c.claimed_date, c.event])}
         <div class="vs">${icon("inconsistent")}</div>
         ${fact("The record says", [a.place, a.date, a.event])}</div>`
    : `<div class="compare single">${fact("The caption says", [c.place, c.claimed_date, c.event])}</div>`;
  box.innerHTML = `
    <div class="rhead">${img}<div>
      <span class="verdict">${icon(r.verdict)}${LABEL[r.verdict] || r.verdict}</span>
      <p class="summary">${esc(r.summary || "")}</p></div></div>
    ${compare}
    ${r.timeline.length ? `<h3>Timeline</h3><div class="timeline">${r.timeline.map((t) => `
      <div class="${t.kind}"><time>${esc(t.date)}</time><span class="tag">${TAG[t.kind]}</span><span>${t.url ? ext(t.url, t.text) : esc(t.text)}</span></div>`).join("")}</div>` : ""}
    <div class="basis">${esc(BASIS[r.basis] || r.basis)} · ${calls} model calls · $${(r.cost?.usd ?? 0).toFixed(3)}${r.mode === "replay" ? " · recorded run" : ""}</div>`;
  (r.cited || []).forEach((id) => document.getElementById("ev-" + id)?.classList.add("cited"));
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

init();
