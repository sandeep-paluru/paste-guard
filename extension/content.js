// Hooks paste events on AI tool pages and shows the verdict overlay.
(function () {
  const MIN_LEN = 20; // skip tiny pastes

  document.addEventListener("paste", (e) => {
    const text = e.clipboardData?.getData("text/plain") || "";
    if (text.length < MIN_LEN) return;
    chrome.runtime.sendMessage(
      { type: "PG_CHECK", text, source: location.hostname },
      (resp) => {
        if (!resp || !resp.ok) {
          console.warn("[Paste Guard] backend not reachable", resp?.error);
          return;
        }
        if (resp.verdict.verdict !== "allow") showOverlay(resp.verdict);
      }
    );
  }, true);

  function showOverlay(v) {
    document.getElementById("pg-overlay")?.remove();
    const box = document.createElement("div");
    box.id = "pg-overlay";
    box.className = "pg-" + v.verdict;
    const findings = (v.findings || []).map((f) => `<li>${escapeHtml(f.type)}</li>`).join("");
    box.innerHTML = `
      <div class="pg-title">Paste Guard: ${escapeHtml(v.verdict.toUpperCase())}</div>
      <div class="pg-msg">${escapeHtml(v.message || "")}</div>
      <ul>${findings}</ul>
      <div class="pg-actions">
        <button id="pg-redact">Redact (coming soon)</button>
        <button id="pg-dismiss">Dismiss</button>
      </div>`;
    document.body.appendChild(box);
    box.querySelector("#pg-dismiss").onclick = () => box.remove();
    box.querySelector("#pg-redact").onclick = () => {
      // TODO(day 3): replace pasted text with v.redacted in the active input.
      alert("Redaction is a placeholder in the Day 1 build.");
    };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
