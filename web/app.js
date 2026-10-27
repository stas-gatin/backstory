const $ = (s) => document.querySelector(s);
let chosenFile = null, chosenExample = null;

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LABEL = { inconsistent: "DOES NOT FIT", consistent: "FITS", cannot_tell: "CANNOT VERIFY" };

async function init() {
  const st = await fetch("/api/status").then((r) => r.json());
  $("#mode").textContent = st.mode === "replay" ? "replay mode · recorded answers, no keys" : "live mode";
  const ex = await fetch("/api/examples").then((r) => r.json());
  $("#examples").innerHTML = ex.map((e) => `
    <button type="button" class="ex" data-id="${esc(e.id)}">
      <img src="/api/examples/${encodeURIComponent(e.id)}/image" alt="">
      <div><b>${esc(e.title)}</b><span>${esc(e.caption)}</span></div>
    </button>`).join("");
  document.querySelectorAll(".ex").forEach((b) => b.addEventListener("click", () => pickExample(ex.find((e) => e.id === b.dataset.id))));
}

function pickExample(e) {
  chosenExample = e; chosenFile = null;
  showPreview(`/api/examples/${encodeURIComponent(e.id)}/image`);
  $("#caption").value = e.caption;
  $("#posted").value = e.posted_on || "";
}

function showPreview(src) {
  $("#preview").src = src; $("#preview").hidden = false; $("#dropText").hidden = true;
}

function pickFile(f) {
  if (!f) return;
  chosenFile = f; chosenExample = null;
  showPreview(URL.createObjectURL(f));
}

$("#file").addEventListener("change", (e) => pickFile(e.target.files[0]));
const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); pickFile(e.dataTransfer.files[0]); });
$("#caption").addEventListener("input", () => { if (chosenExample && $("#caption").value !== chosenExample.caption) chosenExample = null; });

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData();
  if (chosenExample) fd.append("example_id", chosenExample.id);
  else {
    if (!chosenFile || !$("#caption").value.trim()) { alert("Choose a photo and write its caption."); return; }
    fd.append("image", chosenFile);
    fd.append("caption", $("#caption").value);
    fd.append("posted_on", $("#posted").value);
  }
  reset();
  $("#go").disabled = true;
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
});

const rows = {};
function reset() {
  $("#steps").innerHTML = ""; $("#stepsCard").hidden = false;
  $("#result").hidden = true; $("#evidenceCard").hidden = true;
  $("#evidence tbody").innerHTML = "";
  for (const k in rows) delete rows[k];
}

function handle(ev) {
  if (ev.type === "step") addStep(ev);
  else if (ev.type === "evidence") addEvidence(ev.row);
  else if (ev.type === "result") showResult(ev);
  else if (ev.type === "error") {
    const li = document.createElement("li"); li.className = "err";
    li.innerHTML = `<i class="dot"></i><span class="who">Stopped</span><span class="what error">${esc(ev.text)}</span>`;
    $("#steps").appendChild(li);
  }
}

function addStep(ev) {
  // A finished step replaces its own "running" line; a second round of judge/critic gets a new line.
  const open = [...$("#steps").children].reverse().find((li) => li.dataset.agent === ev.agent && li.classList.contains("running"));
  const li = ev.status === "done" && open ? open : document.createElement("li");
  li.dataset.agent = ev.agent;
  li.className = ev.status === "done" ? (ev.approve === false ? "sent" : "done") : "running";
  li.innerHTML = `<i class="dot"></i><span class="who">${esc(ev.label)}</span><span class="what">${esc(ev.text)}</span>`;
  if (!li.parentNode) $("#steps").appendChild(li);
}

function addEvidence(r) {
  $("#evidenceCard").hidden = false;
  rows[r.id] = r;
  let tr = document.getElementById("ev-" + r.id);
  if (!tr) { tr = document.createElement("tr"); tr.id = "ev-" + r.id; $("#evidence tbody").appendChild(tr); }
  const link = (d, url) => d ? (url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(d)}</a>` : esc(d)) : "–";
  const says = [r.described_place, r.described_date, r.described_event].filter(Boolean).join(" · ");
  tr.innerHTML = `<td>${esc(r.id)}</td>
    <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.domain)}</a> ${r.fact_checker ? '<span class="fc">fact-check</span>' : ""}</td>
    <td class="mono">${link(r.image_first, r.image_snapshot)}</td>
    <td class="mono">${link(r.page_first, r.page_snapshot)}</td>
    <td class="mono">${esc((r.page_published || "–").slice(0, 10))}</td>
    <td>${esc(says || (r.opened === false ? "page did not open" : "–"))}${r.quote ? `<br><i>“${esc(r.quote)}”</i>` : ""}</td>`;
}

function showResult(r) {
  const box = $("#result");
  box.hidden = false;
  box.className = "card result " + r.verdict;
  const actual = r.actual && [r.actual.place, r.actual.date, r.actual.event].filter(Boolean).join(" · ");
  box.innerHTML = `
    <span class="verdict">${LABEL[r.verdict] || r.verdict}</span>
    <p class="summary">${esc(r.summary || "")}</p>
    ${actual && r.verdict === "inconsistent" ? `<p><b>What the record says instead:</b> ${esc(actual)}</p>` : ""}
    <div class="basis">Decided by: ${esc(r.basis)} · cost $${(r.cost?.usd ?? 0).toFixed(3)}${r.mode === "replay" ? " (recorded)" : ""}</div>
    ${r.timeline.length ? `<div class="timeline">${r.timeline.map((t) => `
      <div class="${t.kind}"><time>${esc(t.date)}</time>${t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.text)}</a>` : esc(t.text)}</div>`).join("")}</div>` : ""}`;
  (r.cited || []).forEach((id) => document.getElementById("ev-" + id)?.classList.add("cited"));
}

init();
