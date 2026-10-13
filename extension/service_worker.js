// Relays paste text from the content script to the Paste Guard backend.
// Backend URL is set on the options page (default http://localhost:8765).
const DEFAULT_BACKEND = "http://localhost:8765";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "PG_CHECK") return;
  chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND }, ({ backendUrl }) => {
    fetch(backendUrl.replace(/\/+$/, "") + "/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: msg.text, source: msg.source })
    })
      .then((r) => r.json())
      .then((verdict) => sendResponse({ ok: true, verdict }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
  });
  return true; // keep the channel open for the async reply
});
