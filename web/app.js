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
const VCHIP = { inconsistent: "Does not fit", consistent: "Fits", cannot_tell: "Cannot verify" };
const TAG = { claim: "Caption claims", evidence: "Copy online", described: "A page says" };

function drawMap() {
  $("#stages").innerHTML = STAGES.map((s, i) => `<div class="stage"><h4><i>${i + 1}</i>${esc(s.title)}</h4>
    ${s.agents.map(([id, name, by]) => `<div class="node ${IS_META(by) ? "meta" : ""}" id="node-${id}" title="">
      <span class="nd">${icon(id)}</span><div><b>${esc(name)}</b><small>${esc(by)}</small></div></div>`).join("")}</div>`).join("");
}

async function updateStatus() {
  const st = await fetch("/api/status").then((r) => r.json()).catch(() => ({}));
  const lv = st.live || {};
  if (st.mode !== "live") {
    $("#mode").innerHTML = '<i class="live off"></i>Demo: recorded checks';
    $("#mode").title = "This copy replays checks recorded earlier, step by step, with no keys and no network.";
    $("#demoNote").textContent = "This copy replays recorded checks: pick one of the cases below. New links and uploads are checked when Backstory runs with its keys.";
  } else if (lv.live) {
    $("#mode").innerHTML = `<i class="live"></i>Live checks · ${lv.left} of ${lv.per_visitor} left today`;
    $("#mode").title = "New links and uploads run live on Meta's models. Recorded checks are unlimited.";
    $("#demoNote").textContent = `Live: paste any post on X. You have ${lv.left} of ${lv.per_visitor} live checks left today; a check takes about a minute. The recorded checks below are unlimited.`;
  } else {
    $("#mode").innerHTML = '<i class="live off"></i>Live checks paused';
    $("#mode").title = "Live checks are paused (" + (lv.reason || "") + "). Recorded checks still work.";
    $("#demoNote").textContent = `Live checks are paused right now (${lv.reason || "budget"}). The recorded checks below still work, step by step.`;
  }
  $("#demoNote").hidden = false;
}

async function init() {
  drawMap();
  await updateStatus();
  const ex = await fetch("/api/examples").then((r) => r.json()).catch(() => []);
  EXAMPLES = ex;
  // One finished case is shown first, so the page shows what an answer looks like; the gallery leaves it out.
  const pv = ex.find((e) => e.preview?.verdict === "inconsistent" && e.preview.first_date);
  const gallery = ex.filter((e) => e !== pv);
  $("#examplesWrap").hidden = !gallery.length;
  const KIND = { link: "X post", recorded: "X post", video: "Video", photo: "Photo" };
  $("#examples").innerHTML = gallery.map((e) => `
    <button type="button" class="ex" data-id="${esc(e.id)}">
      <img src="/api/examples/${encodeURIComponent(e.id)}/image" alt="" loading="lazy">
      ${VCHIP[e.preview?.verdict] ? `<i class="vchip ${e.preview.verdict}">${icon(e.preview.verdict)}${VCHIP[e.preview.verdict]}</i>` : ""}
      <div class="exbody"><span class="kind">${KIND[e.kind || "photo"] || "Photo"}${e.fresh ? ' <i class="fresh">October 2026</i>' : ""}</span><b>${esc(e.title)}</b><span>${esc(e.blurb || e.caption)}</span></div>
    </button>`).join("");
  if (pv) {
    const p = pv.preview, gap = span(p.first_date, p.claim_date);
    $("#previewWrap").hidden = false;
    $("#heroPreview").innerHTML = `<div class="hp-img"><img src="/api/examples/${encodeURIComponent(pv.id)}/image" alt=""><span class="hp-badge">${icon("inconsistent")}Does not fit</span></div>
      <div class="hp-body"><div class="hp-k">Shared as</div><b>${esc(short(p.claimed, 70))}</b>
        <div class="hp-gap">${esc(gap || "")}<span> earlier</span></div>
        <div class="hp-k">First seen</div><b>${esc(p.first_date)} · ${esc(p.first_domain || "")}</b>${p.record ? `<span>${esc(short(p.record, 70))}</span>` : ""}
        <button type="button" class="hp-go" id="hpGo">Watch the agents check it</button></div>`;
    $("#hpGo").addEventListener("click", () => openExample(pv));
  }
  document.querySelectorAll(".ex").forEach((b, i) => { b.style.animationDelay = (0.15 + i * 0.05) + "s"; });
  document.querySelectorAll(".ex").forEach((b) => b.addEventListener("click", () => openExample(ex.find((e) => e.id === b.dataset.id))));
  route();
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

let EXAMPLES = [], runId = 0;

// Two views: the home page, where you choose what to check, and the check page, where the agents work.
function showView(name, url, title) {
  $("#homeView").hidden = name !== "home";
  $("#checkView").hidden = name !== "check";
  if (url && location.pathname + location.search !== url) history.pushState({ view: name }, "", url);
  $("#checkTitle").textContent = title || "";
  document.title = name === "check" && title ? title + " · Backstory" : "Backstory";
  window.scrollTo(0, 0);
}

function openExample(e) {
  if (!e) return;
  chosenExample = e;
  $("#form").requestSubmit();
}

function route() {
  const q = new URLSearchParams(location.search);
  if (location.pathname === "/check") {
    const ex = EXAMPLES.find((e) => e.id === q.get("case"));
    if (ex) return openExample(ex);
    if (q.get("post")) { $("#postUrl").value = q.get("post"); setTab("link"); chosenExample = null; return $("#form").requestSubmit(); }
    history.replaceState({}, "", "/");
  }
  showView("home");
}
addEventListener("popstate", () => { runId += 1; wake?.(); running = false; setRunning(false); route(); });

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (running) return;
  const fd = new FormData();
  let post = null, url = "/check", title = "";
  if (chosenExample) {
    url = "/check?case=" + encodeURIComponent(chosenExample.id); title = chosenExample.title;
    fd.append("example_id", chosenExample.id);
    post = { media: chosenExample.kind === "video" ? `/api/examples/${encodeURIComponent(chosenExample.id)}/video` : `/api/examples/${encodeURIComponent(chosenExample.id)}/image`,
             video: chosenExample.kind === "video", text: /link|recorded/.test(chosenExample.kind) ? "" : chosenExample.caption,
             meta: /link|recorded/.test(chosenExample.kind) ? chosenExample.post_url : (chosenExample.posted_on ? "Posted " + chosenExample.posted_on : "") };
  } else if (tab === "link") {
    const link = $("#postUrl").value.trim();
    if (!/^https?:\/\/(www\.|mobile\.)?(x|twitter)\.com\/[^/]+\/status\/\d+/.test(link)) {
      $("#formError").textContent = "Paste a link to a post on X (x.com/user/status/…), or pick a case above.";
      return;
    }
    fd.append("post_url", link);
    post = { media: null, text: "", meta: link };
    url = "/check?post=" + encodeURIComponent(link); title = "Post on X";
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
    title = "Uploaded " + (post.video ? "video" : "photo");
  }
  chosenExample = null;
  showView("check", url, title);
  const mine = ++runId;
  $("#formError").textContent = "";
  reset(post);
  setRunning(true);
  // A recorded check comes whole and is paced here, so the viewer can speed it up or skip to the answer.
  const paced = fd.has("example_id");
  if (paced) fd.append("paced_here", "1");
  playback(paced, url);
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
      while ((i = buf.indexOf("\n")) >= 0 && mine === runId) {
        const ev = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1);
        handle(ev);
        if (paced) await pause(ev);
      }
      if (mine !== runId) { reader.cancel(); break; }
    }
    if (!finished && mine === runId) handle({ type: "error", text: "The connection closed before the check finished. Please try again." });
  } catch (err) {
    handle({ type: "error", text: err.message });
  }
  clearInterval(timer);
  setRunning(false);
  $("#replay").hidden = true;
  updateStatus();
});

// The post and the copy in one frame: drag across to see one turn into the other. Offered only when both pictures load
// and they are not the same file.
function wipe(pair) {
  const a = pair?.querySelector(".tn:not(.first) img"), b = pair?.querySelector(".tn.first img");
  if (!a || !b || a.src === b.src || G.post?.video) return;
  const loaded = (img) => new Promise((ok, no) => {
    if (img.complete) return img.naturalWidth ? ok() : no();
    img.addEventListener("load", ok, { once: true }); img.addEventListener("error", no, { once: true });
  });
  Promise.all([loaded(a), loaded(b)]).then(() => {
    const right = pair.querySelector(".tn.first .tnk").textContent;
    pair.insertAdjacentHTML("afterend", `<div class="wipebox"><button type="button" class="more wipebtn">${icon("match")}Compare the two pictures</button>
      <div class="wipe" hidden style="--at:50%"><img class="wa" src="${esc(a.src)}" alt="The post's picture">
        <img class="wb" src="${esc(b.src)}" alt="" referrerpolicy="no-referrer"><span class="wl">The post</span><span class="wr">${esc(right)}</span>
        <input type="range" min="0" max="100" value="50" aria-label="Slide between the post's picture and the copy"></div></div>`);
    const box = pair.nextElementSibling, w = box.querySelector(".wipe");
    box.querySelector(".wipebtn").addEventListener("click", (e) => {
      w.hidden = !w.hidden;
      e.currentTarget.lastChild.textContent = w.hidden ? "Compare the two pictures" : "Hide the comparison";
    });
    w.querySelector("input").addEventListener("input", (e) => w.style.setProperty("--at", e.target.value + "%"));
  }, () => {});
}

// Pauses between a recorded check's steps, the same as the server's: a viewer can follow the agents, at 1x or 2x.
let speed = 1, skipping = false, wake = null;
function pause(ev) {
  const s = ev.type === "step" ? (ev.status === "running" ? 0.25 : 0.55) : ev.type === "evidence" ? 0.06 : 0;
  if (!s || skipping) return Promise.resolve();
  return new Promise((done) => { const t = setTimeout(done, s * 1000 / speed); wake = () => { clearTimeout(t); done(); }; });
}
function playback(paced, url) {
  skipping = false;
  $("#replay").hidden = !paced;
  // Recorded checks and posts on X have a link that opens the same check; an uploaded file has none.
  $("#share").hidden = url === "/check";
  $("#share").dataset.url = url;
  $("#share b").textContent = "Copy link";
}
$("#speed").addEventListener("click", () => {
  speed = speed === 1 ? 2 : 1;
  $("#speed").setAttribute("aria-pressed", speed === 2);
  wake?.();
});
$("#skip").addEventListener("click", () => { skipping = true; wake?.(); $("#replay").hidden = true; });
$("#share").addEventListener("click", () => {
  const link = location.origin + $("#share").dataset.url;
  const said = () => { $("#share b").textContent = "Link copied"; setTimeout(() => { $("#share b").textContent = "Copy link"; }, 1800); };
  if (navigator.clipboard) navigator.clipboard.writeText(link).then(said, () => prompt("Copy this link:", link));
  else prompt("Copy this link:", link);
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
// What each agent said in this check, shown when the pointer rests on it in the map; model answers join at the end.
let NOTES = {}, CALLS = {};
const ROLE_AGENT = { "Claim reader": "claim", "Match checker": "match", "Page reader": "reader", "Judge": "judge", "Critic": "critic",
  "Scene witness": "witness", "Scene witness check": "witness", "Speech reader": "speech", "Photo finder": "cutout" };
function tick() { $("#elapsed").textContent = ((performance.now() - t0) / 1000).toFixed(0) + " s"; }

function showPost(p) {
  $("#postCard").hidden = false;
  $("#media").innerHTML = p.media ? (p.video ? `<video src="${esc(p.media)}" controls muted playsinline></video>` : `<img src="${esc(p.media)}" alt="The checked photo">`) : "";
  $("#postMeta").innerHTML = (p.meta ? esc(p.meta) : "") + (p.url ? ` · ${ext(p.url, "open on X")}` : "");
  $("#postText").textContent = p.text || "";
}

function reset(post) {
  finished = false; modelCalls = 0; NOTES = {}; CALLS = {}; hideTip();
  G = { post: post, inputs: [], rows: {}, judge: 0, sent: 0, speech: "", found: 0, checked: 0, kept: 0 };
  $("#graphCard").hidden = true;
  clearInterval(timer);
  timer = setInterval(tick, 500);
  t0 = performance.now();
  drawMap();
  $("#mapHint").textContent = "watch them work";
  $("#meter").hidden = false; $("#calls").textContent = "";
  $("#feed").innerHTML = ""; $("#feed").hidden = false;
  $("#logToggle")?.remove(); $("#evMore")?.remove();
  $("#mapCard").classList.remove("wide"); $(".right").appendChild($("#mapCard")); $(".pair").classList.remove("done");
  $("#result").hidden = true; $("#evidenceCard").hidden = true; $("#evidence").innerHTML = "";
  showPost(post);
}

function handle(ev) {
  if (ev.type === "result" || ev.type === "error") { finished = true; clearInterval(timer); tick(); }
  if (ev.type === "step") addStep(ev);
  else if (ev.type === "evidence") addEvidence(ev.row);
  else if (ev.type === "result") showResult(ev);
  else if (ev.type === "error") {
    feedLine({ agent: "error", cls: "err", mark: "alert", name: "Stopped", by: "", text: ev.text });
    $("#feed").hidden = false;
    $("#feed").insertAdjacentHTML("beforeend", `<li class="err"><span></span><div><a href="/">Open a recorded check instead &rarr;</a></div></li>`);
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
  if (node) { node.classList.remove("running"); node.classList.add(sent ? "sent" : "done"); }
  (NOTES[ev.agent] = NOTES[ev.agent] || []).push({ text: ev.text, sent, thumbs: ev.agent === "post" ? [] : (ev.thumbs || []).slice(0, 3) });
  if (ev.agent === "post" && ev.post) {
    // A recorded post carries no copy of its media: the picture is the post's own, served by X.
    showPost({ media: (ev.thumbs || [])[0] || (ev.post.media_urls || [])[0] || null, text: ev.post.text,
               meta: `@${ev.post.author} · ${ev.post.posted_on || ""}`, url: ev.post.url });
  }
  if (ev.agent === "frames" && !$("#media").innerHTML && (ev.thumbs || []).length) {
    $("#media").innerHTML = `<img src="${ev.thumbs[0]}" alt="A frame of the video">`;
  }
  if (/Muse|SAM/.test(by || "")) { modelCalls += 1; $("#calls").textContent = modelCalls + " steps on Meta's models"; }
  feedLine({ agent: ev.agent, cls: sent ? "sent" : (ev.agent === "grounds" && ev.grounds?.ok ? "ok" : ""), mark: sent ? "back" : ev.agent,
             name, by, text: ev.text, thumbs: ev.agent === "post" ? [] : ev.thumbs });
}

// Only web links become clickable; anything else (javascript:, data:) is shown as plain text.
const ext = (url, text) => /^https?:\/\//i.test(url || "")
  ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text);
const MATCH = { full: ["Same image", "full"], "confirmed look-alike": ["Same footage, checked by Muse Spark", "full"], partial: ["Partial match", ""], scene: ["In the footage itself", "scene"] };

function addEvidence(r) {
  G.rows[r.id] = r;
  $("#evidenceCard").hidden = false;
  let card = document.getElementById("ev-" + r.id);
  if (!card) {
    card = document.createElement("article"); card.className = "ev reveal"; card.id = "ev-" + r.id;
    const n = (r.id[0] === "S" ? -100 : 0) + +r.id.slice(1);
    const key = (x) => (x.id[3] === "S" ? -100 : 0) + +x.id.slice(4);
    const next = [...$("#evidence").children].find((x) => key(x) > n);
    $("#evidence").insertBefore(card, next || null);
  }
  const [mlabel, mcls] = MATCH[r.match] || [r.match || "", ""];
  const says = [r.described_place, r.described_date, r.described_event].filter(Boolean).join(" · ");
  const dates = [
    WIKI.test(r.domain || "") && r.page_published
      ? ["Article created", String(r.page_published).slice(0, 10)]
      : ["Published", r.page_published ? String(r.page_published).slice(0, 10) + (r.date_source ? ` (${r.date_source})` : "") : null],
    ["Image archived", r.image_first ? ext(r.image_snapshot, r.image_first) : null],
    ["Page archived", r.page_first ? ext(r.page_snapshot, r.page_first) : null],
    ["In the video at", r.scene_t != null ? vtime(r.scene_t) : null],
  ].filter(([, v]) => v);
  const pic = r.image_url && /^(https?:|data:image\/)/.test(r.image_url)
    ? `<img src="${esc(r.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('noimg');this.remove()">` : "";
  card.innerHTML = `<div class="pic ${pic ? "" : "noimg"}">${pic}<span class="id">${esc(r.id)}</span></div>
    <div class="body">
      <div class="src">${icon(r.match === "scene" ? "witness" : "globe")}${r.match === "scene" ? "The post's own footage" : ext(r.url, r.domain)}</div>
      <div class="badges">${mlabel ? `<span class="badge ${mcls}">${esc(mlabel)}</span>` : ""}${r.fact_checker ? '<span class="badge fc">Fact-check site</span>' : ""}</div>
      ${dates.length ? `<dl class="dates">${dates.map(([k, v]) => `<dt>${k}</dt><dd>${k === "Published" || k === "Article created" || k === "In the video at" ? esc(v) : v}${k === "Article created" ? '<small class="unused">not used as proof</small>' : ""}</dd>`).join("")}</dl>` : ""}
      <div class="says">${says ? esc(says) : `<span class="nil">${r.opened === false ? "Page did not open" : "The page gives no description"}</span>`}</div>
      ${r.quote ? `<div class="quote">“${esc(r.quote)}”</div>` : ""}
    </div>`;
}

// "E7 (tiktok.com) shows…" reads as "tiktok.com shows…": evidence numbers are for the table, not for sentences.
const plainIds = (t) => String(t || "").replace(/^[ES]\d+:\s*/, "").replace(/\b[ES]\d+ \(([^)]+)\)/g, "$1");
const WIKI = /(^|\.)(wikipedia|wikimedia|wikiwand|fandom)\.(org|com)$/;

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

function axis(tl, claimDate) {
  // Copies from the same day share one pin; its label says how many.
  const byDay = {};
  tl.filter((t) => /^\d{4}-\d\d-\d\d/.test(t.date)).forEach((t) => {
    const k = t.kind + t.date.slice(0, 10);
    if (byDay[k]) byDay[k].n += 1; else byDay[k] = { ...t, n: 1, ms: +new Date(t.date.slice(0, 10)) };
  });
  const pts = Object.values(byDay);
  if (pts.length < 2) return "";
  const lo = Math.min(...pts.map((p) => p.ms)), hi = Math.max(...pts.map((p) => p.ms));
  if (hi === lo) return "";
  const x = (ms) => 3 + 94 * (ms - lo) / (hi - lo);
  const claim = pts.find((p) => p.kind === "claim"), first = pts.filter((p) => p.kind !== "claim")[0];
  const seg = claim && first && first.ms < claim.ms ? `<div class="seg" style="left:${x(first.ms)}%;width:${x(claim.ms) - x(first.ms)}%"></div>` : "";
  // Year labels at both ends and at the claim, unless they would sit on top of each other.
  const marks = [];
  [lo, claim?.ms, hi].filter(Boolean).forEach((ms) => { if (marks.every((m) => Math.abs(x(m) - x(ms)) > 7)) marks.push(ms); });
  const years = marks.map((ms) => `<span class="yr" style="left:${x(ms)}%">${new Date(ms).getFullYear()}</span>`).join("");
  // Pins closer than a pin's width merge into one, labelled with how many dates it holds; the claim keeps its own.
  const late = (p) => !!(claimDate && p.kind !== "claim" && p.date > claimDate);
  const groups = [];
  pts.slice().sort((p, q) => p.ms - q.ms).forEach((p) => {
    const g = groups[groups.length - 1];
    if (g && p.kind !== "claim" && g.kind !== "claim" && late(p) === g.late && x(p.ms) - x(g.ms) < 2.5) { g.n += p.n; g.last = p.date.slice(0, 10); }
    else groups.push({ ...p, late: late(p), last: null });
  });
  return `<div class="axis">${seg}${groups.map((p) => `<span class="pin ${p.kind}${p.late ? " late" : ""}" style="left:${x(p.ms)}%" title="${esc(p.date.slice(0, 10) + (p.last ? " to " + p.last : "") + (p.n > 1 ? " · " + p.n + " copies" : ""))}">${p.n > 1 ? `<i>${p.n}</i>` : ""}</span>`).join("")}${years}</div>`;
}

// A draft for X Community Notes, built by code from the evidence the verdict cites; the user checks it before posting.
function noteDraft(r) {
  const c = r.claim || {}, a = r.actual || {}, f = r.first_seen;
  const scene = (r.evidence || []).find((e) => e.match === "scene" && e.other_country && (r.cited || []).includes(e.id));
  const what = (G.inputs || []).some((x) => /frame/.test(x.kind)) ? "video" : "photo";
  let text = "";
  if (scene) {
    text = `This ${what} is not from ${c.place || "the place claimed"}. A sign in the footage reads "${scene.quote}", which places it in ${scene.described_place}.`;
  } else if (f) {
    // Shortest parts first to go when the note is too long; never cut a sentence in the middle.
    const base = `This ${what} is older than the post claims. It was online by ${f.date} (${f.domain})`;
    const what2 = c.event || c.place || "what the post says";
    const tails = [`. It does not show ${what2}${c.claimed_date ? " (" + c.claimed_date + ")" : ""}.`, `. It does not show ${what2}.`, "."];
    const desc = a.event ? `, described as ${a.event}` : "";
    text = [base + desc + tails[0], base + tails[0], base + tails[1], base + tails[2]].find((t) => t.length <= 250) || base + ".";
  } else return "";
  const src = scene ? "" : f.url || "";
  return text + (src ? " " + src : "");
}

function verifyLinks(r) {
  const urls = (r.post?.media_urls || []).filter((u) => /^https:\/\//.test(u)).slice(0, 2);
  if (!urls.length) return "";
  const eng = [["Google Lens", (u) => "https://lens.google.com/uploadbyurl?url=" + encodeURIComponent(u)],
               ["TinEye", (u) => "https://tineye.com/search?url=" + encodeURIComponent(u)],
               ["Yandex", (u) => "https://yandex.com/images/search?rpt=imageview&url=" + encodeURIComponent(u)],
               ["Bing", (u) => "https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:" + encodeURIComponent(u)]];
  return `<h3>Check it yourself</h3><div class="verify">${urls.map((u, i) => `<div><span class="hint">${urls.length > 1 ? "Image " + (i + 1) : "The post's image"}:</span> ${eng.map(([n, f]) => `<a href="${esc(f(u))}" target="_blank" rel="noopener noreferrer">${n}</a>`).join(" · ")}</div>`).join("")}
    <small class="hint">Reverse-search the same image in other engines. Every archived date above links to its Internet Archive copy.</small></div>`;
}

function receipt(r) {
  const log = r.cost?.log || [];
  if (!log.length) return "";
  const meta = log.filter((x) => /muse|sam/.test(x.model));
  const tok = log.reduce((s, x) => s + (x.in || 0) + (x.out || 0), 0);
  return `<details class="receipt"><summary>${icon("check")}<b>Model receipt</b><span>${meta.length} calls to Meta's models · ${tok.toLocaleString("en")} tokens · $${(r.cost?.usd ?? 0).toFixed(3)}</span></summary>
    <div class="tablewrap"><table><thead><tr><th>Agent</th><th>Model</th><th>Effort</th><th>Tokens in / out</th><th>Cost</th><th>What it answered</th></tr></thead><tbody>
    ${log.map((x) => `<tr><td>${esc(x.role || "")}</td><td><span class="chip">${esc(MODEL_NAMES[x.model] || x.model)}</span></td><td>${esc(x.effort || "")}</td>
      <td class="mono">${x.in != null ? (x.in || 0).toLocaleString("en") + " / " + (x.out || 0).toLocaleString("en") : ""}</td><td class="mono">$${(x.usd || 0).toFixed(4)}</td>
      <td class="says">${esc(short(String(x.says || "").replace(/\s+/g, " "), 160))}</td></tr>`).join("")}</tbody></table></div></details>`;
}

function claimFact(c) {
  const lines = [c.place, c.claimed_date, c.event].filter(Boolean).map(esc);
  const how = [c.language ? "Caption in " + esc(LANG(c.language)) : "", c.date_basis ? "Date: " + esc(c.date_basis) : ""].filter(Boolean);
  const src = (c.sources || []).filter((s) => /^https?:/.test(s.url || "")).slice(0, 3);
  return `<div class="fact"><div class="k">The caption says${c.implied ? ' <span class="inferred">date inferred from the post</span>' : ""}</div>
    <div class="v">${lines.length ? lines.join("<br>") : '<span class="nil">No place or date</span>'}</div>
    ${how.length ? `<div class="how">${how.join(" · ")}</div>` : ""}
    ${src.length ? `<div class="how">Read with Muse Spark's web search: ${src.map((s) => ext(s.url, short(s.title || s.url, 40))).join(" · ")}</div>` : ""}</div>`;
}

function showResult(r) {
  (r.cost?.log || []).forEach((x) => { const a = ROLE_AGENT[x.role]; if (a) (CALLS[a] = CALLS[a] || []).push(x); });
  (r.evidence || []).forEach(addEvidence);
  const box = $("#result");
  // Verdict first, next to the post; the agent map moves below, full width, and its log folds into one line.
  $(".right").insertBefore(box, $(".right").firstChild);
  $(".pair").classList.add("done");  // the post is shown inside the verdict now
  $("#mapCard").classList.add("wide");
  $(".pair").after($("#mapCard"));
  box.hidden = false;
  box.className = "card result anim " + r.verdict;
  document.querySelectorAll(".node:not(.done):not(.sent):not(.fail)").forEach((n) => n.classList.add("skipped"));
  if (r.basis === "date rule") {
    const g = $("#node-grounds");
    if (g) { g.classList.remove("skipped"); g.classList.add("notneeded"); g.querySelector("small").textContent = "not needed: the date rule decided"; }
  }
  const c = r.claim || {}, a = r.actual || {}, f = r.first_seen;
  const tl = r.timeline || [];
  const claimDate = c.period_start;
  const gap = r.verdict === "inconsistent" && f && claimDate ? span(f.date, claimDate) : null;
  const postImg = G.post?.media ? `<img src="${esc(G.post.media)}" alt="The post's image">` : "";
  const firstImg = f && f.image_url && /^(https?:|data:image\/)/.test(f.image_url)
    ? `<img src="${esc(f.image_url)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : "";
  const then = r.verdict === "inconsistent" && f ? `<div class="thennow">
      <div class="tn"><div class="tnk">Shared as</div>${postImg}<b>${esc(short([c.place, c.claimed_date].filter(Boolean).join(" · ") || "the caption's claim", 70))}</b>
        <span>${esc(r.post ? "@" + r.post.author + ", " + r.post.posted_on : (G.post?.meta || ""))}</span>
        ${(G.post?.text || c.caption) ? `<q>${esc(short(unquote(G.post?.text || c.caption), 200))}</q>` : ""}</div>
      <div class="tngap"><b class="count" data-to="${esc(gap || "")}">${esc(gap || "")}</b><span>earlier</span></div>
      <div class="tn first"><div class="tnk">First seen</div>${firstImg || postImg}<b>${esc(f.date)} · ${ext(f.url, f.domain)}</b>
        <span>${esc(HOW(f.how))}${f.snapshot ? " · " + ext(f.snapshot, "archived copy") : ""}${f.described ? " · " + esc(short(f.described, 80)) : ""}</span></div></div>` : "";
  const scene = (r.evidence || []).find((e) => e.match === "scene" && e.other_country && (r.cited || []).includes(e.id));
  const sceneThen = r.verdict === "inconsistent" && !f && scene ? `<div class="thennow">
      <div class="tn"><div class="tnk">The post: shared as</div>${postImg}<b>${esc(short(c.place || "", 60))}</b><span>${esc(r.post ? "@" + r.post.author + ", " + r.post.posted_on : "")}</span>
        ${(G.post?.text || c.caption) ? `<q>${esc(short(unquote(G.post?.text || c.caption), 200))}</q>` : ""}</div>
      <div class="tngap"><b>${icon("witness")}</b><span>the same video, at ${vtime(scene.scene_t)}</span></div>
      <div class="tn first"><div class="tnk">What the footage shows</div>${scene.image_url ? `<img src="${esc(scene.image_url)}" alt="The frame with the sign">`
        : `<div class="signcard"><small>a sign on screen at ${vtime(scene.scene_t)}</small><blockquote>${esc(scene.quote)}</blockquote></div>`}
        <b>“${esc(scene.quote)}” → ${esc(scene.described_place)}</b>
        <span>read by Muse Spark, confirmed on the frame by Muse Wonder${!scene.image_url && r.post?.url ? ` · ${ext(r.post.url, "play the post on X")} to see it` : ""}</span>
        ${scene.check_reason ? `<p class="why"><b>Why it settles the place:</b> ${esc(short(scene.check_reason, 260))}</p>` : ""}</div></div>` : "";
  // Fits and Cannot verify get the same two pictures: the post, and the oldest copy the agents kept.
  const dated = (e) => [e.image_first, e.page_published && !WIKI.test(e.domain || "") ? String(e.page_published).slice(0, 10) : null].filter(Boolean).sort()[0];
  const oldest = (r.evidence || []).filter((e) => e.match !== "scene" && dated(e)).sort((p, q) => dated(p) < dated(q) ? -1 : 1)
    .find((e) => (r.cited || []).includes(e.id)) || (r.evidence || []).filter((e) => e.match !== "scene" && dated(e)).sort((p, q) => dated(p) < dated(q) ? -1 : 1)[0];
  const MID = { consistent: ["fits", "the record agrees with the caption"], cannot_tell: ["?", c.place || c.claimed_date ? "not enough proof either way" : "the post names no place or date to test"] };
  const otherThen = r.verdict !== "inconsistent" && oldest && MID[r.verdict] ? `<div class="thennow ${r.verdict}">
      <div class="tn"><div class="tnk">The post: shared as</div>${postImg}<b>${esc(short([c.place, c.claimed_date].filter(Boolean).join(" · ") || "No place or date given", 70))}</b>
        <span>${esc(r.post ? "@" + r.post.author + ", " + r.post.posted_on : (G.post?.meta || ""))}</span>
        ${(G.post?.text || c.caption) ? `<q>${esc(short(unquote(G.post?.text || c.caption), 200))}</q>` : ""}</div>
      <div class="tngap neutral"><b>${MID[r.verdict][0] === "fits" ? icon("consistent") : icon("cannot_tell")}</b><span>${esc(MID[r.verdict][1])}</span></div>
      <div class="tn first"><div class="tnk">${(r.cited || []).includes(oldest.id) ? "Oldest copy the verdict cites" : "Oldest copy found"}</div>${oldest.image_url && /^https?:/.test(oldest.image_url) ? `<img src="${esc(oldest.image_url)}" alt="" referrerpolicy="no-referrer">` : postImg}
        <b>${esc(dated(oldest))} · ${ext(oldest.url, oldest.domain)}</b>
        <span>${esc(short([oldest.described_place, oldest.described_date, oldest.described_event].filter(Boolean).join(" · ") || (MATCH[oldest.match] || [""])[0], 90))}</span></div></div>` : "";
  const compare = r.verdict === "inconsistent" && (a.place || a.date || a.event)
    ? `<div class="compare">${claimFact(c)}<div class="vs">${icon("inconsistent")}</div>${fact("The record says", [a.place, a.date, a.event], "record")}</div>`
    : `<div class="compare single">${claimFact(c)}</div>`;
  let proof = "";
  if (r.basis === "date rule" && r.rule) {
    proof = `<div class="proof">${icon("grounds")}<div><b>Decided by code: the date rule</b><span>The image file was archived on ${ext(r.rule.snapshot, r.rule.image_first)}, ${r.rule.days_before} days before the earliest date the caption allows (${esc(r.rule.period_start)}).${f && f.date < r.rule.image_first ? ` The earliest copy the verdict cites is older still: ${esc(f.date)} (${esc(f.domain)}, ${esc(HOW(f.how))}).` : ""}</span></div></div>`;
  } else if (r.grounds) {
    proof = `<div class="proof ${r.grounds.ok ? "" : "weak"}">${icon(r.grounds.ok ? "grounds" : "alert")}<div><b>${r.grounds.ok ? "Proof checked by code" : "Proof check: not enough"}</b><span>${esc(plainIds(r.grounds.text))}${r.grounds.kind === "the scene itself" ? ". This verdict rests on one sign in the scene, confirmed by a second model; no earlier copy was found." : ""}</span></div></div>`;
  }
  // The critic looks at the cited copies itself before it approves; say how many it compared with the post.
  const checked = String(r.critic?.same_source_checked || "").split(/[;,]\s*/).filter((x) => /:/.test(x));
  if (r.verdict === "inconsistent" && checked.length) {
    const same = checked.filter((x) => /:\s*same\b/i.test(x)).length, none = checked.filter((x) => /no image/i.test(x)).length;
    const pic = (G.inputs || []).some((x) => /frame/.test(x.kind)) || G.post?.video ? "footage" : "image";
    proof += `<div class="proof critic">${icon("critic")}<div><b>Re-checked by Muse Wonder before it approved</b><span>It checked ${checked.length} cited ${checked.length > 1 ? "copies" : "copy"} against the post itself: ${same === checked.length && same > 1 ? "all " + same + " are" : same + (same === 1 ? " is" : " are")} the same ${pic}${none ? `, ${none} had no picture to compare` : ""}.</span></div></div>`;
  }
  const draft = r.verdict === "inconsistent" ? noteDraft(r) : "";
  const notes = draft || r.community_note ? `<div class="notes ${draft && r.community_note ? "two" : ""}">
      ${draft ? `<div class="note draft"><div class="k">Draft Community Note <button type="button" class="copy" data-copy="${esc(draft)}">Copy</button></div><p>${esc(draft)}</p><small class="hint">Written by code from the cited evidence. Check it before posting.</small></div>` : ""}
      ${r.community_note ? `<div class="note human"><div class="k">The real X Community Note on this post</div><p>${esc(r.community_note)}</p><small class="hint">Written by people. Never shown to the agents.</small></div>` : ""}</div>` : "";
  box.innerHTML = `
    <div class="banner"><span class="big">${icon(r.verdict)}</span><div>
      <div class="verdict">${LABEL[r.verdict] || esc(r.verdict)}</div>
      <p class="summary">${esc(r.summary || "")}</p></div></div>
    <div class="rbody">
      ${then || sceneThen || otherThen}
      ${compare}
      ${proof}
      ${debate()}
      ${notes}
      ${tl.filter((t) => t.kind !== "claim").length >= 2 ? `<h3>Timeline <span class="hint">${claimDate ? "every dated copy; grey ones appeared after the claimed date" : "every dated copy the agents found"}</span></h3>${axis(tl, claimDate)}<ol class="tl">${tl.map((t) => `
        <li class="${t.kind}${claimDate && t.kind !== "claim" && t.date > claimDate ? " late" : ""}"><time>${esc(t.date)}</time><span class="tag">${TAG[t.kind] || t.kind}</span><span>${t.url ? ext(t.url, t.text) : esc(t.text)}</span></li>`).join("")}</ol>` : ""}
      ${verifyLinks(r)}
      ${receipt(r)}
      <div class="basis"><span>${esc(BASIS[r.basis] || r.basis || "")}</span>
        ${r.post ? `<span>Post: ${ext(r.post.url, "@" + r.post.author + ", " + r.post.posted_on)}</span>` : ""}
        ${r.mode === "replay" ? "<span>Recorded run, replayed step by step</span>" : ""}</div>
    </div>`;
  box.querySelectorAll(".xembed").forEach(xEmbed);
  wipe(box.querySelector(".thennow"));
  box.querySelectorAll(".axis .pin").forEach((el, i) => { el.style.animationDelay = (1.2 + i * 0.12) + "s"; });
  box.querySelectorAll(".tl li").forEach((el, i) => { el.style.animationDelay = (1.3 + i * 0.06) + "s"; });
  box.querySelectorAll(".copy").forEach((b) => b.addEventListener("click", () => {
    navigator.clipboard?.writeText(b.dataset.copy).then(() => { b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500); });
  }));
  // Evidence: the cited copies first; the rest behind one click.
  const cited = new Set(r.cited || []);
  const cards = [...$("#evidence").children];
  cards.forEach((card) => {
    const id = card.id.slice(3);
    if (cited.has(id)) card.classList.add("cited");
    else card.querySelector(".pic").insertAdjacentHTML("beforeend", '<span class="citedtag muted">Not cited</span>');
  });
  cards.sort((p, q) => cited.has(q.id.slice(3)) - cited.has(p.id.slice(3))).forEach((card) => $("#evidence").appendChild(card));
  const rest = cards.filter((card) => !cited.has(card.id.slice(3)));
  $("#evMore")?.remove();
  if (rest.length > 2) {
    rest.forEach((card) => card.classList.add("folded"));
    $("#evidence").insertAdjacentHTML("afterend", `<button type="button" class="more" id="evMore">Show ${rest.length} more copies the agents checked</button>`);
    $("#evMore").addEventListener("click", () => { rest.forEach((card) => card.classList.remove("folded")); $("#evMore").remove(); });
  }
  // The agents' log folds into one line once the verdict is in.
  const steps = $("#feed").children.length;
  $("#feed").hidden = true;
  $("#logToggle")?.remove();
  $("#feed").insertAdjacentHTML("beforebegin", `<button type="button" class="more" id="logToggle">Show the agents' log (${steps} messages)</button>`);
  $("#logToggle").addEventListener("click", () => { const h = !$("#feed").hidden; $("#feed").hidden = h; $("#logToggle").textContent = h ? `Show the agents' log (${steps} messages)` : "Hide the agents' log"; });
  $("#mapHint").textContent = "done";
  drawGraph(r);
  countUp(box.querySelector(".count"));
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

// When the critic sent the judge back: the exchange between the two models, in order.
function debate() {
  if (!G.sent || !(G.debate || []).length) return "";
  return `<h3>The critic sent the judge back</h3><ol class="debate">${G.debate.map((d) => `
    <li class="${d.who} ${d.who === "critic" ? (d.approve ? "ok" : "no") : ""}"><span class="who">${d.who === "judge" ? "Judge · Muse Spark" : "Critic · Muse Wonder"}</span>
      <span>${esc(short(d.text, 260))}</span></li>`).join("")}</ol>`;
}

// "7 years 1 month" counts up when the verdict appears.
function countUp(el) {
  if (!el) return;
  const target = el.dataset.to, m = target.match(/^(\d+) (years?|months?|days?)(.*)$/);
  if (!m || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const n = +m[1], t0 = performance.now();
  const step = (t) => { const k = Math.min(1, (t - t0) / 900); el.textContent = Math.round(n * k) + " " + m[2] + (k === 1 ? m[3] : ""); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

init();

// The check graph: what was checked, which parts of the media were searched, what was found and kept, and what
// the verdict rests on.
function collect(ev) {
  if (ev.agent === "post" && ev.post) G.post = { media: (ev.thumbs || [])[0] || (ev.post.media_urls || [])[0] || G.post?.media, text: ev.post.text, meta: "@" + ev.post.author };
  if (ev.agent === "frames" && !G.post?.media && (ev.thumbs || []).length) G.post = { ...(G.post || {}), media: ev.thumbs[0] };
  if (ev.agent === "speech") G.speech = ev.transcript || "";
  if (ev.agent === "search") { G.inputs = ev.inputs || []; G.found = ev.count || 0; }
  if (ev.agent === "match") G.checked += ev.checked || 0;
  if (ev.agent === "judge") { G.judge += 1; (G.debate = G.debate || []).push({ who: "judge", text: ev.text }); }
  if (ev.agent === "critic") (G.debate = G.debate || []).push({ who: "critic", text: ev.text, approve: ev.approve !== false });
  if (ev.agent === "critic" && ev.approve === false) G.sent += 1;
  if (ev.agent === "critic") G.approved = ev.approve !== false;
}

const short = (t, n) => {
  t = String(t || ""); if (t.length <= n) return t;
  const cut = t.slice(0, n - 1), sp = cut.lastIndexOf(" ");
  return (sp > n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,;:.(–-]+$/, "") + "…";
};
// A post's text often arrives wrapped in its own quotes; the page adds its own.
const unquote = (t) => String(t || "").trim().replace(/^["“”']+|["“”']+$/g, "");
const LANG = (code) => { let n = code; try { n = new Intl.DisplayNames(["en"], { type: "language" }).of(code) || code; } catch { /* a name, not a code */ } return String(n).charAt(0).toUpperCase() + String(n).slice(1); };
const vtime = (t) => { const s = Math.round(+t || 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
// How a date was found, said plainly.
const HOW = (h) => String(h || "").replace("published (TikTok post id)", "date read from the TikTok video ID")
  .replace("published (X post id)", "date read from the X post ID").replace("published (YouTube upload date)", "YouTube upload date");

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
  const date = (x) => x.image_first ? "archived " + x.image_first : x.page_published ? (WIKI.test(x.domain || "") ? "article created " : "published ") + String(x.page_published).slice(0, 10)
    : x.page_first ? "page archived " + x.page_first : "";
  const badge = (x) => { const [l, k] = MATCH[x.match] || [x.match, ""]; return `<span class="badge ${k}">${esc(l)}</span>`; };
  const media = G.post?.media ? `<img src="${esc(G.post.media)}" alt="">` : "";
  const col1 = `<div class="gcol"><div class="gt">1 · The post</div>
    <div class="gnode post" id="g-post">${media}<div class="gtext">${esc(short(G.post?.text || c.caption, 140))}</div></div>
    <div class="gnode claim ${r.verdict === "inconsistent" ? "" : "neutral"}" id="g-claim"><b>The claim</b>${[c.place, c.claimed_date, c.event].filter(Boolean).map((v) => `<span>${esc(short(v, 60))}</span>`).join("")}</div></div>`;
  const tiles = G.inputs.map((x, i) => `<div class="gnode tile" id="g-in-${i}">${x.thumb ? `<img src="${esc(x.thumb)}" alt="">` : ""}<span>${esc(x.kind)}</span></div>`).join("");
  const col2 = `<div class="gcol"><div class="gt">2 · What was searched</div><div class="tiles">${tiles}</div>
    ${scene.map((x) => `<div class="gnode sign" id="g-${x.id}">${x.image_url ? `<img src="${esc(x.image_url)}" alt="">` : ""}<span>Sign in the scene: “${esc(short(x.quote, 40))}” → ${esc(x.described_place || "")}</span></div>`).join("")}
    ${G.speech ? `<div class="gnode speech" id="g-speech">${icon("speech")}<span>“${esc(short(G.speech, 90))}”</span></div>` : ""}</div>`;
  const col3 = `<div class="gcol"><div class="gt">3 · What was found</div>
    <div class="gsum">${G.found ? `${G.found} page${G.found === 1 ? "" : "s"} found${G.checked ? ` · ${G.checked} look-alikes compared` : ""}` : G.checked ? `${G.checked} look-alikes compared, none the same image` : "no earlier copy found"}</div>
    ${shown.map((x) => `<div class="gnode row ${cited.has(x.id) || x.id === ruleId ? "cited" : ""}" id="g-${x.id}"><div><b>${esc(x.id)}</b> ${esc(short(x.domain, 28))}</div>
      <div class="gmeta">${badge(x)}${date(x) ? `<span class="gdate">${esc(date(x))}</span>` : ""}</div>
      ${x.described_place || x.described_event ? `<div class="gsays">${esc(short([x.described_place, x.described_event].filter(Boolean).join(" · "), 70))}</div>` : ""}</div>`).join("")}
    ${pages.length ? "" : `<div class="gnode gempty">No earlier copy of this ${G.inputs.length > 1 ? "media" : "photo"} found online</div>`}
    ${pages.length > shown.length ? `<div class="gsum dim">+ ${pages.length - shown.length} more kept</div>` : ""}
    ${aside ? `<div class="gsum dim">${aside} set aside: not the same image, or nothing to read or date</div>` : ""}</div>`;
  const ok = r.verdict;
  const g = r.grounds;
  const col4 = `<div class="gcol"><div class="gt">4 · The decision</div>
    <div class="gnode step ${r.basis === "date rule" ? "on" : ""}" id="g-rule">${icon("rule")}<div><b>Date rule</b><span>${r.basis === "date rule" ? `decided: a copy archived ${esc(r.rule?.image_first || "")}` : "not used"}</span></div></div>
    <div class="gnode step ${r.basis !== "date rule" && G.judge ? "on" : ""}" id="g-judge">${icon("judge")}<div><b>Judge · Muse Spark</b><span>${G.judge > 1 ? G.judge + " rounds" : G.judge ? "1 round" : "not needed"}</span></div></div>
    <div class="gnode step ${G.sent ? "warn" : G.approved ? "on" : ""}" id="g-critic">${icon("critic")}<div><b>Critic · Muse Wonder</b><span>${G.sent ? `sent the judge back ${G.sent > 1 ? G.sent + " times" : "once"}${G.approved ? ", then approved" : ""}` : G.approved ? "approved" : "not needed"}</span></div></div>
    ${g ? `<div class="gnode step ${g.ok ? "on" : "warn"}" id="g-grounds">${icon("grounds")}<div><b>Proof check · code</b><span>${g.ok ? esc(short(g.kind, 40)) : "too little proof"}</span></div></div>` : ""}
    <div class="gnode verdict ${ok}" id="g-verdict">${icon(ok)}<b>${LABEL[ok] || ok}</b></div></div>`;
  card.hidden = false;
  $("#graph").innerHTML = `<svg class="glines" id="glines"></svg>${col1}${col2}${col3}${col4}`;
  $("#graph").classList.remove("anim"); void $("#graph").offsetWidth; $("#graph").classList.add("anim");
  G.drawn = false;
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
  // The first time, each line draws itself, from the post to the verdict; on resize they just appear.
  if (!G.drawn && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    G.drawn = true;
    [...svg.querySelectorAll("path")].forEach((p, i) => {
      const len = p.getTotalLength();
      p.style.strokeDasharray = len; p.style.strokeDashoffset = len;
      p.style.animationDelay = (0.4 + i * 0.07) + "s"; p.classList.add("drawing");
    });
    const v = document.getElementById("g-verdict");
    if (v) setTimeout(() => v.classList.add("landed"), 600 + svg.querySelectorAll("path").length * 70);
  }
}
addEventListener("resize", () => requestAnimationFrame(drawLines));

// A post shown with X's own embed: its photo or video comes from X, not from this site.
function xEmbed(el) {
  el.innerHTML = `<blockquote class="twitter-tweet" data-dnt="true" data-conversation="none" data-cards="visible"><a href="${esc(el.dataset.url.replace("x.com", "twitter.com"))}"></a></blockquote>`;
  if (window.twttr?.widgets) return window.twttr.widgets.load(el);
  if (!document.getElementById("xw")) { const sc = document.createElement("script"); sc.id = "xw"; sc.async = true; sc.src = "https://platform.twitter.com/widgets.js"; document.body.appendChild(sc); }
}

// The agent map: rest the pointer on an agent (or tap it) to read what it did in this check.
function tipHtml(node) {
  const id = node.id.replace("node-", ""), name = node.querySelector("b").textContent, by = node.querySelector("small").textContent;
  const notes = NOTES[id] || [], calls = CALLS[id] || [];
  const head = `<div class="tip-h"><b>${esc(name)}</b><span class="chip ${IS_META(by) ? "" : "tool"}">${esc(by)}</span></div>`;
  if (!notes.length && !calls.length) {
    return head + `<p class="tip-nil">${node.classList.contains("running") ? "Working on it…" : "Not needed in this check."}</p>`;
  }
  const said = notes.slice(-4).map((n) => `<li class="${n.sent ? "sent" : ""}">${esc(short(n.text || "", 260))}</li>`).join("");
  const thumbs = notes.flatMap((n) => n.thumbs).slice(0, 3);
  const tok = calls.reduce((t, x) => t + (x.in || 0) + (x.out || 0), 0), usd = calls.reduce((t, x) => t + (x.usd || 0), 0);
  const answers = calls.filter((x) => x.says).slice(0, 3).map((x) => `<li><span class="mono">${esc(MODEL_NAMES[x.model] || x.model)}</span> ${esc(short(String(x.says).replace(/\s+/g, " "), 180))}</li>`).join("");
  return head + (said ? `<ul class="tip-said">${said}</ul>` : "")
    + (thumbs.length ? `<div class="tip-thumbs">${thumbs.map((t) => `<img src="${t}" alt="">`).join("")}</div>` : "")
    + (answers ? `<div class="tip-k">What the model answered${calls.length > 3 ? ` (3 of ${calls.length})` : ""}</div><ul class="tip-ans">${answers}</ul>` : "")
    + (calls.length ? `<div class="tip-foot mono">${calls.length} call${calls.length > 1 ? "s" : ""} · ${tok.toLocaleString("en")} tokens · $${usd.toFixed(4)}</div>` : "");
}
function showTip(node) {
  let tip = $("#nodeTip");
  if (!tip) { tip = document.createElement("div"); tip.id = "nodeTip"; tip.setAttribute("role", "tooltip"); document.body.appendChild(tip); }
  tip.innerHTML = tipHtml(node);
  tip.classList.add("on");
  const r = node.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  let left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
  let top = r.bottom + 8;
  if (top + h > innerHeight - 8 && r.top - h - 8 > 8) top = r.top - h - 8;
  tip.style.left = left + scrollX + "px"; tip.style.top = top + scrollY + "px";
}
function hideTip() { $("#nodeTip")?.classList.remove("on"); }
document.addEventListener("mouseover", (e) => { const n = e.target.closest?.(".node"); if (n) showTip(n); });
document.addEventListener("mouseout", (e) => { const n = e.target.closest?.(".node"); if (n && !n.contains(e.relatedTarget)) hideTip(); });
document.addEventListener("click", (e) => { const n = e.target.closest?.(".node"); if (n) showTip(n); else if (!e.target.closest?.("#nodeTip")) hideTip(); });
addEventListener("scroll", hideTip, { passive: true });
