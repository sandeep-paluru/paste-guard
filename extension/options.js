const DEFAULT_BACKEND = "http://localhost:8765";
const $ = (id) => document.getElementById(id);
chrome.storage.sync.get({ backendUrl: DEFAULT_BACKEND }, ({ backendUrl }) => ($("url").value = backendUrl));
$("save").onclick = async () => {
  const url = ($("url").value.trim() || DEFAULT_BACKEND).replace(/\/+$/, "");
  const origin = new URL(url).origin + "/*";
  // Remote URLs need a host permission; ask only for that one origin.
  const granted = origin.startsWith("http://localhost") || await chrome.permissions.request({ origins: [origin] });
  if (!granted) { $("status").textContent = "Permission denied"; return; }
  chrome.storage.sync.set({ backendUrl: url }, async () => {
    try {
      const h = await (await fetch(url + "/health")).json();
      $("status").textContent = `Saved. Backend ok, index ${h.index.built ? "built" : "NOT built"}.`;
    } catch (e) { $("status").textContent = "Saved, but backend not reachable: " + e; }
  });
};
