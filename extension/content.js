// Intercepts pastes on AI tool pages, checks them with the backend, and
// inserts either the original text or the redacted text.
(function () {
  const MIN_LEN = 20; // tiny pastes go straight through

  document.addEventListener("paste", (e) => {
    const text = e.clipboardData?.getData("text/plain") || "";
    if (text.length < MIN_LEN) return;
    const target = document.activeElement;
    e.preventDefault();
    e.stopImmediatePropagation();
    chrome.runtime.sendMessage({ type: "PG_CHECK", text, source: location.hostname }, (resp) => {
      if (!resp || !resp.ok) {
        console.warn("[Paste Guard] backend not reachable, pasting as is", resp?.error);
        insert(target, text);
        return;
      }
      const v = resp.verdict;
      if (v.verdict === "allow") insert(target, text);
      else showOverlay(v, target, text);
    });
  }, true);

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

  function showOverlay(v, target, original) {
    document.getElementById("pg-overlay")?.remove();
    const box = document.createElement("div");
    box.id = "pg-overlay";
    box.className = "pg-" + v.verdict;
    const items = (v.findings || []).map((f) => `<li>${esc(f.type)}</li>`);
    if (v.semantic_match) {
      const m = v.semantic_match;
      items.push(`<li>matches ${esc(m.path)} lines ${m.lines[0]}-${m.lines[1]} (similarity ${m.similarity})</li>`);
    }
    box.innerHTML = `
      <div class="pg-title">Paste Guard: ${esc(v.verdict.toUpperCase())}</div>
      <div class="pg-msg">${esc(v.message || "")}</div>
      <ul>${items.join("")}</ul>
      <div class="pg-actions">
        <button id="pg-redact">Paste redacted</button>
        ${v.verdict === "block" ? "" : '<button id="pg-anyway">Paste anyway</button>'}
        <button id="pg-cancel">Cancel</button>
      </div>`;
    document.body.appendChild(box);
    box.querySelector("#pg-cancel").onclick = () => box.remove();
    box.querySelector("#pg-redact").onclick = () => { box.remove(); insert(target, v.redacted); };
    box.querySelector("#pg-anyway")?.addEventListener("click", () => { box.remove(); insert(target, original); });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
