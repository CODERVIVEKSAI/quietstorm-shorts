// QuietStorm dashboard — talks to the GitHub API to fetch and trigger workflow runs.
// Stores PAT in localStorage. Extracts MP4s from artifact ZIPs client-side.

const OWNER = "CODERVIVEKSAI";
const REPO = "quietstorm-shorts";
const API = "https://api.github.com";

const WORKFLOWS = {
  daily: "scheduled.yml",
  custom: "custom.yml",
  edit: "edit.yml",
};

const PAT_KEY = "qs_pat";

// ---------- helpers ----------

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function getPAT() {
  return localStorage.getItem(PAT_KEY);
}
function setPAT(v) {
  localStorage.setItem(PAT_KEY, v);
}
function clearPAT() {
  localStorage.removeItem(PAT_KEY);
}

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  setTimeout(() => t.classList.add("hidden"), 4000);
}

async function api(path, opts = {}) {
  const pat = getPAT();
  if (!pat) throw new Error("no PAT — open settings");
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${pat}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${txt.slice(0, 200)}`);
  }
  return res;
}

// ---------- runs + artifacts ----------

async function fetchRecentRuns(workflowFile, limit = 10) {
  const res = await api(
    `/repos/${OWNER}/${REPO}/actions/workflows/${workflowFile}/runs?per_page=${limit}`
  );
  const data = await res.json();
  return data.workflow_runs || [];
}

async function fetchArtifacts(runId) {
  const res = await api(`/repos/${OWNER}/${REPO}/actions/runs/${runId}/artifacts`);
  const data = await res.json();
  return data.artifacts || [];
}

// Download a single artifact (returns Blob of zip)
async function downloadArtifact(artifactId) {
  const res = await api(
    `/repos/${OWNER}/${REPO}/actions/artifacts/${artifactId}/zip`
  );
  return await res.blob();
}

// Extract video.mp4 from a zip blob and return a blob URL
async function extractVideo(zipBlob) {
  const zip = await JSZip.loadAsync(zipBlob);
  const file = zip.file("video.mp4");
  if (!file) throw new Error("video.mp4 not found in artifact");
  const mp4Blob = await file.async("blob");
  const meta = zip.file("metadata.json");
  let metadata = null;
  if (meta) metadata = JSON.parse(await meta.async("string"));
  return {
    url: URL.createObjectURL(new Blob([mp4Blob], { type: "video/mp4" })),
    metadata,
  };
}

// Parse format name from artifact name like "video-quote-20260425"
function formatFromArtifact(name) {
  const m = name.match(/^video-([a-z_]+)-/);
  return m ? m[1] : "unknown";
}

// ---------- dispatching workflows ----------

async function triggerWorkflow(workflowFile, inputs = {}) {
  await api(`/repos/${OWNER}/${REPO}/actions/workflows/${workflowFile}/dispatches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs }),
  });
}

// ---------- rendering ----------

function videoCard({ url, format, metadata, runId }) {
  const card = document.createElement("div");
  card.className = "video-card";
  const title = (metadata && metadata.title) || format;
  card.innerHTML = `
    <video controls preload="metadata" playsinline></video>
    <div class="meta">
      <span class="format-tag">${format}</span>
      <div class="title">${escapeHtml(title)}</div>
      <div class="actions">
        <a class="btn-mini" href="${url}" download="${format}.mp4">download</a>
        <button class="btn-mini edit-btn" data-format="${format}" data-run="${runId}">edit</button>
      </div>
    </div>
  `;
  card.querySelector("video").src = url;
  card.querySelector(".edit-btn").addEventListener("click", () => {
    openEditModal(format, runId);
  });
  return card;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function loadToday() {
  const grid = $("#today-grid");
  grid.innerHTML = '<p class="muted"><span class="loading"></span>loading latest run…</p>';
  $("#today-empty").classList.add("hidden");

  let runs;
  try {
    runs = await fetchRecentRuns(WORKFLOWS.daily, 5);
  } catch (e) {
    grid.innerHTML = "";
    toast(`fetch failed: ${e.message}`, "error");
    return;
  }

  const latest = runs.find((r) => r.status === "completed" && r.conclusion === "success");
  if (!latest) {
    grid.innerHTML = "";
    $("#today-empty").classList.remove("hidden");
    return;
  }

  $("#today-date").textContent = new Date(latest.run_started_at).toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });

  const arts = await fetchArtifacts(latest.id);
  grid.innerHTML = "";
  if (!arts.length) {
    grid.innerHTML = '<p class="muted">no artifacts (expired after 7 days?)</p>';
    return;
  }

  // Process in parallel
  await Promise.all(arts.map(async (art) => {
    const placeholder = document.createElement("div");
    placeholder.className = "video-card";
    placeholder.innerHTML = `<div class="meta"><span class="loading"></span>loading ${escapeHtml(art.name)}…</div>`;
    grid.appendChild(placeholder);

    try {
      const blob = await downloadArtifact(art.id);
      const { url, metadata } = await extractVideo(blob);
      const card = videoCard({
        url,
        format: formatFromArtifact(art.name),
        metadata,
        runId: latest.id,
      });
      placeholder.replaceWith(card);
    } catch (e) {
      placeholder.innerHTML = `<div class="meta muted small">⚠ ${escapeHtml(art.name)}: ${escapeHtml(e.message)}</div>`;
    }
  }));
}

// Estimated wall-clock duration per workflow (used for ETA bars)
const ESTIMATED_SECONDS = {
  "Daily Shorts": 10 * 60,
  "Custom Video": 5 * 60,
  "Edit Video": 5 * 60,
};

let progressPollHandle = null;
let progressTickHandle = null;

function fmtElapsed(secs) {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

async function loadInProgress() {
  let allRuns = [];
  for (const wf of Object.values(WORKFLOWS)) {
    try {
      const runs = await fetchRecentRuns(wf, 5);
      allRuns = allRuns.concat(runs);
    } catch { /* ignore */ }
  }
  const active = allRuns.filter((r) => r.status === "in_progress" || r.status === "queued");

  const section = $("#in-progress");
  const list = $("#progress-list");
  const count = $("#progress-count");

  if (!active.length) {
    section.classList.add("hidden");
    list.innerHTML = "";
    count.textContent = "";
    stopProgressPolling();
    return;
  }

  section.classList.remove("hidden");
  count.textContent = `${active.length} active`;

  // Diff: only re-render if the set of run IDs changed
  const newIds = active.map((r) => r.id).sort().join(",");
  if (list.dataset.runIds === newIds) {
    // Same runs — just update the live ticker via tickProgress()
    return;
  }
  list.dataset.runIds = newIds;
  list.innerHTML = "";

  for (const run of active) {
    const card = document.createElement("div");
    card.className = "progress-card";
    card.dataset.startedAt = run.run_started_at;
    card.dataset.estimated = ESTIMATED_SECONDS[run.name] || 5 * 60;
    card.innerHTML = `
      <div class="top">
        <div class="label">
          <span class="kind">${escapeHtml(run.name)}</span>
          <span class="status-text">${run.status === "queued" ? "queued..." : "generating..."}</span>
        </div>
        <a class="open-link" href="${run.html_url}" target="_blank" rel="noopener">open ↗</a>
      </div>
      <div class="times">
        <span class="elapsed">0s</span> elapsed · <span class="eta">~5m</span> remaining
      </div>
      <div class="bar"><div class="bar-fill" style="width:0%"></div></div>
    `;
    list.appendChild(card);
  }
  tickProgress();  // immediate first tick
  startProgressPolling();
}

function tickProgress() {
  document.querySelectorAll(".progress-card").forEach((card) => {
    const startedAt = new Date(card.dataset.startedAt).getTime();
    const estimatedSec = parseInt(card.dataset.estimated, 10);
    const elapsedSec = Math.max(0, (Date.now() - startedAt) / 1000);
    const remainingSec = Math.max(0, estimatedSec - elapsedSec);
    const pct = Math.min(95, (elapsedSec / estimatedSec) * 100);  // cap at 95% so it doesn't look done

    card.querySelector(".elapsed").textContent = fmtElapsed(elapsedSec);
    card.querySelector(".eta").textContent =
      remainingSec > 0 ? `~${fmtElapsed(remainingSec)}` : "wrapping up...";
    card.querySelector(".bar-fill").style.width = `${pct}%`;
  });
}

function startProgressPolling() {
  // Local ticker every second to update elapsed/ETA
  if (!progressTickHandle) {
    progressTickHandle = setInterval(tickProgress, 1000);
  }
  // Server poll every 15 seconds to detect completion + new runs
  if (!progressPollHandle) {
    progressPollHandle = setInterval(async () => {
      const before = $("#progress-list").dataset.runIds;
      await loadInProgress();
      const after = $("#progress-list").dataset.runIds;
      if (before && before !== after) {
        // Something completed or started — refresh today/recent
        loadToday();
        loadRecent();
      }
    }, 15000);
  }
}

function stopProgressPolling() {
  if (progressTickHandle) { clearInterval(progressTickHandle); progressTickHandle = null; }
  if (progressPollHandle) { clearInterval(progressPollHandle); progressPollHandle = null; }
}

// Lazy-loaded recents: cards show metadata + ▶ button, video downloads only on click.
// Avoids downloading 50-100MB of artifact zips on every page load.
async function loadRecent() {
  const grid = $("#recent-grid");
  const countLabel = $("#recent-count");
  grid.innerHTML = '<p class="muted"><span class="loading"></span>loading recent…</p>';
  $("#recent-empty").classList.add("hidden");

  let customRuns = [], editRuns = [];
  try {
    [customRuns, editRuns] = await Promise.all([
      fetchRecentRuns(WORKFLOWS.custom, 5),
      fetchRecentRuns(WORKFLOWS.edit, 5),
    ]);
  } catch (e) {
    grid.innerHTML = "";
    return;
  }

  const all = [...customRuns, ...editRuns]
    .filter((r) => r.status === "completed" && r.conclusion === "success")
    .sort((a, b) => new Date(b.run_started_at) - new Date(a.run_started_at))
    .slice(0, 6);

  if (!all.length) {
    grid.innerHTML = "";
    $("#recent-empty").classList.remove("hidden");
    countLabel.textContent = "";
    return;
  }

  countLabel.textContent = `${all.length} · click to load`;
  grid.innerHTML = "";

  for (const run of all) {
    const card = document.createElement("div");
    card.className = "video-card";
    const dateStr = new Date(run.run_started_at).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
    const kind = run.name === "Custom Video" ? "custom" : "edit";
    card.innerHTML = `
      <div class="play-poster" style="aspect-ratio:9/16;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#1a1a25,#10101a);cursor:pointer;">
        <span style="font-size:3rem;opacity:0.7;">▶</span>
      </div>
      <div class="meta">
        <span class="format-tag">${kind}</span>
        <div class="title">${dateStr}</div>
      </div>
    `;
    const poster = card.querySelector(".play-poster");
    poster.addEventListener("click", async () => {
      poster.innerHTML = '<span class="loading"></span><span style="margin-left:6px;color:var(--muted);">loading…</span>';
      try {
        const arts = await fetchArtifacts(run.id);
        if (!arts.length) throw new Error("artifact expired");
        const art = arts[0];
        const blob = await downloadArtifact(art.id);
        const { url, metadata } = await extractVideo(blob);
        const replacement = videoCard({
          url,
          format: `${kind} · ${formatFromArtifact(art.name)}`,
          metadata: metadata || { title: dateStr },
          runId: run.id,
        });
        card.replaceWith(replacement);
      } catch (e) {
        poster.innerHTML = `<span style="color:var(--red);font-size:0.85rem;padding:8px;text-align:center;">⚠ ${escapeHtml(e.message)}</span>`;
      }
    });
    grid.appendChild(card);
  }
}

async function loadHistory() {
  const list = $("#history-list");
  list.innerHTML = '<p class="muted"><span class="loading"></span>loading…</p>';

  // All workflow types combined
  let all = [];
  for (const wf of Object.values(WORKFLOWS)) {
    try {
      const runs = await fetchRecentRuns(wf, 5);
      all = all.concat(runs);
    } catch { /* ignore individual workflow errors */ }
  }
  all.sort((a, b) => new Date(b.run_started_at) - new Date(a.run_started_at));
  all = all.slice(0, 20);

  if (!all.length) {
    list.innerHTML = '<p class="muted">no runs yet.</p>';
    return;
  }

  list.innerHTML = "";
  for (const run of all) {
    const row = document.createElement("div");
    row.className = "run-row";
    const date = new Date(run.run_started_at);
    const dateStr = date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
    const statusClass = run.conclusion || run.status;
    row.innerHTML = `
      <div class="info">
        <div class="date">${dateStr} · <span class="muted small">${escapeHtml(run.name)}</span></div>
        <div class="status ${statusClass}">${run.status}${run.conclusion ? " · " + run.conclusion : ""}</div>
      </div>
      <a class="btn-mini" href="${run.html_url}" target="_blank" rel="noopener">open</a>
    `;
    list.appendChild(row);
  }
}

// ---------- modal flows ----------

function openSetup() {
  $("#setup-modal").classList.remove("hidden");
  $("#pat-input").value = getPAT() || "";
  $("#pat-input").focus();
}
function closeSetup() {
  $("#setup-modal").classList.add("hidden");
}

function openCustom() {
  $("#custom-modal").classList.remove("hidden");
  $("#custom-prompt").value = "";
  $("#custom-prompt").focus();
}
function closeCustom() {
  $("#custom-modal").classList.add("hidden");
}

let currentEdit = null;
function openEditModal(format, runId) {
  currentEdit = { format, runId };
  $("#edit-target").textContent = `format: ${format} · source run: ${runId}`;
  $("#edit-prompt").value = "";
  $("#edit-modal").classList.remove("hidden");
  $("#edit-prompt").focus();
}
function closeEdit() {
  $("#edit-modal").classList.add("hidden");
  currentEdit = null;
}

// ---------- wire up ----------

window.addEventListener("DOMContentLoaded", async () => {
  // Wait for JSZip
  await new Promise((r) => {
    if (window.JSZip) return r();
    const interval = setInterval(() => {
      if (window.JSZip) { clearInterval(interval); r(); }
    }, 50);
  });

  if (!getPAT()) {
    openSetup();
  } else {
    refresh();
  }

  $("#refresh-btn").addEventListener("click", refresh);
  $("#settings-btn").addEventListener("click", openSetup);
  $("#trigger-daily").addEventListener("click", async () => {
    try {
      await triggerWorkflow(WORKFLOWS.daily);
      toast("triggered. comes back in ~10 min.", "success");
      setTimeout(loadInProgress, 3000);
    } catch (e) {
      toast(`failed: ${e.message}`, "error");
    }
  });

  $("#history-toggle").addEventListener("click", () => {
    const open = $("#history-toggle").classList.toggle("open");
    $("#history-list").classList.toggle("hidden", !open);
    if (open) loadHistory();
  });

  $("#pat-save").addEventListener("click", () => {
    const v = $("#pat-input").value.trim();
    if (!v) return toast("paste your token", "error");
    setPAT(v);
    closeSetup();
    toast("saved. loading…", "success");
    refresh();
  });

  $("#custom-btn").addEventListener("click", openCustom);
  $("#custom-cancel").addEventListener("click", closeCustom);
  $("#custom-submit").addEventListener("click", async () => {
    const prompt = $("#custom-prompt").value.trim();
    if (!prompt) return toast("write a prompt", "error");
    const inputs = {
      prompt,
      tone: $("#opt-tone").value,
      length: $("#opt-length").value,
      visual_style: $("#opt-visual").value,
      mood: $("#opt-mood").value,
      voice: $("#opt-voice").value,
    };
    try {
      await triggerWorkflow(WORKFLOWS.custom, inputs);
      closeCustom();
      toast("custom video queued. ~5 min.", "success");
      setTimeout(loadInProgress, 3000);  // give GitHub a moment to register the run
    } catch (e) {
      toast(`failed: ${e.message}`, "error");
    }
  });

  $("#edit-cancel").addEventListener("click", closeEdit);
  $("#edit-submit").addEventListener("click", async () => {
    const editPrompt = $("#edit-prompt").value.trim();
    if (!editPrompt || !currentEdit) return toast("write an edit prompt", "error");
    try {
      await triggerWorkflow(WORKFLOWS.edit, {
        format: currentEdit.format,
        edit_prompt: editPrompt,
        source_artifact_run: String(currentEdit.runId),
      });
      closeEdit();
      toast("edit queued. ~5 min.", "success");
      setTimeout(loadInProgress, 3000);
    } catch (e) {
      toast(`failed: ${e.message}`, "error");
    }
  });

  // dismiss modals on backdrop click
  $$(".modal").forEach((m) => {
    m.addEventListener("click", (e) => {
      if (e.target === m) m.classList.add("hidden");
    });
  });
});

async function refresh() {
  try {
    await Promise.all([loadInProgress(), loadToday(), loadRecent()]);
    if ($("#history-toggle").classList.contains("open")) {
      await loadHistory();
    }
  } catch (e) {
    toast(e.message, "error");
  }
}
