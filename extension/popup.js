const DEFAULTS = { backendUrl: "http://localhost:8765", disabledSites: [] };
const $ = (id) => document.getElementById(id);
$("ver").textContent = "v" + chrome.runtime.getManifest().version;
$("opts").onclick = () => chrome.runtime.openOptionsPage();

chrome.storage.sync.get(DEFAULTS, async ({ backendUrl, disabledSites }) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = "";
  try { host = new URL(tab?.url || "").hostname; } catch (_) { /* non-web tab */ }
  const protectedHosts = chrome.runtime.getManifest().content_scripts[0].matches.map((m) => new URL(m.replace("/*", "/")).hostname);
  const isAi = protectedHosts.includes(host);
  const paused = disabledSites.includes(host);
  $("sdot").className = "dot " + (isAi ? (paused ? "warn" : "ok") : "");
  $("site").textContent = isAi ? `${host}: ${paused ? "paused" : "protected"}` : "This page is not an AI chat site";
  $("toggle").style.display = isAi ? "" : "none";
  $("toggle").textContent = paused ? "Resume on this site" : "Pause on this site";
  $("toggle").onclick = () => {
    const next = paused ? disabledSites.filter((h) => h !== host) : [...disabledSites, host];
    chrome.storage.sync.set({ disabledSites: next }, () => location.reload());
  };
  try {
    const h = await (await fetch(backendUrl.replace(/\/+$/, "") + "/health")).json();
    const i = h.index || {};
    $("dot").className = "dot " + (i.built ? "ok" : "warn");
    $("state").textContent = i.built ? "Protection active" : "Backend up, index not built";
    $("detail").textContent = i.built
      ? `${i.doc_chunks || 0} document passages and ${i.code_chunks || 0} code chunks indexed. Backend v${h.version}.`
      : "Run ./pasteguard reindex on the backend machine.";
  } catch (e) {
    $("dot").className = "dot bad";
    $("state").textContent = "Backend not reachable";
    $("detail").textContent = backendUrl + ". Pastes and uploads go through unchecked until it is back.";
  }
});
