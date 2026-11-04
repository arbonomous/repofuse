/* RepoFuse Studio.
   Two honest modes:
   - LIVE (free stages): your pasted repos are really cloned, pinned,
     license-checked, analyzed, and safety-qualified (static scan,
     dependency inventory, live OSV advisory) by the local server. A
     failed or unknown required check stops the run here. Stops at the
     paid boundary (model calls disabled).
   - REPLAY: only for the recorded microdot+peewee notes run (2026-11-04);
     replays its real artifacts, with the AI's original bytes and the
     assistant's later repairs/extensions clearly separated. */
(function () {
  const R = window.REPLAY;
  const qs = new URLSearchParams(location.search);
  const FREEZE = qs.get("freeze");
  const SPEED = FREEZE ? 0 : parseFloat(qs.get("speed") || "1");
  const wait = (ms) => new Promise(r => setTimeout(r, ms / (SPEED || 1)));
  if (FREEZE) document.body.classList.add("freeze");

  const $ = (s) => document.querySelector(s);
  function setBadge(text, cls) {
    const b = $("#replay-badge");
    b.innerHTML = `<span class="dot"></span> ${text}`;
    b.className = "replay-badge " + cls;
  }
  const show = (id) => {
    document.querySelectorAll(".screen").forEach(el => el.classList.remove("active"));
    $(id).classList.add("active");
  };
  const norm = (u) => (u || "").trim().toLowerCase().replace(/\/+$/, "").replace(/\.git$/, "");
  const inputsMatchRecorded = () => {
    const a = norm($("#repo-a").value), b = norm($("#repo-b").value);
    const ra = norm(R.recorded_inputs.repo_a), rb = norm(R.recorded_inputs.repo_b);
    const intent = $("#intent").value.trim();
    return ({[a]:1,[b]:1}[ra] && {[a]:1,[b]:1}[rb]) &&
           (intent === "" || /notes?/i.test(intent));
  };

  /* ---------------- modal ---------------- */
  $("#whats-real-btn").onclick = () => {
    $("#modal-body").innerHTML = `
      <p><b>Two modes, both honest:</b></p>
      <ul>
        <li><b>Fuse repositories</b> really clones, pins, license-checks and analyzes
          the repos you paste, on your machine, right now. It stops before the model
          stages - those need a paid model call, which is disabled here.</li>
        <li><b>Replay the recorded run</b> (only for the pinned microdot + peewee
          notes build) replays the real artifacts of 2026-11-04: the model's original
          code, its real 4/4 failure, and the assistant's labeled repair and
          edit/delete extension that made it pass.</li>
        <li><b>Notes preview</b> on the result screen talks to the <b>real verified
          app</b> running locally (microdot + peewee + SQLite) - not a browser
          simulation.</li>
        <li><b>Not claimed:</b> unattended AI fusion. The unedited model output failed;
          the working app is assistant-repaired and assistant-extended.</li>
      </ul>`;
    $("#modal-backdrop").hidden = false;
  };
  $("#modal-close").onclick = () => ($("#modal-backdrop").hidden = true);
  $("#modal-backdrop").onclick = (e) => { if (e.target.id === "modal-backdrop") e.target.hidden = true; };

  /* ---------------- stage rail ---------------- */
  let railStages = [];
  function buildRail(stages) {
    railStages = stages;
    const rail = $("#stage-rail");
    rail.innerHTML = "";
    stages.forEach((s, i) => {
      const el = document.createElement("div");
      el.className = "stage pending" + (s.assistant ? " assistant" : "");
      el.id = "stage-" + s.id;
      el.innerHTML = `<div class="stage-name"><span class="icon">&#9675;</span>${i + 1}. ${s.label}</div>
                      <div class="stage-meta"></div>`;
      rail.appendChild(el);
    });
  }
  function setStage(id, state, meta) {
    const el = $("#stage-" + id);
    if (!el) return;
    el.className = "stage " + state + (railStages.find(s => s.id === id)?.assistant ? " assistant" : "");
    const icon = el.querySelector(".icon");
    icon.innerHTML = state === "done" ? "&#10003;" : state === "failed" ? "&#10007;"
      : state === "running" ? "&#10227;" : state === "blocked" ? "&#10073;" : "&#9675;";
    if (meta !== undefined) el.querySelector(".stage-meta").textContent = meta;
  }

  /* ---------------- log ---------------- */
  const logEl = $("#build-log");
  function logText(text, cls) {
    // Server-supplied values (repo names, findings, verdict notes) are
    // UNTRUSTED: they render as text, never markup.
    const line = document.createElement("div");
    line.className = "log-line" + (cls ? " " + cls : "");
    line.textContent = text;
    logEl.appendChild(line);
  }
  function log(html) {
    const line = document.createElement("div");
    line.className = "log-line";
    line.innerHTML = html;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }
  function verdict(html, kind) {
    const el = document.createElement("div");
    el.className = "log-verdict " + kind;
    el.innerHTML = html;
    logEl.appendChild(el);
    logEl.scrollTop = logEl.scrollHeight;
  }

  /* ---------------- graph ---------------- */
  const svg = $("#graph");
  const NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    (parent || svg).appendChild(e);
    return e;
  }
  function text(x, y, str, cls, parent) {
    const t = el("text", { x, y, class: cls }, parent);
    t.textContent = str;
    return t;
  }
  // progress: {repos, exports, app, planEdges, extEdges, repoData}
  function drawGraph(progress) {
    svg.innerHTML = "";
    const repos = progress.repoData || R.repos;
    repos.forEach((r, i) => {
      const y = 56 + i * 180;
      const g = el("g", { opacity: progress.repos ? 1 : 0 });
      el("rect", { x: 20, y, width: 224, height: 112, rx: 12, class: "node-box" }, g);
      text(38, y + 28, r.name, "node-title", g);
      text(38, y + 46, "pin " + (r.commit || "").slice(0, 12), "node-sub", g);
      text(38, y + 62, (r.license || "?") + (r.version ? " \u00b7 declared v" + r.version : "") + (r.role ? " \u00b7 " + r.role : ""), "node-sub", g);
      if (progress.exports) {
        (r.exports || []).slice(0, 4).forEach((x, j) => {
          const cx = 30 + (j % 2) * 108, cy = y + 72 + Math.floor(j / 2) * 22;
          el("rect", { x: cx, y: cy, width: 100, height: 17, rx: 8, class: "chip" }, g);
          text(cx + 8, cy + 12.5, x.length > 13 ? x.slice(0, 12) + "\u2026" : x, "chip-text", g);
        });
      }
    });
    if (!progress.app) return;
    const g = el("g", {});
    el("rect", { x: 630, y: 100, width: 250, height: 210, rx: 12, class: "node-box hot" }, g);
    text(648, 128, "generated/app.py", "node-title", g);
    text(648, 148, "fused notes API", "node-sub", g);
    text(648, 172, "+ test_fused.py", "node-sub", g);
    text(648, 192, "+ assistant_ext.py (edit/delete)", "node-sub", g);
    const edges = R.bridges.filter(b =>
      b.by === "model" ? progress.planEdges : progress.extEdges)
      .slice()
      .sort((a, b2) => (a.from.startsWith("microdot") ? 0 : 1) -
                       (b2.from.startsWith("microdot") ? 0 : 1));
    edges.forEach((b, j) => {
      const srcY = b.from.startsWith("microdot") ? 112 : 292;
      const dstY = 122 + j * 27;
      const dashed = b.by !== "model";
      const p = el("path", {
        d: `M 244 ${srcY} C 420 ${srcY}, 440 ${dstY}, 630 ${dstY}`,
        class: "edge" + (dashed ? " edge-assistant" : ""), id: "edge-" + j,
      });
      const lbl = text(614, dstY - 9,
           b.from.split(":")[1] + " \u2192 " + b.to + (dashed ? "  (assistant, later)" : ""),
           "edge-label" + (dashed ? " edge-label-assistant" : ""));
      lbl.setAttribute("text-anchor", "end");
      setTimeout(() => p.classList.add("drawn"), FREEZE ? 0 : j * 200 / SPEED);
      if (FREEZE) p.classList.add("drawn");
    });
    text(20, 404,
      "Illustrated map of the final repaired app (assistant-drawn). Not the verbatim recorded AI plan - that is shown raw in the code panel.",
      "graph-caption", g);
  }

  /* ---------------- code panel ---------------- */
  let typing = null;
  function setTabs(active, labels) {
    $("#code-tabs").innerHTML = "";
    labels.forEach(name => {
      const t = document.createElement("div");
      t.className = "code-tab" + (name === active ? " active" : "");
      t.textContent = name;
      $("#code-tabs").appendChild(t);
    });
  }
  function typeCode(tab, labels, code, maxChars) {
    setTabs(tab, labels);
    const view = $("#code-content");
    const target = maxChars ? code.slice(0, maxChars) : code;
    if (typing) cancelAnimationFrame(typing);
    if (FREEZE) { view.textContent = target; return; }
    let i = 0;
    const step = Math.max(4, Math.floor(target.length / 240));
    (function tick() {
      i = Math.min(target.length, i + step);
      view.textContent = target.slice(0, i);
      $("#code-view").scrollTop = $("#code-view").scrollHeight;
      if (i < target.length) typing = requestAnimationFrame(tick);
    })();
  }
  const tokenMeter = (html) => ($("#token-meter").innerHTML = html);
  const CODE_TABS = ["generated/app.py", "test_fused.py", "assistant_ext.py"];

  /* ---------------- idea cards (from real local analysis, no model) ---------------- */
  function renderIdeaCards(cards, recordedPair, source, provenance, paidAttempt) {
    lastIdeas = { cards, recordedPair, source, provenance, paidAttempt };
    const box = $("#ideas-cards");
    $("#code-tabs").innerHTML = "";
    $("#code-content").textContent = "";
    $("#code-view").classList.add("hidden");
    box.classList.remove("hidden");
    const fromModel = source && source.indexOf("model:") === 0;
    const head = fromModel
      ? `SUGGESTED BY ${source.slice(6).toUpperCase()} - 1 paid model call` +
        (provenance && provenance.usage
          ? ` (${provenance.usage.input} in / ${provenance.usage.output} out)` : "")
      : paidAttempt && paidAttempt.spent === true
        ? "SUGGESTED FROM THE REAL ANALYSIS - local fallback - 1 paid call made, output rejected"
        : paidAttempt && paidAttempt.spent === null
          ? "SUGGESTED FROM THE REAL ANALYSIS - local fallback - paid call state UNKNOWN"
          : "SUGGESTED FROM THE REAL ANALYSIS - local, no model call";
    box.innerHTML = `<div class="idea-head">${head}</div>` +
      (fromModel
        ? `<div class="idea-head">Ideas are proposals, not built or tested apps. Their security has not been reviewed.</div>`
        : "");
    cards.forEach(c => {
      const b = document.createElement("button");
      b.className = "idea-card";
      b.innerHTML = `<h4>${c.title}</h4><p>${c.what}</p>` +
        `<div class="idea-fit"><b>why these repos:</b> ${c.fit.join(" + ")}</div>`;
      b.onclick = () => pickIdea(c, recordedPair);
      box.appendChild(b);
    });
  }

  let lastIdeas = null;
  let buildInputDesc = null;  // truthful provenance of the build input card
  function pickIdea(card, recordedPair) {
    log(`You picked: <span class="hl">${card.title}</span>`);
    if (recordedPair && card.id === "notes-crud") {
      // This exact build is the recorded run. OFFER the replay explicitly;
      // never silently switch into REPLAY as if a new build started.
      const box = $("#ideas-cards");
      box.innerHTML = `<div class="idea-head">THIS EXACT BUILD WAS RECORDED - your choice</div>` +
        `<div class="idea-offer"><p>A notes API fused from pinned microdot 2.7.0 + peewee (declared 4.5.3) ` +
        `was really built on 2026-11-04, including its paid model stages. Nothing new will be ` +
        `generated - you can watch the recording of that real run: the original AI output, its ` +
        `acceptance failure, and the labeled assistant repair.</p>` +
        `<div class="offer-actions"><button class="offer-replay">Watch the recorded replay</button>` +
        `<button class="offer-back">Back to ideas</button></div></div>`;
      box.querySelector(".offer-replay").onclick = () => {
        log(`Watching the <span class="hl">recorded replay</span> of the 2026-11-04 notes build.`);
        $("#ideas-cards").classList.add("hidden");
        $("#code-view").classList.remove("hidden");
        runReplay();
      };
      box.querySelector(".offer-back").onclick = () => {
        if (lastIdeas) renderIdeaCards(lastIdeas.cards, lastIdeas.recordedPair,
                                       lastIdeas.source, lastIdeas.provenance);
      };
      return;
    }
    $("#ideas-cards").classList.add("hidden");
    $("#code-view").classList.remove("hidden");
    startBuild(card);
  }

  function startBuild(card) {
    if (!lastRunId) return;
    const li = lastIdeas || {};
    buildInputDesc = (li.source && li.source.indexOf("model:") === 0)
      ? "the AI-suggested idea you picked"
      : "a locally-generated analysis card you picked (no model call produced it)";
    setStage("architecture", "running");
    log(`Building <span class="hl">${card.title}</span> - the repos get re-pinned at the exact commits from this run; each model stage is honestly gated.`);
    fetch("/api/build", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: lastRunId, card }),
    }).then(r => r.json()).then(resp => {
      if (resp.error) { verdict(resp.error, "fail"); return; }
      pollLive(lastRunId, liveSeen);
    }).catch(e => verdict(`build request failed honestly: ${e}`, "fail"));
  }

  function resumeBuild(runId) {
    setStage("verify", "running", "re-hash + acceptance");
    log(`Resuming <span class="hl">${runId}</span> - <span class="hl">no generation</span>: the retained bytes are re-hashed against the review manifest, then the reviewed acceptance tests run.`);
    fetch("/api/build/resume", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId }),
    }).then(r => r.json()).then(resp => {
      if (resp.error) { verdict(`resume refused honestly: ${resp.error}`, "fail"); setStage("verify", "blocked", "awaiting source review"); return; }
      pollLive(runId, liveSeen);
    }).catch(e => verdict(`resume request failed honestly: ${e}`, "fail"));
  }

  /* ================= LIVE MODE (real free stages) ================= */
  async function startLive() {
    const repoA = $("#repo-a").value, repoB = $("#repo-b").value, intent = $("#intent").value;
    const resp = await fetch("/api/fuse", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_a: repoA, repo_b: repoB, intent }),
    }).then(r => r.json());
    lastRunId = resp.run_id; liveSeen = 0;
    setBadge("LIVE &middot; free stages &middot; 0 model calls", "live");
    show("#screen-build");
    buildRail([
      { id: "ingest", label: "Ingest (real)" },
      { id: "analyze", label: "Analyze (real)" },
      { id: "safety", label: "Safety checks (real)" },
      { id: "architecture", label: "Architecture" },
      { id: "glue", label: "Glue synthesis" },
      { id: "tests", label: "Test synthesis" },
      { id: "verify", label: "Verify" },
    ]);
    drawGraph({});
    logEl.innerHTML = "";
    $("#code-content").textContent = "";
    $("#ideas-cards").classList.add("hidden");
    $("#code-view").classList.remove("hidden");
    setStage("ingest", "running");
    setStage("safety", "pending");
    setStage("architecture", "pending");
    log(`Run <span class="hl">${resp.run_id}</span> started - <span class="hl">real free stages</span>, paid generation disabled.`);
    if (resp.recorded_pair)
      log(`This pair matches the recorded run - the <span class="hl">Replay</span> mode shows its full paid pipeline.`);
    await pollLive(resp.run_id);
  }

  let lastRunId = null;
  let liveSeen = 0;
  async function pollLive(runId, startSeen = 0) {
    let seen = startSeen;
    const repoLive = [];
    for (;;) {
      const snap = await fetch("/api/run/" + runId).then(r => r.json());
      for (; seen < snap.events.length; seen++) {
        const ev = snap.events[seen];
        if (ev.stage === "safety") {
          if (ev.kind === "safety_verdict" && ev.data) {
            setStage("safety", "running");
            const cls = ev.data.status === "pass" ? "ok"
              : ev.data.status === "warn" ? "warn"
              : "bad";
            logText(ev.text);
            const mark = document.createElement("div");
            mark.className = "log-line";
            const span = document.createElement("span");
            span.className = cls;
            span.textContent = "  verdict: " + String(ev.data.status)
              .toUpperCase() + " - advisory queries made: "
              + String(ev.data.queries_made);
            mark.appendChild(span);
            logEl.appendChild(mark);
            continue;
          }
          if (ev.kind === "safety_blocked") {
            setStage("safety", "blocked", "fail/unknown - stopped");
            setStage("architecture", "pending");
            logText(ev.text);
            verdict("STOPPED BY SAFETY CHECKS - a required check failed "
                    + "or is unknown; nothing spent, nothing executed",
                    "fail");
            continue;
          }
          if (ev.kind === "stage_done") {
            const meta = snap.safety && snap.safety.status === "warn"
              ? "warn - review needed before spend/execute" : "qualified";
            setStage("safety", "done", meta);
            logText(ev.text);
            continue;
          }
          logText(ev.text);
          continue;
        }
        if (ev.kind === "error") { log(`<span class="bad">&#10007;</span> ${ev.text}`); verdict(ev.text, "fail"); }
        else if (ev.kind === "blocked") {
          setStage("architecture", "blocked", "needs model grant");
          const pa = ev.data && ev.data.paid_attempt;
          verdict(pa && pa.spent === true
            ? `STOPPED - 1 paid call was made and rejected (never retried)`
            : pa && pa.spent === null
              ? `STOPPED - paid call state UNKNOWN - check the retained record before any retry`
              : `STOPPED AT THE PAID BOUNDARY - no model call made`, "fail");
          log(ev.text);
          tokenMeter(pa && pa.spent === true
            ? `paid stages: <b>1 model call made</b> &middot; its output rejected, nothing retried`
            : pa && pa.spent === null
              ? `paid stages: call state <b>UNKNOWN</b> &middot; check the retained record`
              : `paid stages: <b>disabled</b> &middot; 0 model calls made &middot; 0 keys used`);
        }
        else {
          log(ev.text.replace(/(pinned at \w+|license \S+|exports,?)/g, '<span class="hl">$1</span>'));
          if (ev.data && ev.data.slug && ev.data.commit) {
            const existing = repoLive.find(r => r.name === ev.data.slug);
            if (!existing) repoLive.push({
              name: ev.data.slug, commit: ev.data.commit,
              license: ev.data.license || "?", role: "", exports: [],
            });
            drawGraph({ repos: true, repoData: repoLive });
          }
          if (ev.data && ev.data.exports) {
            const r = repoLive.find(x => x.name === ev.data.slug);
            if (r) { r.exports = ev.data.exports.slice(0, 6); r.role = r.role || "analyzed"; }
            setStage("analyze", "running");
            drawGraph({ repos: true, exports: true, repoData: repoLive });
            typeCode("exports", ["exports"], ev.data.exports.join("\n"), 2000);
          }
        }
        if (ev.kind === "stage_done" && ev.stage === "ingest") {
          setStage("ingest", "done", "cloned + pinned");
          setStage("analyze", "running");
        }
        if (ev.kind === "stage_done" && ev.stage === "analyze") {
          setStage("analyze", "done", "exports mapped");
          setStage("safety", "running");
        }
        if (ev.kind === "review") {
          setStage("architecture", "done", "plan accepted");
          setStage("glue", "done", "generated + linted");
          setStage("tests", "done", "generated + linted");
          setStage("verify", "blocked", "awaiting source review");
          setBadge("LIVE &middot; generated + pinned &middot; nothing executed", "live");
          verdict("PINNED FOR REVIEW - nothing executed; an independent reviewer must approve these exact bytes first", "fail");
          log(ev.text);
          if (ev.data && ev.data.files)
            typeCode("review", ["sha256"],
                     Object.entries(ev.data.files).map(([k, v]) => `${k}\n  ${v}`).join("\n"), 4000);
          if (!document.getElementById("resume-btn")) {
            const rb = document.createElement("button");
            rb.id = "resume-btn"; rb.className = "ghost-btn";
            rb.textContent = "Review approved? Resume build (no generation)";
            rb.onclick = () => resumeBuild(runId);
            logEl.appendChild(rb);
          }
        }
        if (ev.stage === "build" && ev.kind === "ready" && ev.data && ev.data.prefix) {
          setStage("architecture", "done", "plan accepted");
          setStage("glue", "done", "generated + gated");
          setStage("tests", "done", "generated + gated");
          setStage("verify", "done", "acceptance passed");
          setBadge("LIVE &middot; real build &middot; probe-verified", "live");
          verdict(`BUILD VERIFIED - ${ev.data.app_name} (unedited generated output)`, "pass");
          log(ev.text);
          initBuildApp(runId, ev.data);
        }
        if (ev.kind === "ideas" && ev.data && ev.data.cards) {
          setStage("architecture", "pending", "pick an idea below");
          renderIdeaCards(ev.data.cards, snap.recorded_pair,
                          ev.data.source, ev.data.provenance,
                          ev.data.paid_attempt);
          const p = ev.data.provenance;
          const pa = ev.data.paid_attempt;
          if (p) setBadge("LIVE &middot; free stages &middot; 1 paid idea call", "live");
          else if (pa && pa.spent === true)
            setBadge("LIVE &middot; free stages &middot; 1 paid call (output rejected)", "live");
          else if (pa && pa.spent === null)
            setBadge("LIVE &middot; free stages &middot; paid call state UNKNOWN", "live");
          tokenMeter(p
            ? `ideas from <b>${p.model}</b> &middot; 1 model call &middot; <b>${p.usage.input}</b> in / <b>${p.usage.output}</b> out`
            : (pa && pa.spent === true
              ? `ideas from <b>local analysis</b> &middot; 1 model call made &middot; its output rejected, fallback shown`
              : pa && pa.spent === null
                ? `ideas from <b>local analysis</b> &middot; paid call state UNKNOWN &middot; check the retained record before any retry`
                : `ideas from <b>local analysis</b> &middot; 0 model calls made`));
        }
      }
      if (snap.status !== "running" && snap.status !== "resuming") { liveSeen = seen; break; }
      await new Promise(r => setTimeout(r, 500));
    }
  }

  /* ================= REPLAY MODE (recorded run) ================= */
  const REPLAY_STAGES = R.stages;

  async function runReplay() {
    setBadge("REPLAY &middot; recorded run 2026-11-04", "");
    show("#screen-build");
    buildRail(REPLAY_STAGES);
    logEl.innerHTML = "";
    $("#code-content").textContent = "";
    $("#ideas-cards").classList.add("hidden");
    $("#code-view").classList.remove("hidden");
    drawGraph({});

    setStage("ingest", "running");
    typeCode("vendor manifest", ["vendor manifest (sha256)"],
      "microdot/  2.7.0 @ " + R.repos[0].commit + "  [MIT]\n" +
      "peewee/    4.5.3 @ " + R.repos[1].commit + "  [MIT]\n" +
      R.vendored_files + " files, every one sha256-pinned and verified.\n" +
      "No unpinned snapshots. No network at verify time.", 1200);
    await wait(600);
    drawGraph({ repos: true });
    log(`Pinning <span class="hl">microdot ${R.repos[0].version}</span> @ ${R.repos[0].commit.slice(0, 12)} &middot; <span class="hl">peewee ${R.repos[1].version}</span> @ ${R.repos[1].commit.slice(0, 12)}`);
    await wait(600);
    log(`Licenses: <span class="ok">MIT + MIT</span> &middot; vendored ${R.vendored_files} files, sha256-verified`);
    setStage("ingest", "done", `${R.vendored_files} files pinned`);

    setStage("analyze", "running");
    await wait(500);
    drawGraph({ repos: true, exports: true });
    typeCode("exports", ["exports (real, extracted)"],
      "# microdot\n" + R.repos[0].exports.join("\n") + "\n\n# peewee\n" + R.repos[1].exports.join("\n"), 1600);
    log(`microdot exports: <span class="hl">${R.repos[0].exports.slice(0, 4).join(", ")}</span>&hellip;`);
    log(`peewee exports: <span class="hl">${R.repos[1].exports.slice(0, 4).join(", ")}</span>&hellip;`);
    await wait(700);
    setStage("analyze", "done", "exports mapped");

    setStage("architecture", "running", "model call 1/4");
    tokenMeter(`model call 1/4 &middot; architecture &middot; <b>4,397</b> in / <b>634</b> out`);
    log(`Model call 1/4: architecture plan&hellip;`);
    await wait(900);
    drawGraph({ repos: true, exports: true, app: true, planEdges: true, extEdges: true });
    typeCode("architecture.json", ["architecture.json (VERBATIM recorded AI output)"],
      R.manifest, 2200);
    log(`<span class="hl">Recorded plan (verbatim above):</span> ${R.arbitrage.split(".")[0]}.`);
    await wait(900);
    setStage("architecture", "done", "plan received (verbatim shown)");
    log(`<span class="hl">Note:</span> the recorded plan's bridge list included update/delete (PUT/DELETE /users) - <span class="hl">the model's glue did not deliver them</span>; the assistant added them later for /notes.`);
    log(`<span class="hl">Graph at left:</span> illustrated map of the FINAL repaired app (assistant-drawn), not the verbatim recorded plan.`);

    setStage("glue", "running", "model call 2/4");
    tokenMeter(`model call 2/4 &middot; glue synthesis &middot; <b>1,182</b> in / <b>1,919</b> out`);
    log(`Model call 2/4: writing <span class="hl">generated/app.py</span> - <span class="bad">ORIGINAL AI bytes shown</span>`);
    typeCode("generated/app.py", CODE_TABS, R.code.app_original_ai, 2600);
    await wait(2100);
    setStage("glue", "done", "generated/app.py (AI)");

    setStage("tests", "running", "model call 3/4");
    tokenMeter(`model call 3/4 &middot; test synthesis &middot; <b>2,415</b> in / <b>2,048</b> out`);
    log(`Model call 3/4: writing <span class="hl">test_fused.py</span> - <span class="bad">ORIGINAL AI bytes shown</span>`);
    typeCode("test_fused.py", CODE_TABS, R.code.tests_original_ai, 1600);
    await wait(1700);
    setStage("tests", "done", "test_fused.py (AI)");
    tokenMeter(`calls: <b>4 charged</b> + <b>4 count-checks</b> &middot; totals <b>8,008</b> in / <b>4,602</b> out &middot; probe 14/1`);

    setStage("verify", "running");
    log(`Fixed acceptance test in sandbox, against the UNEDITED AI output&hellip;`);
    await wait(1000);
    R.acceptance_tests.forEach(t => log(`<span class="bad">&#10007;</span> ${t} - <span class="bad">ERROR at import</span>`));
    await wait(600);
    verdict(`UNEDITED AI OUTPUT: 4/4 FAILED AT IMPORT`, "fail");
    setStage("verify", "failed", "4 errors");
    await wait(900);

    setStage("repair", "running", "offline");
    log(`- <span class="hl">ASSISTANT repair</span>: offline, no model calls -`);
    R.original_verdict.defects.forEach(d => log(`fix ${d.n}: <span class="hl">${d.title}</span>`));
    typeCode("generated/app.py", CODE_TABS, R.code.app_repaired, 2600);
    tokenMeter(`assistant repair &middot; <b>0</b> model calls &middot; 3 labeled fixes, every other byte unchanged`);
    await wait(1300);
    R.acceptance_tests.forEach(t => log(`<span class="ok">&#10003;</span> ${t}`));
    verdict(`ASSISTANT-REPAIRED BUILD: 4/4 PASSED + vacuity confirmed`, "pass");
    setStage("repair", "done", "4/4 + vacuity");
    await wait(900);

    setStage("extend", "running", "offline");
    drawGraph({ repos: true, exports: true, app: true, planEdges: true, extEdges: true });
    log(`- <span class="hl">ASSISTANT extension</span>: edit/delete added offline -`);
    typeCode("assistant_ext.py", CODE_TABS, R.code.ext, 2200);
    await wait(1200);
    log(`<span class="ok">&#10003;</span> edit/delete extension checks: <span class="ok">7/7</span> (assistant-authored tests, plain Python)`);
    verdict(`FULL GOAL REACHED BY ASSISTANT: save / list / read / edit / delete`, "pass");
    setStage("extend", "done", "7/7");
    await wait(1000);

    showResult();
  }

  /* ---------------- result screen ---------------- */
  function showResult() {
    $("#verdict-journey").innerHTML = `
      <div class="journey-card"><span class="j-badge fail">4/4 ERRORS</span>
        <h3>1 &middot; Unedited AI output</h3>
        <p>Every acceptance check failed at import - three real defects in the
        model&rsquo;s own loader. The verifier caught all of them.</p></div>
      <div class="journey-arrow">&#8594;</div>
      <div class="journey-card"><span class="j-badge pass">4/4 PASS</span>
        <h3>2 &middot; Assistant-repaired</h3>
        <p>Three labeled offline fixes, zero new model calls. Fixed acceptance passes,
        vacuity control confirms the tests bite.</p></div>
      <div class="journey-arrow">&#8594;</div>
      <div class="journey-card"><span class="j-badge ext">7/7 PASS</span>
        <h3>3 &middot; Assistant-extended</h3>
        <p>Edit and delete added offline - the app now saves, lists, reads,
        edits and deletes notes.</p></div>`;
    show("#screen-result");
    initRealNotes();
  }

  /* ---------------- notes: REAL backend ---------------- */
  async function api(path, method, body) {
    const resp = await fetch(path, {
      method, headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (resp.status === 204) return { ok: true };
    const data = await resp.json().catch(() => null);
    return { ok: resp.ok, status: resp.status, data };
  }
  let notesReal = false;
  let appBase = "/notes", appField = "text", appEntity = "note";
  async function initBuildApp(runId, d) {
    $("#verdict-journey").innerHTML = `
      <div class="journey-card"><span class="j-badge pass">VERIFIED</span>
        <h3>${d.app_name}</h3>
        <p>Generated from ${buildInputDesc || "the input card selected for this run"}
        and verified against its unedited output. The app below IS this
        build - spawned and probe-verified just now, not the recorded
        example.</p><p id="model-tests-note"></p></div>`;
    const mtNote = $("#model-tests-note");
    if (d.model_tests === "passed")
      mtNote.textContent = "The model's own test script also passed (supporting signal; the fixed acceptance is the bar).";
    else if (d.model_tests)
      mtNote.textContent = `Honesty note: the model's own test script ${d.model_tests}; the pass above is the fixed, model-independent CRUD acceptance.`;
    show("#screen-result");
    appBase = `/build/${runId}${d.prefix}`; appField = d.field;
    appEntity = d.entity || "item";
    $("#result-app-title").textContent = `${d.app_name} - interactive preview`;
    $("#note-text").placeholder = `New ${appEntity}\u2026`;
    $("#note-add").textContent = `Add ${appEntity}`;
    $("#run-real-card").classList.add("hidden");  // replay-only rail
    const badge = $("#notes-backend-badge");
    const res = await api(appBase, "GET");
    if (res.ok) {
      notesReal = true;
      badge.textContent = "REAL AI-built app running locally \u00b7 spawned + probe-verified";
      badge.className = "sim-badge real";
      $("#preview-truth").textContent =
        `Every action below hits this reviewed build over HTTP (${d.prefix}) with its own real SQLite store.`;
    } else {
      notesReal = false;
      badge.textContent = "build backend unavailable";
      badge.className = "sim-badge";
      $("#preview-truth").textContent =
        "The verified build backend is not reachable; the server spawns it on demand.";
    }
    await refreshNotes();
  }
  async function initRealNotes() {
    appBase = "/notes"; appField = "text"; appEntity = "note";
    $("#result-app-title").textContent = "Notes app - interactive preview";
    $("#note-text").placeholder = "Write a note\u2026";
    $("#note-add").textContent = "Save note";
    $("#run-real-card").classList.remove("hidden");
    const health = await fetch("/api/notes-health").then(r => r.json()).catch(() => null);
    const badge = $("#notes-backend-badge");
    if (health && health.available) {
      notesReal = true;
      badge.textContent = "REAL app running locally \u00b7 microdot + peewee + SQLite";
      badge.className = "sim-badge real";
      $("#preview-truth").textContent =
        "Every action below hits the actual verified app over HTTP (POST/GET/PUT/DELETE /notes) " +
        "with its real SQLite store - the same code that passed 4/4 acceptance and 7/7 extension checks.";
    } else {
      badge.textContent = "backend unavailable - start via studio/serve.py";
      badge.className = "sim-badge";
      $("#preview-truth").textContent =
        "The real app backend is not reachable. Start the UI with studio/serve.py from the repo root; " +
        "it launches the verified example app locally.";
    }
    await refreshNotes();
  }
  async function refreshNotes() {
    const list = $("#notes-list");
    if (!notesReal) { list.innerHTML = `<div class="notes-empty">Backend offline.</div>`; return; }
    const res = await api(appBase, "GET");
    const notes = (res.data || []);
    list.innerHTML = notes.length ? "" : `<div class="notes-empty">Nothing here yet - add a ${appEntity} above.</div>`;
    notes.forEach(n => {
      const row = document.createElement("div");
      row.className = "note-row";
      row.innerHTML = `<span class="note-id">#${n.id}</span>
        <span class="note-body"></span>
        <button data-act="edit">Edit</button>
        <button data-act="del">Delete</button>`;
      row.querySelector(".note-body").textContent = n[appField];
      row.querySelector('[data-act="del"]').onclick = async () => { await api(`${appBase}/${n.id}`, "DELETE"); refreshNotes(); };
      row.querySelector('[data-act="edit"]').onclick = () => {
        const body = row.querySelector(".note-body");
        const inp = document.createElement("input");
        inp.className = "note-edit-input"; inp.value = n.text;
        body.replaceWith(inp); inp.focus();
        inp.onkeydown = async (ev) => {
          if (ev.key === "Enter" && inp.value.trim()) {
            await api(`${appBase}/${n.id}`, "PUT", { [appField]: inp.value.trim() });
            refreshNotes();
          }
        };
      };
      list.appendChild(row);
    });
  }
  $("#note-add").onclick = async () => {
    const t = $("#note-text").value.trim();
    if (!t || !notesReal) return;
    await api(appBase, "POST", { [appField]: t });
    $("#note-text").value = "";
    refreshNotes();
  };
  $("#note-text").addEventListener("keydown", e => { if (e.key === "Enter") $("#note-add").click(); });

  /* ---------------- wire up ---------------- */
  $("#fuse-btn").onclick = () => startLive().catch(e => {
    show("#screen-build");
    logEl.innerHTML = "";
    verdict("Could not reach the local server. Start it: python3 studio/serve.py", "fail");
  });
  const replayBtn = $("#replay-btn");
  replayBtn.onclick = () => runReplay();
  $("#intent, #repo-a, #repo-b").forEach ? null : null;
  const fuseBtn = $("#fuse-btn");
  const syncFuseLabel = () => {
    fuseBtn.innerHTML = $("#intent").value.trim()
      ? "Fuse repositories &#8594;" : "Suggest what to build &#8594;";
  };
  syncFuseLabel();
  ["#intent", "#repo-a", "#repo-b"].forEach(sel => $(sel).addEventListener("input", () => {
    syncFuseLabel();
    const ok = inputsMatchRecorded();
    replayBtn.disabled = !ok;
    replayBtn.title = ok ? "" : "Replay exists only for the recorded microdot + peewee notes build";
    $("#replay-hint").textContent = ok
      ? "Repos match the RECORDED NOTES API build (microdot + peewee, 2026-11-04) - replay that recorded run's full paid pipeline."
      : "Replay exists only for the RECORDED NOTES API build (pinned microdot + peewee, 2026-11-04). Your inputs run the real free stages instead.";
  }));
  replayBtn.disabled = false; // default inputs match

  /* -------- saved reviewed builds present on this machine -------- */
  (async () => {
    let builds = [];
    try {
      const r = await fetch("/api/builds/local").then(r => r.json());
      builds = r.builds || [];
    } catch (e) { return; }  // older server or offline - no card
    if (!builds.length) return;
    const card = document.createElement("div");
    card.className = "setup-note";
    card.style.borderTop = "1px solid rgba(255,255,255,.08)";
    card.style.paddingTop = "12px";
    // No innerHTML for server-supplied values: buttons and the note are
    // built with textContent, and the run id travels via closure only.
    builds.forEach(b => {
      const btn = document.createElement("button");
      btn.className = "replay-btn open-saved";
      btn.textContent = `Open the saved reviewed AI-built ${b.app_name}`;
      btn.onclick = () => {
        const runId = b.run_id;
        lastRunId = runId; liveSeen = 0;
        setBadge("LIVE &middot; saved reviewed build &middot; 0 model calls", "live");
        show("#screen-build");
        buildRail([
          { id: "ingest", label: "Ingest (real)" },
          { id: "analyze", label: "Analyze (real)" },
          { id: "architecture", label: "Architecture" },
          { id: "glue", label: "Glue synthesis" },
          { id: "tests", label: "Test synthesis" },
          { id: "verify", label: "Verify" },
        ]);
        logEl.innerHTML = "";
        log(`Opening the <span class="hl">saved reviewed AI-built app</span> ` +
            `- no generation: bytes are re-hashed against the ` +
            `review manifest, then the fixed acceptance re-runs.`);
        resumeBuild(runId);
      };
      card.appendChild(btn);
    });
    const note = document.createElement("p");
    note.className = "setup-note";
    note.textContent = "A real app the AI pipeline built on 2026-11-04 " +
      "from a locally-generated analysis card. Every byte was hash-reviewed " +
      "before it ever ran, and this machine re-verified every byte on import. " +
      "Its model-written test script fails (retained unedited) - the " +
      "independent CRUD acceptance is what passed. Runs fully locally.";
    card.appendChild(note);
    $("#replay-hint").after(card);
  })();

  /* ---------------- freeze states (deterministic screenshots) ---------------- */
  if (FREEZE && FREEZE !== "setup") {
    (async () => {
      if (FREEZE.startsWith("live")) {
        const rid = qs.get("run");
        if (rid) {
          // render a finished live run's real events instantly
          const snap = await fetch("/api/run/" + rid).then(r => r.json());
          setBadge("LIVE &middot; free stages &middot; 0 model calls", "live");
          show("#screen-build");
          buildRail([{ id: "ingest", label: "Ingest (real)" }, { id: "analyze", label: "Analyze (real)" },
                     { id: "safety", label: "Safety checks (real)" },
                     { id: "architecture", label: "Architecture" }, { id: "glue", label: "Glue synthesis" },
                     { id: "tests", label: "Test synthesis" }, { id: "verify", label: "Verify" }]);
          const repoLive = [];
          snap.events.forEach(ev => {
            if (ev.data && ev.data.slug && ev.data.commit && !repoLive.find(r => r.name === ev.data.slug))
              repoLive.push({ name: ev.data.slug, commit: ev.data.commit, license: ev.data.license || "?", role: "", exports: [] });
            if (ev.data && ev.data.exports) {
              const r = repoLive.find(x => x.name === ev.data.slug);
              if (r) r.exports = ev.data.exports.slice(0, 6);
            }
            if (ev.kind === "blocked") { verdict("STOPPED AT THE PAID BOUNDARY - no model call made", "fail"); log(ev.text); }
            else if (ev.kind === "ideas" && ev.data && ev.data.cards) {
              renderIdeaCards(ev.data.cards, snap.recorded_pair,
                              ev.data.source, ev.data.provenance,
                              ev.data.paid_attempt);
              if (ev.data.provenance)
                setBadge("LIVE &middot; free stages &middot; 1 paid idea call", "live");
              else if (ev.data.paid_attempt && ev.data.paid_attempt.spent === true)
                setBadge("LIVE &middot; free stages &middot; 1 paid call (output rejected)", "live");
              else if (ev.data.paid_attempt && ev.data.paid_attempt.spent === null)
                setBadge("LIVE &middot; free stages &middot; paid call state UNKNOWN", "live");
            }
            else if (ev.kind !== "stage_done") log(ev.text);
          });
          setStage("ingest", "done", "cloned + pinned");
          setStage("analyze", "done", "exports mapped");
          if (snap.safety)
            setStage("safety", snap.safety.status === "fail" || snap.safety.status === "unknown" ? "blocked" : "done",
                     `verdict: ${snap.safety.status}`);
          setStage("architecture", snap.status === "ideas_ready" ? "pending" : "blocked",
                   snap.status === "ideas_ready" ? "pick an idea below" : "needs model grant");
          drawGraph({ repos: true, exports: true, repoData: repoLive });
          if (snap.status !== "ideas_ready")
            typeCode("exports", ["exports"], (repoLive[1] ? repoLive[1].exports : []).join("\n"), 1500);
          const ideaEv = (snap.events || []).find(e => e.kind === "ideas" && e.data && e.data.cards);
          const ip = ideaEv && ideaEv.data.provenance;
          const ipa = ideaEv && ideaEv.data.paid_attempt;
          tokenMeter(snap.status === "ideas_ready"
            ? (ip
              ? `ideas from <b>${ip.model}</b> &middot; 1 model call &middot; <b>${ip.usage.input}</b> in / <b>${ip.usage.output}</b> out`
              : (ipa && ipa.spent === true
                ? `ideas from <b>local analysis</b> &middot; 1 model call made &middot; its output rejected, fallback shown`
                : ipa && ipa.spent === null
                  ? `ideas from <b>local analysis</b> &middot; paid call state UNKNOWN &middot; check the retained record before any retry`
                  : `ideas from <b>local analysis</b> &middot; 0 model calls made`))
            : `paid stages: <b>disabled</b> &middot; 0 model calls made`);
        }
        return;
      }
      setBadge("REPLAY &middot; recorded run 2026-11-04", "");
      show("#screen-build");
      buildRail(REPLAY_STAGES);
      const done = (...ids) => ids.forEach(s => setStage(s, "done"));
      if (FREEZE === "ingest") {
        drawGraph({ repos: true }); setStage("ingest", "running");
      } else if (FREEZE === "analyze") {
        drawGraph({ repos: true, exports: true }); setStage("ingest", "done", `${R.vendored_files} files pinned`); setStage("analyze", "running");
      } else if (FREEZE === "architecture") {
        drawGraph({ repos: true, exports: true, app: true, planEdges: true, extEdges: true });
        done("ingest", "analyze"); setStage("architecture", "done", "plan received (verbatim shown)");
        typeCode("architecture.json", ["architecture.json (VERBATIM recorded AI output)"], R.manifest, 99999);
        tokenMeter(`model call 1/4 &middot; <b>4,397</b> in / <b>634</b> out`);
      } else if (FREEZE === "glue") {
        drawGraph({ repos: true, exports: true, app: true, planEdges: true, extEdges: true });
        done("ingest", "analyze", "architecture"); setStage("glue", "running", "model call 2/4");
        log(`Model call 2/4: writing generated/app.py - <span class="bad">ORIGINAL AI bytes shown</span>`);
        typeCode("generated/app.py", CODE_TABS, R.code.app_original_ai, 2600);
        tokenMeter(`model call 2/4 &middot; <b>1,182</b> in / <b>1,919</b> out`);
      } else if (FREEZE === "verify") {
        drawGraph({ repos: true, exports: true, app: true, planEdges: true, extEdges: true });
        done("ingest", "analyze", "architecture", "glue", "tests");
        R.acceptance_tests.forEach(t => log(`<span class="bad">&#10007;</span> ${t} - <span class="bad">ERROR at import</span>`));
        verdict(`UNEDITED AI OUTPUT: 4/4 FAILED AT IMPORT`, "fail");
        setStage("verify", "failed", "4 errors");
        R.original_verdict.defects.forEach(d => log(`fix ${d.n}: <span class="hl">${d.title}</span>`));
        R.acceptance_tests.forEach(t => log(`<span class="ok">&#10003;</span> ${t}`));
        verdict(`ASSISTANT-REPAIRED BUILD: 4/4 PASSED + vacuity confirmed`, "pass");
        setStage("repair", "done", "4/4 + vacuity");
        typeCode("generated/app.py", CODE_TABS, R.code.app_repaired, 2600);
        tokenMeter(`calls: <b>4 charged</b> + <b>4 count-checks</b> &middot; totals <b>8,008</b> in / <b>4,602</b> out`);
      } else if (FREEZE === "extend") {
        drawGraph({ repos: true, exports: true, app: true, planEdges: true, extEdges: true });
        done("ingest", "analyze", "architecture", "glue", "tests");
        setStage("verify", "failed", "4 errors");
        setStage("repair", "done", "4/4 + vacuity");
        setStage("extend", "done", "7/7");
        log(`<span class="ok">&#10003;</span> edit/delete extension checks: <span class="ok">7/7</span>`);
        verdict(`FULL GOAL REACHED BY ASSISTANT: save / list / read / edit / delete`, "pass");
        typeCode("assistant_ext.py", CODE_TABS, R.code.ext, 2200);
        tokenMeter(`assistant extension &middot; <b>0</b> model calls`);
      } else if (FREEZE === "result" || FREEZE === "notes") {
        showResult();
      }
    })();
  }
  // Test seam: a browser driver runs the SAME event loop a real session
  // would - no alternate rendering path, no synthetic state.
  window.__rf = { pollLive };
  if (qs.get("autostart") && !FREEZE) runReplay();
})();
