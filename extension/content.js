// Paste Guard content script for the protected AI chat sites (see manifest).
// Intercepts (1) text pastes, (2) file picker uploads (input[type=file] change)
// and (3) drag-and-drop, checks them with the backend, then lets the action
// through, offers a redacted version, or cancels it.
(function () {
  const MIN_LEN = 20; // tiny pastes go straight through
  const TEXT_EXT = [".txt", ".md", ".markdown", ".csv", ".json", ".py", ".js", ".ts", ".java", ".go", ".sql"];
  const BACKEND_EXT = [".pdf", ".docx"];
  let replaying = false; // set while we re-dispatch an approved event
  let settings = { disabledSites: [], checkFiles: true, failOpen: true };
  const load = () => chrome.storage.sync.get(settings, (s) => (settings = s));
  load();
  chrome.storage.onChanged.addListener(load);
  const active = () => !settings.disabledSites.includes(location.hostname);

  const ext = (name) => (name.match(/\.[^.]+$/)?.[0] || "").toLowerCase();
  const checkable = (f) => TEXT_EXT.includes(ext(f.name)) || BACKEND_EXT.includes(ext(f.name));
  const send = (msg) => new Promise((res) => chrome.runtime.sendMessage(msg, res));

  // ---------- text paste ----------
  document.addEventListener("paste", (e) => {
    if (replaying || !active()) return;
    const text = e.clipboardData?.getData("text/plain") || "";
    if (text.length < MIN_LEN) return;
    const target = document.activeElement;
    e.preventDefault();
    e.stopImmediatePropagation();
    send({ type: "PG_CHECK", text, source: location.hostname }).then((resp) => {
      if (!resp || !resp.ok) {
        console.warn("[Paste Guard] backend not reachable", resp?.error);
        if (settings.failOpen) insert(target, text);
        else toast("Paste Guard backend is not reachable, so the paste was held back.");
        return;
      }
      const v = resp.verdict;
      if (v.verdict === "allow") insert(target, text);
      else showOverlay(v, {
        title: "paste",
        onRedacted: () => insert(target, v.redacted),
        onAnyway: () => insert(target, text)
      });
    });
  }, true);

  // ---------- files ----------
  async function checkFile(file) {
    if (TEXT_EXT.includes(ext(file.name))) {
      const text = await file.text(); // extracted client-side
      const r = await send({ type: "PG_CHECK", text, source: location.hostname + " file:" + file.name });
      if (r?.ok) r.verdict.file = { name: file.name, chars: text.length };
      return r;
    }
    const buf = new Uint8Array(await file.arrayBuffer());
    let bin = "";
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return send({ type: "PG_CHECK_FILE", source: location.hostname, name: file.name, mime: file.type, b64: btoa(bin) });
  }

  // Check every file; return the worst verdict (with the file it came from) or null if all allowed.
  async function worstVerdict(files) {
    const rank = { allow: 0, nudge: 1, coach: 2, block: 3 };
    let worst = null;
    for (const f of files) {
      if (!checkable(f)) continue;
      const r = await checkFile(f);
      if (!r || !r.ok) { console.warn("[Paste Guard] could not check", f.name, r?.error); continue; }
      const v = r.verdict;
      v.file = v.file || { name: f.name };
      if (!worst || rank[v.verdict] > rank[worst.verdict]) worst = v;
    }
    return worst && worst.verdict !== "allow" ? worst : null;
  }

  // File picker: stop the site's change handler, check, then replay the event.
  window.addEventListener("change", async (e) => {
    const input = e.target;
    if (replaying || !active() || !settings.checkFiles || !(input instanceof HTMLInputElement) || input.type !== "file") return;
    const files = Array.from(input.files || []);
    if (!files.some(checkable)) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const v = await worstVerdict(files);
    const replay = () => {
      replaying = true;
      try { input.dispatchEvent(new Event("change", { bubbles: true })); input.dispatchEvent(new Event("input", { bubbles: true })); }
      finally { replaying = false; }
    };
    if (!v) return replay();
    showOverlay(v, {
      title: "upload",
      onRedacted: () => { input.value = ""; copyText(v.redacted); },
      onAnyway: replay,
      onCancel: () => { input.value = ""; }
    });
  }, true);

  // Drag and drop: hold the drop, check, then re-dispatch it with the same files.
  window.addEventListener("drop", async (e) => {
    if (replaying || !active() || !settings.checkFiles) return;
    const files = Array.from(e.dataTransfer?.files || []);
    if (!files.some(checkable)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const target = e.target, x = e.clientX, y = e.clientY;
    const v = await worstVerdict(files);
    const replay = () => {
      const dt = new DataTransfer();
      files.forEach((f) => dt.items.add(f));
      replaying = true;
      try {
        target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, composed: true, dataTransfer: dt, clientX: x, clientY: y }));
      } finally { replaying = false; }
    };
    if (!v) return replay();
    showOverlay(v, { title: "upload", onRedacted: () => copyText(v.redacted), onAnyway: replay });
  }, true);

  // ---------- helpers ----------
  function insert(target, text) {
    target?.focus();
    if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) {
      const s = target.selectionStart, e = target.selectionEnd;
      target.setRangeText(text, s, e, "end");
      target.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      document.execCommand("insertText", false, text); // works with contenteditable editors
    }
  }

  function copyText(text) {
    navigator.clipboard.writeText(text).then(
      () => toast("Redacted text copied. Paste it instead of the file."),
      () => toast("Could not copy the redacted text."));
  }

  function toast(msg) {
    const t = document.createElement("div");
    t.id = "pg-toast"; t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  }

  function showOverlay(v, { title, onRedacted, onAnyway, onCancel }) {
    document.getElementById("pg-overlay")?.remove();
    const box = document.createElement("div");
    box.id = "pg-overlay";
    box.className = "pg-" + v.verdict;
    const items = (v.findings || []).map((f) => `<li>${esc(f.type)}${f.match ? ": " + esc(f.match) : ""}</li>`);
    const m = v.semantic_match;
    const matchHtml = m ? `
      <div class="pg-match">
        <div class="pg-src">${m.kind === "doc" ? "Document" : "Code"}: <b>${esc(m.source || m.path)}</b>
          (${esc(m.unit || "lines")} ${m.lines[0]}-${m.lines[1]}, similarity ${m.similarity})</div>
        <blockquote>${esc(m.snippet || "")}</blockquote>
      </div>` : "";
    const isFile = title === "upload";
    box.innerHTML = `
      <div class="pg-title">Paste Guard: ${esc(v.verdict.toUpperCase())}${v.file ? " (" + esc(v.file.name) + ")" : ""}</div>
      <div class="pg-msg">${esc(v.message || "")}</div>
      ${matchHtml}
      <ul>${items.join("")}</ul>
      <div class="pg-actions">
        <button id="pg-redact">${isFile ? "Copy redacted text" : "Paste redacted"}</button>
        ${v.verdict === "block" ? "" : `<button id="pg-anyway">${isFile ? "Upload anyway" : "Paste anyway"}</button>`}
        <button id="pg-cancel">Cancel</button>
      </div>`;
    document.body.appendChild(box);
    box.querySelector("#pg-cancel").onclick = () => { box.remove(); onCancel?.(); };
    box.querySelector("#pg-redact").onclick = () => { box.remove(); onRedacted(); };
    box.querySelector("#pg-anyway")?.addEventListener("click", () => { box.remove(); onAnyway(); });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
