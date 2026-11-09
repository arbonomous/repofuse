/* One build. The server still refuses a failed or unknown check.
   The first python-wsgi card with no extra dependencies is the one that
   is built. That rule matches studio/straight.py. */
(function () {
  const $ = (id) => document.getElementById(id);
  let busy = false;
  let connected = false;

  function mark(step, state) {
    const item = document.querySelector('[data-step="' + step + '"]');
    if (item) item.className = state;
  }

  function resetSteps() {
    document.querySelectorAll(".s-steps li").forEach((item) => { item.className = ""; });
    $("log").textContent = "";
    $("choice").classList.add("hidden");
    $("choice").textContent = "";
    $("app-link").textContent = "";
  }

  function say(text) {
    $("status").textContent = text;
  }

  function log(text) {
    const line = document.createElement("li");
    line.textContent = text.length > 500 ? text.slice(0, 500) + "…" : text;
    $("log").appendChild(line);
  }

  async function post(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      const error = new Error(data.error || "Request failed");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function session() {
    try {
      const response = await fetch("/api/local-session/status");
      const data = await response.json();
      connected = !!data.connected;
    } catch (_) {
      connected = false;
    }
    $("key-status").textContent = connected
      ? "Meta is connected for this Studio process."
      : "Meta is not connected. The key stays in this process and clears when Studio restarts.";
  }

  $("connect").onclick = async () => {
    const field = $("key");
    const key = field.value;
    field.value = "";
    try {
      await post("/api/local-session/connect", {key});
      await session();
    } catch (error) {
      $("key-status").textContent = error.message || "Connection refused.";
      connected = false;
    }
  };

  function paint(snap) {
    const events = snap.events || [];
    const done = (stage) => events.some((event) => event.stage === stage && event.kind === "stage_done");
    if (events.some((event) => event.stage === "ingest")) mark("clone", done("ingest") ? "done" : "now");
    if (events.some((event) => event.stage === "safety")) {
      mark("check", snap.status === "stopped_safety_blocked" ? "stopped" : done("safety") ? "done" : "now");
    }
    if (events.some((event) => event.kind === "model_ideas")) mark("ideas", "done");
    if (events.some((event) => event.stage === "glue" && event.kind === "stage_done")) mark("build", "now");
    if (snap.status === "build_verified") { mark("build", "done"); mark("app", "now"); }
    if (snap.status === "build_failed" || snap.status === "failed") mark("build", "stopped");
    const last = events.length ? events[events.length - 1].text : snap.status;
    if (last) say(last.length > 280 ? last.slice(0, 280) + "…" : last);
  }

  async function waitFor(runId, accept) {
    const deadline = Date.now() + 12 * 60 * 1000;
    let seen = 0;
    for (;;) {
      const response = await fetch("/api/run/" + runId);
      const snap = await response.json();
      if (!response.ok) throw new Error(snap.error || "Run status unavailable");
      for (; seen < (snap.events || []).length; seen++) log(snap.events[seen].text || "");
      paint(snap);
      if (accept(snap)) return snap;
      if (Date.now() > deadline) throw new Error("This step took too long. The run is still on this machine.");
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }

  function failureText(snap) {
    const events = snap.events || [];
    for (let i = events.length - 1; i >= 0; i--) {
      const event = events[i];
      if (["error", "safety_blocked", "planning_refused", "blocked"].includes(event.kind) && event.text)
        return event.text;
    }
    if (snap.status === "stopped_safety_blocked")
      return "The check stopped this build. Nothing was sent to the model.";
    return "This build stopped before an idea was sent.";
  }

  function report(runId) {
    fetch("/api/relay", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({run_id: runId}),
    }).catch(() => {});
  }

  function eligible(cards) {
    return (cards || []).find((card) => card
      && card.runtime === "python-wsgi"
      && card.id && card.title
      && !(card.dependencies || []).length
      && !(card.external_services || []).length) || null;
  }

  function showChoice(chosen, cards) {
    const box = $("choice");
    box.classList.remove("hidden");
    box.textContent = "";
    const title = document.createElement("h2");
    title.textContent = chosen.title;
    box.appendChild(title);
    const why = document.createElement("p");
    why.textContent = "This is the first idea that runs on the contained Python app, with no extra packages or services. The others stay as proposals.";
    box.appendChild(why);
    for (const card of cards) {
      if (card.id === chosen.id) continue;
      const line = document.createElement("p");
      line.textContent = card.title;
      box.appendChild(line);
    }
  }

  async function storeRecords(runId) {
    const response = await fetch("/api/operator-review/" + runId);
    const preview = await response.json();
    if (!response.ok) throw new Error(preview.error || "Check details unavailable");
    if (!preview.recordable) {
      throw new Error("A failed or unknown check stops this build. Nothing was sent to the model.");
    }
    if (!preview.input_ready) {
      await post("/api/operator-review", {
        run_id: runId, stage: "input", reviewer: "local operator", findings: preview.findings,
      });
    }
    const disclosure = preview.disclosure;
    if (disclosure && disclosure.payload_sha256 && !preview.disclosure_ready) {
      await post("/api/operator-review", {
        run_id: runId, stage: "disclosure", reviewer: "local operator",
        payload_sha256: disclosure.payload_sha256,
      });
    }
  }

  async function finishTree(runId) {
    const response = await fetch("/api/operator-review/" + runId);
    const preview = await response.json();
    if (!response.ok || !preview.source) throw new Error((preview && preview.error) || "Generated tree unavailable");
    await post("/api/operator-review", {
      run_id: runId, stage: "source", reviewer: "local operator",
      tree_sha256: preview.source.tree_sha256,
    });
    mark("build", "done");
    await post("/api/build-general/verify", {run_id: runId});
    const verified = await waitFor(runId, (snap) => snap.status === "build_verified" || snap.status === "build_failed");
    if (verified.status !== "build_verified") {
      mark("build", "stopped");
      throw new Error("The contained tests did not pass. The app was not served.");
    }
    const served = await post("/api/build-general/serve", {run_id: runId});
    mark("app", "done");
    const link = document.createElement("a");
    link.href = served.url;
    link.textContent = served.url;
    link.target = "_blank";
    link.rel = "noopener";
    $("app-link").textContent = "";
    $("app-link").appendChild(link);
    say("The app is running on this machine.");
  }

  $("build").onclick = async () => {
    if (busy) return;
    if (!connected) {
      say("Connect the Meta key first. Build does not start without it.");
      return;
    }
    busy = true;
    $("build").disabled = true;
    resetSteps();
    mark("clone", "now");
    say("Cloning both repositories.");
    let started = null;
    try {
      started = await post("/api/fuse", {
        repo_a: $("repo-a").value, repo_b: $("repo-b").value, intent: "",
      });
      const ready = await waitFor(started.run_id, (snap) =>
        ["ideas_ready", "stopped_safety_blocked", "failed", "stopped_at_paid_boundary"].includes(snap.status));
      if (ready.status !== "ideas_ready") {
        mark("check", "stopped");
        say(failureText(ready));
        report(started.run_id);
        return;
      }
      mark("ideas", "now");
      say("Asking Meta for ideas.");
      await storeRecords(started.run_id);
      let ideas;
      try {
        ideas = await post("/api/planning/generate", {
          run_id: started.run_id, public_inputs: true, credit_review: true,
        });
      } catch (error) {
        mark("ideas", "stopped");
        report(started.run_id);
        throw error;
      }
      const chosen = eligible(ideas.cards);
      if (!chosen) {
        mark("ideas", "stopped");
        say("None of the ideas fit the contained Python app. Nothing else was built.");
        return;
      }
      showChoice(chosen, ideas.cards || []);
      mark("ideas", "done");
      mark("build", "now");
      say("Building " + chosen.title + ".");
      await post("/api/planning/select", {run_id: started.run_id, idea_id: chosen.id});
      const built = await waitFor(started.run_id, (snap) =>
        ["awaiting_review", "frontend_preflight_failed", "failed", "build_failed", "pending_repair_disclosure"].includes(snap.status));
      if (built.status !== "awaiting_review") {
        mark("build", "stopped");
        say(failureText(built));
        report(started.run_id);
        return;
      }
      await finishTree(started.run_id);
    } catch (error) {
      say(error.message || "The build stopped.");
      if (started && started.run_id) report(started.run_id);
    } finally {
      busy = false;
      $("build").disabled = false;
    }
  };

  session();
})();
