(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const state = {
    clusters: [],
    decisions: {},   // cluster_id -> "merge" | "keep_separate"
    uploadColumns: [],
  };

  // -----------------------------------------------------------
  // Toast
  // -----------------------------------------------------------
  let toastTimer;
  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-visible"), 3200);
  }

  // -----------------------------------------------------------
  // Count-up helper
  // -----------------------------------------------------------
  function countUp(el, to, opts = {}) {
    const duration = opts.duration || 900;
    const suffix = opts.suffix || "";
    const start = performance.now();
    function frame(now) {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const value = Math.round(to * eased);
      el.textContent = `${value}${suffix}`;
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // -----------------------------------------------------------
  // Hero convergence badge percentage
  // -----------------------------------------------------------
  function animateHeroBadge() {
    const pctEl = $("#convergence-pct");
    setTimeout(() => countUp(pctEl, 94, { duration: 1000, suffix: "%" }), 1400);
  }

  // -----------------------------------------------------------
  // Status pills
  // -----------------------------------------------------------
  async function loadStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();

      const modePill = $("#pill-mode");
      modePill.textContent = data.demo_mode ? "demo mode" : "live mode";
      modePill.className = "pill " + (data.demo_mode ? "pill--muted" : "pill--ok");

      const srcPill = $("#pill-source");
      srcPill.textContent = `source: ${data.source.connected ? "connected" : "offline"}`;
      srcPill.className = "pill " + (data.source.connected ? "pill--ok" : "pill--bad");

      const tgtPill = $("#pill-target");
      tgtPill.textContent = `target: ${data.target.connected ? "connected" : "offline"}`;
      tgtPill.className = "pill " + (data.target.connected ? "pill--ok" : "pill--bad");

      $("#demo-hint").textContent = data.demo_mode
        ? "Running on local sample data — flip DEMO_MODE off in config.py to point at real MySQL."
        : `Connected to ${data.table} across your source and target MySQL servers.`;

      $("#active-source-label").textContent = data.demo_mode
        ? "Using demo data"
        : `Using ${data.table} from your source MySQL database`;
      // Note: we deliberately do NOT call showSourcePanel("active") here.
      // The page loads with the "idle" (upload) panel visible by default —
      // forcing it to "active" on every load hid the dropzone before the
      // user had a chance to use it.
    } catch (err) {
      toast("Couldn't reach the backend — is app.py running?");
    }
  }

  // -----------------------------------------------------------
  // Data source: upload + column mapping
  // -----------------------------------------------------------

  function showSourcePanel(which) {
    // which: "idle" | "mapping" | "active"
    $("#source-idle").hidden = which !== "idle";
    $("#source-mapping").hidden = which !== "mapping";
    $("#source-active").hidden = which !== "active";
  }

  async function handleFile(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        toast(data.error || "Couldn't read that file.");
        return;
      }
      renderMapping(data);
      showSourcePanel("mapping");
    } catch (err) {
      toast("Upload failed — check the terminal running app.py.");
    }
  }

  function renderMapping(data) {
    state.uploadColumns = data.columns;

    $("#mapping-filename").textContent = data.filename;
    $("#mapping-rowcount").textContent = `${data.row_count} rows detected`;

    ["name", "phone", "email"].forEach((field) => {
      const select = $(`#map-${field}`);
      select.innerHTML = `<option value="">— not mapped —</option>` +
        data.columns.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
      if (data.guessed_mapping[field]) select.value = data.guessed_mapping[field];
    });

    const head = $("#mapping-preview-head");
    head.innerHTML = data.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");

    const body = $("#mapping-preview-body");
    body.innerHTML = data.preview.map((row) => `
      <tr>${data.columns.map((c) => `<td>${escapeHtml(row[c] ?? "")}</td>`).join("")}</tr>
    `).join("");
  }

  async function confirmMapping() {
    const mapping = {
      name: $("#map-name").value,
      phone: $("#map-phone").value,
      email: $("#map-email").value,
    };
    if (!mapping.name && !mapping.phone && !mapping.email) {
      toast("Map at least one column before continuing.");
      return;
    }

    const btn = $("#btn-confirm-mapping");
    if (btn.disabled) return; // guard against double-click firing two requests
    btn.disabled = true;
    btn.classList.add("is-loading");
    const originalLabel = btn.textContent;
    btn.textContent = "Using this data…";

    try {
      const res = await fetch("/api/confirm-mapping", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mapping),
      });
      const data = await res.json();
      if (!res.ok) {
        toast(data.error || "Couldn't use that mapping.");
        return;
      }
      $("#active-source-label").textContent = `Using your uploaded file (${data.record_count} rows)`;
      showSourcePanel("active");
      resetResultsUI();
      toast(`Dataset ready (${data.record_count} rows) — click Scan for duplicates below.`);
    } catch (err) {
      toast("Couldn't confirm the column mapping — check the terminal running app.py.");
    } finally {
      btn.disabled = false;
      btn.classList.remove("is-loading");
      btn.textContent = originalLabel;
    }
  }

  async function useDemoData() {
    try {
      await fetch("/api/clear-upload", { method: "POST" });
      await fetch("/api/seed-demo", { method: "POST" });
      $("#active-source-label").textContent = "Using demo data";
      showSourcePanel("active");
      resetResultsUI();
      toast("Switched to demo data.");
    } catch (err) {
      toast("Couldn't switch to demo data.");
    }
  }

  function resetResultsUI() {
    state.clusters = [];
    state.decisions = {};
    $$(".stat-card").forEach((c) => c.classList.remove("is-visible"));
    $("#clusters-list").innerHTML = "";
    $("#clusters-empty").hidden = false;
    $("#migrate-bar").hidden = true;
  }

  // -----------------------------------------------------------
  // Scan
  // -----------------------------------------------------------
  async function runScan() {
    const btn = $("#btn-scan");
    btn.classList.add("is-loading");
    btn.disabled = true;

    try {
      const res = await fetch("/api/scan", { method: "POST" });
      if (!res.ok) throw new Error("scan failed");
      const data = await res.json();

      state.clusters = data.clusters;
      state.decisions = {};

      revealStats(data);
      renderClusters(data.clusters);
      updateMigrateBar();

      if (data.capped) {
        toast(
          `Scanned the first ${data.max_scan_records} of ${data.total_available} records ` +
          `(matching is capped for performance) — found ${data.clusters.length} group${data.clusters.length === 1 ? "" : "s"}.`
        );
      } else {
        toast(
          data.clusters.length
            ? `Found ${data.clusters.length} possible duplicate group${data.clusters.length === 1 ? "" : "s"}.`
            : "No duplicates found — every record looks unique."
        );
      }
    } catch (err) {
      toast("Scan failed — check the terminal running app.py for details.");
    } finally {
      btn.classList.remove("is-loading");
      btn.disabled = false;
    }
  }

  function revealStats(data) {
    const stats = $$(".stat-card");
    stats.forEach((c) => c.classList.add("is-visible"));
    countUp($("#stat-total"), data.total_records);
    countUp($("#stat-dupes"), data.duplicate_records);
    countUp($("#stat-clean"), data.clean_records);
    countUp($("#stat-groups"), data.clusters.length);
  }

  // -----------------------------------------------------------
  // Render duplicate clusters
  // -----------------------------------------------------------
  function renderClusters(clusters) {
    const list = $("#clusters-list");
    const empty = $("#clusters-empty");
    list.innerHTML = "";

    if (!clusters.length) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;

    clusters.forEach((cluster, idx) => {
      const card = document.createElement("article");
      card.className = "cluster-card";
      card.style.animationDelay = `${idx * 0.06}s`;
      card.dataset.clusterId = cluster.cluster_id;

      const recordsHtml = cluster.records.map((r) => `
        <div class="record-row">
          <div class="record-row__id">#${r.id}</div>
          <div class="record-row__name">${escapeHtml(r.name || "")}</div>
          <div class="record-row__meta">${escapeHtml(r.phone || "")} · ${escapeHtml(r.email || "")}</div>
        </div>
      `).join("");

      const reasonsHtml = cluster.reasons.map((r) => `<span class="reason-tag">${escapeHtml(r)}</span>`).join("");

      card.innerHTML = `
        <div class="cluster-card__head">
          <span class="cluster-card__title">Possible duplicate group · ${cluster.records.length} records</span>
          <div class="cluster-card__score">
            <div class="score-bar"><div class="score-bar__fill" data-target="${cluster.avg_similarity}"></div></div>
            <span class="score-bar__label">${cluster.avg_similarity}%</span>
          </div>
        </div>
        <div class="cluster-card__records">${recordsHtml}</div>
        <div class="cluster-card__reasons">${reasonsHtml}</div>
        <div class="cluster-card__actions">
          <button class="btn btn--sm btn--merge" data-action="merge">Merge into one</button>
          <button class="btn btn--sm btn--keep" data-action="keep_separate">Keep separate</button>
        </div>
        <div class="cluster-card__decision" hidden></div>
      `;

      list.appendChild(card);

      requestAnimationFrame(() => {
        const fill = card.querySelector(".score-bar__fill");
        fill.style.width = `${cluster.avg_similarity}%`;
      });

      card.querySelector('[data-action="merge"]').addEventListener("click", () => setDecision(cluster.cluster_id, "merge", card));
      card.querySelector('[data-action="keep_separate"]').addEventListener("click", () => setDecision(cluster.cluster_id, "keep_separate", card));
    });
  }

  function setDecision(clusterId, decision, card) {
    state.decisions[clusterId] = decision;
    card.querySelector('[data-action="merge"]').classList.toggle("is-active", decision === "merge");
    card.querySelector('[data-action="keep_separate"]').classList.toggle("is-active", decision === "keep_separate");

    const cluster = state.clusters.find((c) => c.cluster_id === clusterId);
    const note = card.querySelector(".cluster-card__decision");

    if (cluster && note) {
      note.hidden = false;
      if (decision === "merge") {
        const kept = cluster.records[0];
        const droppedIds = cluster.records.slice(1).map((r) => `#${r.id}`).join(", ");
        note.className = "cluster-card__decision cluster-card__decision--merge";
        note.innerHTML = `✓ Will keep <strong>#${kept.id} ${escapeHtml(kept.name || "")}</strong> and drop ${droppedIds} when you migrate.`;
        toast(`Group marked to merge — keeping #${kept.id}, dropping ${cluster.records.length - 1} duplicate${cluster.records.length - 1 === 1 ? "" : "s"}.`);
      } else {
        note.className = "cluster-card__decision cluster-card__decision--keep";
        note.innerHTML = `✓ Keeping all ${cluster.records.length} records separate.`;
        toast("Group marked to keep separate.");
      }
    }

    updateMigrateBar();
  }

  function updateMigrateBar() {
    const bar = $("#migrate-bar");
    const total = state.clusters.length;
    const reviewed = Object.keys(state.decisions).length;

    if (total === 0) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    $("#migrate-summary").textContent = `${reviewed} of ${total} group${total === 1 ? "" : "s"} reviewed`;
  }

  // -----------------------------------------------------------
  // Migrate
  // -----------------------------------------------------------
  async function runMigrate() {
    const btn = $("#btn-migrate");
    btn.classList.add("is-loading");
    btn.disabled = true;

    try {
      const res = await fetch("/api/migrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decisions: state.decisions }),
      });
      const data = await res.json();
      toast(`Migrated ${data.migrated} records · merged ${data.groups_merged} group(s).`);
      await loadTargetPreview();
    } catch (err) {
      toast("Migration failed — check the terminal running app.py.");
    } finally {
      btn.classList.remove("is-loading");
      btn.disabled = false;
    }
  }

  // -----------------------------------------------------------
  // Export cleaned CSV
  // -----------------------------------------------------------
  async function exportCsv() {
    const btn = $("#btn-export-csv");
    btn.classList.add("is-loading");
    btn.disabled = true;

    try {
      const res = await fetch("/api/export-csv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decisions: state.decisions }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast(data.error || "Couldn't export CSV.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "cleaned_customers.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast("Cleaned CSV downloaded.");
    } catch (err) {
      toast("Couldn't export CSV.");
    } finally {
      btn.classList.remove("is-loading");
      btn.disabled = false;
    }
  }

  // -----------------------------------------------------------
  // Target preview table
  // -----------------------------------------------------------
  async function loadTargetPreview() {
    try {
      const res = await fetch("/api/target-preview");
      const data = await res.json();
      const body = $("#target-table-body");

      if (!data.records.length) {
        body.innerHTML = `<tr><td colspan="4" class="preview-table__empty">No records migrated yet.</td></tr>`;
        return;
      }

      body.innerHTML = data.records.map((r) => `
        <tr>
          <td><code>#${r.id}</code></td>
          <td>${escapeHtml(r.name || "")}</td>
          <td><code>${escapeHtml(r.phone || "")}</code></td>
          <td>${escapeHtml(r.email || "")}</td>
        </tr>
      `).join("");
    } catch (err) { /* silent — preview is best-effort */ }
  }

  // -----------------------------------------------------------
  // Scroll reveal for "how it works" steps
  // -----------------------------------------------------------
  function setupScrollReveal() {
    const targets = $$(".how__step");
    if (!("IntersectionObserver" in window) || !targets.length) {
      targets.forEach((t) => t.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.2 });
    targets.forEach((t) => io.observe(t));
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -----------------------------------------------------------
  // Init
  // -----------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    loadStatus();
    loadTargetPreview();
    animateHeroBadge();
    setupScrollReveal();

    $("#btn-scan").addEventListener("click", runScan);
    $("#btn-migrate").addEventListener("click", runMigrate);
    $("#btn-export-csv").addEventListener("click", exportCsv);

    // Data source controls
    $("#file-input").addEventListener("change", (e) => handleFile(e.target.files[0]));
    $("#btn-use-demo").addEventListener("click", useDemoData);
    $("#btn-cancel-upload").addEventListener("click", () => showSourcePanel("idle"));
    $("#btn-confirm-mapping").addEventListener("click", confirmMapping);
    $("#btn-change-source").addEventListener("click", () => showSourcePanel("idle"));

    const dropzone = $("#dropzone");
    ["dragenter", "dragover"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("is-dragover"); })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("is-dragover"); })
    );
    dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    });
  });
})();
