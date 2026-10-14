// Relays paste text and dropped/uploaded files from the content script to the
// Paste Guard backend. Backend URL is set on the options page (default http://localhost:8765).
const DEFAULT_BACKEND = "http://localhost:8765";

function backend(cb) {
  chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND }, ({ backendUrl }) => cb(backendUrl.replace(/\/+$/, "")));
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "PG_CHECK") {
    backend((url) =>
      fetch(url + "/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: msg.text, source: msg.source })
      })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
          return r.json();
        })
        .then((verdict) => sendResponse({ ok: true, verdict }))
        .catch((err) => sendResponse({ ok: false, error: String(err) }))
    );
    return true; // keep the channel open for the async reply
  }
  if (msg?.type === "PG_CHECK_FILE") {
    // PDF and DOCX arrive base64 encoded (messages are JSON); the backend extracts the text.
    const bin = atob(msg.b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const form = new FormData();
    form.append("source", msg.source || "");
    form.append("file", new Blob([bytes], { type: msg.mime || "application/octet-stream" }), msg.name);
    backend((url) =>
      fetch(url + "/check_file", { method: "POST", body: form })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
          return r.json();
        })
        .then((verdict) => sendResponse({ ok: true, verdict }))
        .catch((err) => sendResponse({ ok: false, error: String(err) }))
    );
    return true;
  }
});
