const DEFAULTS = { backendUrl: "http://localhost:8765", disabledSites: [], checkFiles: true, failOpen: true };
const $ = (id) => document.getElementById(id);
const SITES = chrome.runtime.getManifest().content_scripts[0].matches.map((m) => new URL(m.replace("/*", "/")).hostname);
$("ver").textContent = "v" + chrome.runtime.getManifest().version;

chrome.storage.sync.get(DEFAULTS, (s) => {
  $("url").value = s.backendUrl;
  $("files").checked = s.checkFiles;
  $("failopen").checked = s.failOpen;
  $("sites").innerHTML = SITES.map((h) =>
    `<label class="chk"><input type="checkbox" data-host="${h}" ${s.disabledSites.includes(h) ? "" : "checked"}> ${h}</label>`).join("");
  test(s.backendUrl);
});

async function test(url) {
  $("dot").className = "dot";
  $("status").textContent = "Checking...";
  try {
    const h = await (await fetch(url.replace(/\/+$/, "") + "/health")).json();
    const i = h.index || {};
    $("dot").className = "dot " + (i.built ? "ok" : "warn");
    $("status").textContent = i.built
      ? `Connected. Backend v${h.version}, ${i.doc_chunks || 0} document passages, ${i.code_chunks || 0} code chunks.`
      : "Connected, but the index is not built yet.";
  } catch (e) {
    $("dot").className = "dot bad";
    $("status").textContent = "Not reachable: " + e.message;
  }
}

$("test").onclick = () => test($("url").value.trim() || DEFAULTS.backendUrl);
$("save").onclick = async () => {
  const url = ($("url").value.trim() || DEFAULTS.backendUrl).replace(/\/+$/, "");
  const origin = new URL(url).origin + "/*";
  // A non-local backend needs a host permission; ask only for that one origin.
  const granted = /^http:\/\/(localhost|127\.0\.0\.1)/.test(url) || await chrome.permissions.request({ origins: [origin] });
  if (!granted) { $("dot").className = "dot bad"; $("status").textContent = "Permission for that address was declined."; return; }
  const disabledSites = [...document.querySelectorAll("[data-host]")].filter((c) => !c.checked).map((c) => c.dataset.host);
  chrome.storage.sync.set({ backendUrl: url, disabledSites, checkFiles: $("files").checked, failOpen: $("failopen").checked },
    () => test(url));
};
