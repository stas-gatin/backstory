const $ = (s) => document.querySelector(s);
let chosenFile = null, chosenExample = null, running = false, finished = false, tab = "link";

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Line icons, 24x24, drawn with the current text colour.
const PATHS = {
  post: '<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/>',
  cutout: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
  match: '<rect x="3" y="3" width="12" height="12" rx="2"/><rect x="9" y="9" width="12" height="12" rx="2"/>',
  frames: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  speech: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  claim: '<path d="M4 6h16M4 12h12M4 18h8"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/>',
  reader: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  rule: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  judge: '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>',
  witness: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  grounds: '<path d="M9 4h6v3H9z"/><path d="M15 5h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h3"/><path d="m9 14 2 2 4-4"/>',
  critic: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  back: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
  inconsistent: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  consistent: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  cannot_tell: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.2M12 17h.01"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
};
const icon = (name, cls = "ic") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name] || PATHS.check}</svg>`;
document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });

// The agents, in the order they work. "by" names the model or tool; Meta models are highlighted.
const STAGES = [
  { title: "Read the post", agents: [
    ["post", "Post reader", "X post data"], ["frames", "Frame grabber", "ffmpeg"],
    ["speech", "Speech reader", "Muse Voice Transcribe"], ["claim", "Claim reader", "Muse Spark + web search"],
    ["cutout", "Photo finder", "SAM 3.1"], ["witness", "Scene witness", "Muse Spark + Muse Wonder"]] },
  { title: "Find its past", agents: [
    ["search", "Image search", "Google Vision"], ["clock", "Post clock", "code"],
    ["match", "Match checker", "Muse Spark"], ["archive", "Archivist", "Internet Archive"],
    ["reader", "Page reader", "Muse Spark"]] },
  { title: "Decide", agents: [
    ["rule", "Date rule", "code"], ["judge", "Judge", "Muse Spark"], ["critic", "Critic", "Muse Wonder"]] },
  { title: "Check the proof", agents: [["grounds", "Proof check", "code"]] },
];
const IS_META = (by) => /Muse|SAM/.test(by || "");
const MODEL_NAMES = { "muse-spark-1.3": "Muse Spark", "muse-wonder-1.0": "Muse Wonder", "muse-voice-transcribe-1.0": "Muse Voice Transcribe", "sam-3.1": "SAM 3.1" };
const LABEL = { inconsistent: "Does not fit", consistent: "Fits", cannot_tell: "Cannot verify" };
const BASIS = {
  "date rule": "Decided by the date rule (code): an archived copy predates the claim",
  "judge, approved by critic": "Decided by the judge, approved by the critic",
  "judge and critic disagree": "The judge and the critic did not agree, so no verdict is given",
  "no evidence": "No earlier copy of the photo was found",
  "proof too weak": "The judge leaned to \"does not fit\", but the proof check found too little proof",
};
const TAG = { claim: "Caption claims", evidence: "Copy online", described: "A page says" };

function drawMap() {
  $("#stages").innerHTML = STAGES.map((s, i) => `<div class="stage"><h4><i>${i + 1}</i>${esc(s.title)}</h4>
    ${s.agents.map(([id, name, by]) => `<div class="node ${IS_META(by) ? "meta" : ""}" id="node-${id}" title="">
      <span class="nd">${icon(id)}</span><div><b>${esc(name)}</b><small>${esc(by)}</small></div></div>`).join("")}</div>`).join("");
}

async function init() {
  drawMap();
  const st = await fetch("/api/status").then((r) => r.json()).catch(() => ({}));
  $("#mode").innerHTML = st.mode === "replay"
    ? '<i class="live off"></i>Replay · recorded runs' : '<i class="live"></i>Live';
  const ex = await fetch("/api/examples").then((r) => r.json()).catch(() => []);
  $("#examplesWrap").hidden = !ex.length;
  const KIND = { link: "X post", video: "Video", photo: "Photo" };
  $("#examples").innerHTML = ex.map((e) => `
    <button type="button" class="ex" data-id="${esc(e.id)}">
      <img src="/api/examples/${encodeURIComponent(e.id)}/image" alt="" loading="lazy">
      <div class="exbody"><span class="kind">${KIND[e.kind || "photo"] || "Photo"}</span><b>${esc(e.title)}</b><span>${esc(e.blurb || e.caption)}</span></div>
    </button>`).join("");
  document.querySelectorAll(".ex").forEach((b) => b.addEventListener("click", () => {
    if (running) return;
    chosenExample = ex.find((e) => e.id === b.dataset.id);
    document.querySelectorAll(".ex").forEach((x) => x.classList.toggle("on", x === b));
    $("#form").requestSubmit();
  }));
}

function setTab(name) {
  tab = name;
  document.querySelectorAll(".tabbtn").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll(".pane").forEach((p) => { p.hidden = p.dataset.pane !== name; });
}
document.querySelectorAll(".tabbtn").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

function pickFile(f) {
  if (!f || running) return;
  chosenFile = f; chosenExample = null;
  document.querySelectorAll(".ex").forEach((b) => b.classList.remove("on"));
  const url = URL.createObjectURL(f);
  $("#drop").querySelector("img, video")?.remove();
  const el = document.createElement(f.type.startsWith("video/") ? "video" : "img");
  el.src = url; if (el.tagName === "VIDEO") { el.muted = true; el.controls = true; }
  $("#dropText").hidden = true; $("#drop").appendChild(el);
}
$("#file").addEventListener("change", (e) => pickFile(e.target.files[0]));
const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); pickFile(e.dataTransfer.files[0]); });
$("#postUrl").addEventListener("input", () => { chosenExample = null; document.querySelectorAll(".ex").forEach((b) => b.classList.remove("on")); });

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (running) return;
  const fd = new FormData();
  let post = null;
  if (chosenExample) {
    fd.append("example_id", chosenExample.id);
    post = { media: chosenExample.kind === "video" ? `/api/examples/${encodeURIComponent(chosenExample.id)}/video` : `/api/examples/${encodeURIComponent(chosenExample.id)}/image`,
             video: chosenExample.kind === "video", text: chosenExample.kind === "link" ? "" : chosenExample.caption,
             meta: chosenExample.kind === "link" ? chosenExample.post_url : (chosenExample.posted_on ? "Posted " + chosenExample.posted_on : "") };
  } else if (tab === "link") {
    const link = $("#postUrl").value.trim();
    if (!/^https?:\/\/(www\.|mobile\.)?(x|twitter)\.com\/[^/]+\/status\/\d+/.test(link)) {
      $("#formError").textContent = "Paste a link to a post on X (x.com/user/status/…), or pick a case above.";
      return;
    }
    fd.append("post_url", link);
    post = { media: null, text: "", meta: link };
  } else {
    if (!chosenFile || !$("#caption").value.trim()) {
      $("#formError").textContent = "Choose a photo or video and enter the caption it was shared with.";
      return;
    }
    fd.append("image", chosenFile);
    fd.append("caption", $("#caption").value);
    fd.append("posted_on", $("#posted").value);
    post = { media: URL.createObjectURL(chosenFile), video: chosenFile.type.startsWith("video/"), text: $("#caption").value,
             meta: $("#posted").value ? "Posted " + $("#posted").value : "" };
  }
  $("#formError").textContent = "";
  reset(post);
  setRunning(true);
  try {
    const res = await fetch("/api/check", { method: "POST", body: fd });
    if (!res.ok) throw new Error(await errorText(res));
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) { handle(JSON.parse(buf.slice(0, i))); buf = buf.slice(i + 1); }
    }
    if (!finished) handle({ type: "error", text: "The connection closed before the check finished. Please try again." });
  } catch (err) {
    handle({ type: "error", text: err.message });
  }
  clearInterval(timer);
  setRunning(false);
});

function setRunning(on) {
  running = on;
  $("#go").disabled = on;
  $("#go").textContent = on ? "Agents at work…" : "Check the caption";
  $("#inputCard").classList.toggle("busy", on);
}

async function errorText(res) {
  try {
    const j = await res.json();
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((d) => d.msg || "").join("; ");
  } catch (e) { /* not JSON, e.g. a proxy's error page */ }
  return `The server answered ${res.status} ${res.statusText}`.trim();
}

let t0 = 0, timer = null, modelCalls = 0;
let G = {};  // what the check graph needs, collected from the agents' messages
function tick() { $("#elapsed").textContent = ((performance.now() - t0) / 1000).toFixed(0) + " s"; }

function showPost(p) {
  $("#postCard").hidden = false;
  $("#media").innerHTML = p.media ? (p.video ? `<video src="${esc(p.media)}" controls muted playsinline></video>` : `<img src="${esc(p.media)}" alt="The checked photo">`) : "";
  $("#postMeta").innerHTML = p.meta ? esc(p.meta) : "";
  $("#postText").textContent = p.text || "";
}

function reset(post) {
  finished = false; modelCalls = 0;
  G = { post: post, inputs: [], rows: {}, judge: 0, sent: 0, speech: "", found: 0, checked: 0, kept: 0 };
  $("#graphCard").hidden = true;
  clearInterval(timer);
  timer = setInterval(tick, 500);
  t0 = performance.now();
  drawMap();
  $("#mapHint").textContent = "watch them work";
  $("#meter").hidden = false; $("#calls").textContent = "";
  $("#feed").innerHTML = ""; $("#feed").hidden = false;
  $("#result").hidden = true; $("#evidenceCard").hidden = true; $("#evidence").innerHTML = "";
  showPost(post);
  $("#mapCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

function handle(ev) {
  if (ev.type === "result" || ev.type === "error") { finished = true; clearInterval(timer); tick(); }
  if (ev.type === "step") addStep(ev);
  else if (ev.type === "evidence") addEvidence(ev.row);
  else if (ev.type === "result") showResult(ev);
  else if (ev.type === "error") {
    feedLine({ agent: "error", cls: "err", mark: "alert", name: "Stopped", by: "", text: ev.text });
    document.querySelectorAll(".node.running").forEach((n) => n.classList.replace("running", "fail"));
  }
}

function feedLine({ agent, cls, mark, name, by, text, thumbs }) {
  const li = document.createElement("li");
  li.className = cls; li.dataset.agent = agent;
  li.innerHTML = `<span class="dot">${icon(mark)}</span><div><div class="head"><span class="who">${esc(name)}</span>
    ${by ? `<span class="chip ${IS_META(by) ? "" : "tool"}">${esc(by)}</span>` : ""}</div><div class="what">${esc(text)}</div>
    ${(thumbs || []).length ? `<div class="thumbs ${agent === "witness" ? "big" : ""}">${thumbs.map((t) => `<img src="${t}" alt="">`).join("")}</div>` : ""}</div>`;
  $("#feed").appendChild(li);
  $("#feed").scrollTop = $("#feed").scrollHeight;
  return li;
}

function addStep(ev) {
  const node = document.getElementById("node-" + ev.agent);
  const [name, by] = (ev.label || ev.agent).split(" · ");
  if (ev.status === "done") collect(ev);
  if (ev.status === "running") {
    node?.classList.remove("done", "sent");
    node?.classList.add("running");
    return;
  }
  const sent = ev.approve === false;
  if (node) { node.classList.remove("running"); node.classList.add(sent ? "sent" : "done"); node.title = ev.text; }
  if (ev.agent === "post" && ev.post) {
    showPost({ media: (ev.thumbs || [])[0] || null, text: ev.post.text,
               meta: `@${ev.post.author} · ${ev.post.posted_on || ""}` });
  }
  if (ev.agent === "frames" && !$("#media").innerHTML && (ev.thumbs || []).length) {
    $("#media").innerHTML = `<img src="${ev.thumbs[0]}" alt="A frame of the video">`;
  }
  if (/Muse|SAM/.test(by || "")) { modelCalls += 1; $("#calls").textContent = modelCalls + " model steps"; }
  feedLine({ agent: ev.agent, cls: sent ? "sent" : (ev.agent === "grounds" && ev.grounds?.ok ? "ok" : ""), mark: sent ? "back" : ev.agent,
             name, by, text: ev.text, thumbs: ev.agent === "post" ? [] : ev.thumbs });
}

// Only web links become clickable; anything else (javascript:, data:) is shown as plain text.
const ext = (url, text) => /^https?:\/\//i.test(url || "")
  ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text);
const MATCH = { full: ["Same image", "full"], "confirmed look-alike": ["Same footage, checked", "confirmed"], partial: ["Partial match", ""], scene: ["In the footage itself", "scene"] };

function addEvidence(r) {
  G.rows[r.id] = r;
  $("#evidenceCard").hidden = false;
  let card = document.getElementById("ev-" + r.id);
  if (!card) {
    card = document.createElement("article"); card.className = "ev"; card.id = "ev-" + r.id;
    const n = (r.id[0] === "S" ? -100 : 0) + +r.id.slice(1);
    const key = (x) => (x.id[3] === "S" ? -100 : 0) + +x.id.slice(4);
    const next = [...$("#evidence").children].find((x) => key(x) > n);
    $("#evidence").insertBefore(card, next || null);
  }
  const [mlabel, mcls] = MATCH[r.match] || [r.match || "", ""];
  const says = [r.described_place, r.described_date, r.described_event].filter(Boolean).join(" · ");
  const dates = [
    ["Published", r.page_published ? String(r.page_published).slice(0, 10) + (r.date_source ? ` (${r.date_source})` : "") : null],
    ["Image archived", r.image_first ? ext(r.image_snapshot, r.image_first) : null],
    ["Page archived", r.page_first ? ext(r.page_snapshot, r.page_first) : null],
    ["In the video at", r.scene_t != null ? r.scene_t + " s" : null],
  ].filter(([, v]) => v);
  const pic = r.image_url && /^(https?:|data:image\/)/.test(r.image_url)
    ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('noimg');this.remove()">` : "";
  card.innerHTML = `<div class="pic ${pic ? "" : "noimg"}">${pic}<span class="id">${esc(r.id)}</span></div>
    <div class="body">
      <div class="src">${icon("globe")}${r.match === "scene" ? "The post's own footage" : ext(r.url, r.domain)}</div>
      <div class="badges">${mlabel ? `<span class="badge ${mcls}">${esc(mlabel)}</span>` : ""}${r.fact_checker ? '<span class="badge fc">Fact-check site</span>' : ""}</div>
      ${dates.length ? `<dl class="dates">${dates.map(([k, v]) => `<dt>${k}</dt><dd>${k === "Published" || k === "In the video at" ? esc(v) : v}</dd>`).join("")}</dl>` : ""}
      <div class="says">${says ? esc(says) : `<span class="nil">${r.opened === false ? "Page did not open" : "No description read"}</span>`}</div>
      ${r.quote ? `<div class="quote">“${esc(r.quote)}”</div>` : ""}
    </div>`;
}

function fact(label, parts, cls = "") {
  const v = parts.filter(Boolean);
  return `<div class="fact ${cls}"><div class="k">${label}</div><div class="v">${v.length ? v.map(esc).join("<br>") : '<span class="nil">Not stated</span>'}</div></div>`;
}

function span(a, b) {
  // "4 years 7 months" between two ISO dates.
  const d1 = new Date(a), d2 = new Date(b);
  if (isNaN(d1) || isNaN(d2) || d2 <= d1) return null;
  let m = (d2.getFullYear() - d1.getFullYear()) * 12 + d2.getMonth() - d1.getMonth();
  if (d2.getDate() < d1.getDate()) m -= 1;
  const days = Math.round((d2 - d1) / 864e5);
  if (m < 1) return days + (days === 1 ? " day" : " days");
  const y = Math.floor(m / 12), mo = m % 12;
  return [y ? y + (y === 1 ? " year" : " years") : "", mo ? mo + (mo === 1 ? " month" : " months") : ""].filter(Boolean).join(" ");
}

function axis(tl) {
  const pts = tl.filter((t) => /^\d{4}-\d\d-\d\d/.test(t.date)).map((t) => ({ ...t, ms: +new Date(t.date.slice(0, 10)) }));
  if (pts.length < 2) return "";
  const lo = Math.min(...pts.map((p) => p.ms)), hi = Math.max(...pts.map((p) => p.ms));
  if (hi === lo) return "";
  const x = (ms) => 2 + 96 * (ms - lo) / (hi - lo);
  const claim = pts.find((p) => p.kind === "claim"), first = pts.filter((p) => p.kind !== "claim")[0];
  const seg = claim && first && first.ms < claim.ms ? `<div class="seg" style="left:${x(first.ms)}%;width:${x(claim.ms) - x(first.ms)}%"></div>` : "";
  return `<div class="axis">${seg}${pts.map((p) => `<span class="pin ${p.kind}" style="left:${x(p.ms)}%" title="${esc(p.date)}"></span>`).join("")}</div>`;
}

function showResult(r) {
  (r.evidence || []).forEach(addEvidence);
  const box = $("#result");
  box.hidden = false;
  box.className = "card result " + r.verdict;
  document.querySelectorAll(".node:not(.done):not(.sent):not(.fail)").forEach((n) => n.classList.add("skipped"));
  const c = r.claim || {}, a = r.actual || {};
  const tl = r.timeline || [];
  // The gap uses only dates that show the image itself existed: an archived image file, or the publication date of a
  // page with the same image (not a wiki article's creation date), among the copies the verdict cites.
  const claimT = tl.find((t) => t.kind === "claim");
  const ev = Object.fromEntries((r.evidence || []).map((e) => [e.id, e]));
  const proven = (e) => [e.image_first, (["full", "confirmed look-alike"].includes(e.match) && !/(^|\.)(wikipedia|wikimedia|wikiwand|fandom)\.(org|com)$/.test(e.domain || ""))
    ? String(e.page_published || "").slice(0, 10) : null].filter((d) => /^\d{4}-\d\d-\d\d$/.test(d || ""));
  const dates = (r.cited || []).flatMap((id) => (ev[id] ? proven(ev[id]) : [])).sort();
  const firstCopy = dates.length ? { date: dates[0] } : null;
  const gap = r.verdict === "inconsistent" && claimT && firstCopy ? span(firstCopy.date, claimT.date) : null;
  const compare = r.verdict === "inconsistent" && (a.place || a.date || a.event)
    ? `<div class="compare">${fact("The caption says", [c.place, c.claimed_date, c.event])}<div class="vs">${icon("inconsistent")}</div>${fact("The record says", [a.place, a.date, a.event], "record")}</div>`
    : `<div class="compare single">${fact("The caption says", [c.place, c.claimed_date, c.event])}</div>`;
  let proof = "";
  if (r.basis === "date rule" && r.rule) {
    proof = `<div class="proof">${icon("grounds")}<div><b>Proof checked by code: the date rule</b><span>The image file was archived on ${esc(r.rule.image_first)}, ${r.rule.days_before} days before the earliest date the caption allows (${esc(r.rule.period_start)}).</span></div></div>`;
  } else if (r.grounds) {
    proof = `<div class="proof ${r.grounds.ok ? "" : "weak"}">${icon(r.grounds.ok ? "grounds" : "alert")}<div><b>${r.grounds.ok ? "Proof checked by code" : "Proof check: not enough"}</b><span>${esc(r.grounds.text)}</span></div></div>`;
  }
  const calls = r.cost?.calls || {};
  const models = Object.entries(calls).map(([m, n]) => `<span class="chip">${esc(MODEL_NAMES[m] || m)} × ${n}</span>`).join("");
  box.innerHTML = `
    <div class="banner"><span class="big">${icon(r.verdict)}</span><div>
      <div class="verdict">${LABEL[r.verdict] || esc(r.verdict)}</div>
      <p class="summary">${esc(r.summary || "")}</p></div></div>
    <div class="rbody">
      ${gap ? `<div class="gap"><b>${gap}</b><span>between the earliest dated copy of this image the verdict cites (${esc(firstCopy.date)}) and the date the caption claims (${esc(claimT.date)})</span></div>` : ""}
      ${compare}
      ${proof}
      ${tl.length ? `<h3>Timeline</h3>${axis(tl)}<ol class="tl">${tl.map((t) => `
        <li class="${t.kind}"><time>${esc(t.date)}</time><span class="tag">${TAG[t.kind] || t.kind}</span><span>${t.url ? ext(t.url, t.text) : esc(t.text)}</span></li>`).join("")}</ol>` : ""}
      ${r.community_note ? `<div class="note"><div class="k">For comparison: the X Community Note on this post</div>
        <p>${esc(r.community_note)}</p><small class="hint">Never shown to the agents: Backstory reached its verdict without it.</small></div>` : ""}
      <div class="basis"><span>${esc(BASIS[r.basis] || r.basis || "")}</span>
        ${r.post ? `<span>Post: ${ext(r.post.url, "@" + r.post.author + ", " + r.post.posted_on)}</span>` : ""}
        <span class="models">${models}</span><span>$${(r.cost?.usd ?? 0).toFixed(3)}${r.mode === "replay" ? " · recorded run" : ""}</span></div>
    </div>`;
  (r.cited || []).forEach((id) => {
    const card = document.getElementById("ev-" + id);
    if (card) { card.classList.add("cited"); card.querySelector(".pic").insertAdjacentHTML("beforeend", '<span class="citedtag">Cited</span>'); }
  });
  $("#mapHint").textContent = "done";
  drawGraph(r);
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

init();

// The check graph: what was checked, which parts of the media were searched, what was found and kept, and what
// the verdict rests on.
function collect(ev) {
  if (ev.agent === "post" && ev.post) G.post = { media: (ev.thumbs || [])[0] || G.post?.media, text: ev.post.text, meta: "@" + ev.post.author };
  if (ev.agent === "frames" && !G.post?.media && (ev.thumbs || []).length) G.post = { ...(G.post || {}), media: ev.thumbs[0] };
  if (ev.agent === "speech") G.speech = ev.transcript || "";
  if (ev.agent === "search") { G.inputs = ev.inputs || []; G.found = ev.count || 0; }
  if (ev.agent === "match") G.checked += ev.checked || 0;
  if (ev.agent === "judge") G.judge += 1;
  if (ev.agent === "critic" && ev.approve === false) G.sent += 1;
  if (ev.agent === "critic") G.approved = ev.approve !== false;
}

const short = (t, n) => { t = String(t || ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };

function drawGraph(r) {
  const card = $("#graphCard");
  const rows = Object.values(G.rows).length ? Object.values(G.rows) : (r.evidence || []);
  const cited = new Set(r.cited || []);
  const ruleId = r.rule?.evidence_id;
  const pages = rows.filter((x) => x.match !== "scene");
  const scene = rows.filter((x) => x.match === "scene");
  const shown = [...pages].sort((a, b) => (cited.has(b.id) - cited.has(a.id)) || (+a.id.slice(1) - +b.id.slice(1))).slice(0, 7);
  const aside = Math.max(0, G.found - pages.length);
  const c = r.claim || {};
  const date = (x) => x.image_first ? "archived " + x.image_first : x.page_published ? "published " + String(x.page_published).slice(0, 10)
    : x.page_first ? "page archived " + x.page_first : "";
  const badge = (x) => { const [l, k] = MATCH[x.match] || [x.match, ""]; return `<span class="badge ${k}">${esc(l)}</span>`; };
  const media = G.post?.media ? `<img src="${esc(G.post.media)}" alt="">` : "";
  const col1 = `<div class="gcol"><div class="gt">1 · The post</div>
    <div class="gnode post" id="g-post">${media}<div class="gtext">${esc(short(G.post?.text || c.caption, 140))}</div></div>
    <div class="gnode claim" id="g-claim"><b>The claim</b>${[c.place, c.claimed_date, c.event].filter(Boolean).map((v) => `<span>${esc(short(v, 60))}</span>`).join("")}</div></div>`;
  const tiles = G.inputs.map((x, i) => `<div class="gnode tile" id="g-in-${i}">${x.thumb ? `<img src="${esc(x.thumb)}" alt="">` : ""}<span>${esc(x.kind)}</span></div>`).join("");
  const col2 = `<div class="gcol"><div class="gt">2 · What was searched</div><div class="tiles">${tiles}</div>
    ${scene.map((x) => `<div class="gnode sign" id="g-${x.id}">${x.image_url ? `<img src="${esc(x.image_url)}" alt="">` : ""}<span>Sign in the scene: “${esc(short(x.quote, 40))}” → ${esc(x.described_place || "")}</span></div>`).join("")}
    ${G.speech ? `<div class="gnode speech" id="g-speech">${icon("speech")}<span>“${esc(short(G.speech, 90))}”</span></div>` : ""}</div>`;
  const col3 = `<div class="gcol"><div class="gt">3 · What was found</div>
    <div class="gsum">${G.found} page${G.found === 1 ? "" : "s"} found${G.checked ? ` · ${G.checked} look-alikes compared` : ""}</div>
    ${shown.map((x) => `<div class="gnode row ${cited.has(x.id) || x.id === ruleId ? "cited" : ""}" id="g-${x.id}"><div><b>${esc(x.id)}</b> ${esc(short(x.domain, 28))}</div>
      <div class="gmeta">${badge(x)}${date(x) ? `<span class="gdate">${esc(date(x))}</span>` : ""}</div>
      ${x.described_place || x.described_event ? `<div class="gsays">${esc(short([x.described_place, x.described_event].filter(Boolean).join(" · "), 70))}</div>` : ""}</div>`).join("")}
    ${pages.length ? "" : `<div class="gnode gempty">No earlier copy of this ${G.inputs.length > 1 ? "media" : "photo"} found online</div>`}
    ${pages.length > shown.length ? `<div class="gsum dim">+ ${pages.length - shown.length} more kept</div>` : ""}
    ${aside ? `<div class="gsum dim">${aside} set aside: not the same image, or nothing to read or date</div>` : ""}</div>`;
  const ok = r.verdict;
  const g = r.grounds;
  const col4 = `<div class="gcol"><div class="gt">4 · The decision</div>
    <div class="gnode step ${r.basis === "date rule" ? "on" : ""}" id="g-rule">${icon("rule")}<div><b>Date rule</b><span>${r.basis === "date rule" ? `fired: a copy archived ${esc(r.rule?.image_first || "")}` : "did not fire"}</span></div></div>
    <div class="gnode step ${r.basis !== "date rule" && G.judge ? "on" : ""}" id="g-judge">${icon("judge")}<div><b>Judge · Muse Spark</b><span>${G.judge > 1 ? G.judge + " rounds" : G.judge ? "1 round" : "not needed"}</span></div></div>
    <div class="gnode step ${G.sent ? "warn" : G.approved ? "on" : ""}" id="g-critic">${icon("critic")}<div><b>Critic · Muse Wonder</b><span>${G.sent ? `sent the judge back ${G.sent > 1 ? G.sent + " times" : "once"}${G.approved ? ", then approved" : ""}` : G.approved ? "approved" : "not needed"}</span></div></div>
    ${g ? `<div class="gnode step ${g.ok ? "on" : "warn"}" id="g-grounds">${icon("grounds")}<div><b>Proof check · code</b><span>${g.ok ? esc(short(g.kind, 40)) : "too little proof"}</span></div></div>` : ""}
    <div class="gnode verdict ${ok}" id="g-verdict">${icon(ok)}<b>${LABEL[ok] || ok}</b></div></div>`;
  card.hidden = false;
  $("#graph").innerHTML = `<svg class="glines" id="glines"></svg>${col1}${col2}${col3}${col4}`;
  const links = [["g-post", "g-claim", ""]];
  G.inputs.forEach((_, i) => links.push(["g-post", "g-in-" + i, ""]));
  shown.forEach((x) => links.push([x.found_by != null && document.getElementById("g-in-" + x.found_by) ? "g-in-" + x.found_by : "g-in-0", "g-" + x.id, cited.has(x.id) ? "hot" : ""]));
  shown.filter((x) => cited.has(x.id) || x.id === ruleId).forEach((x) => links.push(["g-" + x.id, x.id === ruleId && r.basis === "date rule" ? "g-rule" : "g-judge", "hot"]));
  scene.filter((x) => cited.has(x.id)).forEach((x) => links.push(["g-" + x.id, "g-judge", "hot"]));
  links.push(["g-claim", "g-judge", ""], ["g-rule", "g-judge", ""], ["g-judge", "g-critic", ""]);
  links.push([g ? "g-critic" : "g-critic", g ? "g-grounds" : "g-verdict", ""]);
  if (g) links.push(["g-grounds", "g-verdict", ""]);
  if (r.basis === "date rule") links.push(["g-rule", "g-verdict", "hot"]);
  G.links = links;
  requestAnimationFrame(drawLines);
}

function drawLines() {
  const box = $("#graph"), svg = $("#glines");
  if (!box || !svg || !G.links) return;
  const b = box.getBoundingClientRect();
  svg.setAttribute("width", b.width); svg.setAttribute("height", b.height);
  const narrow = innerWidth < 900;
  svg.innerHTML = G.links.map(([from, to, cls]) => {
    const p = document.getElementById(from), q = document.getElementById(to);
    if (!p || !q) return "";
    const a = p.getBoundingClientRect(), z = q.getBoundingClientRect();
    let x1, y1, x2, y2;
    if (narrow || Math.abs(a.left - z.left) < 20) { x1 = a.left + a.width / 2 - b.left; y1 = a.bottom - b.top; x2 = z.left + z.width / 2 - b.left; y2 = z.top - b.top; }
    else { x1 = a.right - b.left; y1 = a.top + a.height / 2 - b.top; x2 = z.left - b.left; y2 = z.top + z.height / 2 - b.top; }
    const m = narrow || Math.abs(a.left - z.left) < 20 ? `M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2}`
      : `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
    return `<path class="${cls}" d="${m}"/>`;
  }).join("");
}
addEventListener("resize", () => requestAnimationFrame(drawLines));
