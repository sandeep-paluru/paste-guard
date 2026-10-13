// Relays paste text from the content script to the local backend.
const BACKEND = "http://localhost:8765/check";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "PG_CHECK") return;
  fetch(BACKEND, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: msg.text, source: msg.source })
  })
    .then((r) => r.json())
    .then((verdict) => sendResponse({ ok: true, verdict }))
    .catch((err) => sendResponse({ ok: false, error: String(err) }));
  return true; // keep the channel open for the async reply
});
