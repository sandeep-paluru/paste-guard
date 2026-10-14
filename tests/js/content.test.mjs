// Tests the extension's content script logic in jsdom with a fake chrome.runtime.
// Run: cd tests/js && npm install && node --test   (also run by tests/test_extension_js.py)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
import { File as NodeFile } from "node:buffer";

const SRC = readFileSync(new URL("../../extension/content.js", import.meta.url), "utf8");
const tick = () => new Promise((r) => setTimeout(r, 20));

function setup(reply, settings = {}) {
  const dom = new JSDOM(`<!doctype html><body><textarea id="t"></textarea><div id="zone"></div></body>`,
    { url: "https://claude.ai/new", runScripts: "outside-only" });
  const w = dom.window;
  const sent = [];
  w.chrome = {
    storage: { sync: { get: (d, cb) => cb({ ...d, ...settings }) }, onChanged: { addListener() {} } },
    runtime: { sendMessage: (msg, cb) => { sent.push(msg); Promise.resolve(reply(msg)).then(cb); } },
  };
  // jsdom has no DataTransfer / DragEvent / execCommand / clipboard: minimal stand-ins.
  w.DataTransfer = class { constructor() { this.files = []; this.items = { add: (f) => this.files.push(f) }; } };
  w.DragEvent = class extends w.Event { constructor(t, o = {}) { super(t, o); this.dataTransfer = o.dataTransfer; } };
  w.document.execCommand = () => true;
  w.File = NodeFile; // jsdom File has no text() or arrayBuffer()
  const copied = [];
  Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async (t) => copied.push(t) } });
  w.eval(SRC);
  return { w, sent, copied, ta: w.document.getElementById("t") };
}

function paste(w, target, text) {
  target.focus();
  const e = new w.Event("paste", { bubbles: true, cancelable: true });
  e.clipboardData = { getData: () => text };
  target.dispatchEvent(e);
  return e;
}

const LONG = "This is a long enough paste to be checked by the backend service.";
const verdict = (v, extra = {}) => ({ ok: true, verdict: { verdict: v, message: "m", findings: [], matches: [],
  semantic_match: null, redacted: "[REDACTED]", ...extra } });

test("short paste goes straight through without a backend call", async () => {
  const { w, sent, ta } = setup(() => verdict("block"));
  const e = paste(w, ta, "hi there");
  assert.equal(e.defaultPrevented, false);
  assert.equal(sent.length, 0);
});

test("allowed paste is inserted", async () => {
  const { w, ta } = setup(() => verdict("allow"));
  assert.equal(paste(w, ta, LONG).defaultPrevented, true);
  await tick();
  assert.equal(ta.value, LONG);
  assert.equal(w.document.getElementById("pg-overlay"), null);
});

test("blocked paste shows overlay without Paste anyway; redact inserts redacted text", async () => {
  const { w, ta } = setup(() => verdict("block"));
  paste(w, ta, LONG); await tick();
  const ov = w.document.getElementById("pg-overlay");
  assert.ok(ov && ov.className === "pg-block");
  assert.equal(ov.querySelector("#pg-anyway"), null);
  ov.querySelector("#pg-redact").click();
  assert.equal(ta.value, "[REDACTED]");
});

test("coach paste offers Paste anyway and Cancel leaves the box empty", async () => {
  const { w, ta } = setup(() => verdict("coach"));
  paste(w, ta, LONG); await tick();
  const ov = w.document.getElementById("pg-overlay");
  assert.ok(ov.querySelector("#pg-anyway"));
  ov.querySelector("#pg-cancel").click();
  assert.equal(ta.value, "");
});

test("overlay escapes HTML from the backend", async () => {
  const { w, ta } = setup(() => verdict("coach", { message: "<img src=x onerror=alert(1)>" }));
  paste(w, ta, LONG); await tick();
  assert.equal(w.document.querySelector("#pg-overlay img"), null);
});

test("backend down: paste fails open with a visible status", async () => {
  const { w, ta } = setup(() => ({ ok: false, error: "TypeError: Failed to fetch" }));
  paste(w, ta, LONG); await tick();
  assert.equal(ta.value, LONG);
  assert.match(w.document.getElementById("pg-toast").textContent, /offline/);
});

test("backend down with failOpen off: paste is held back", async () => {
  const { w, ta } = setup(() => undefined, { failOpen: false });
  paste(w, ta, LONG); await tick();
  assert.equal(ta.value, "");
  assert.match(w.document.getElementById("pg-toast").textContent, /held back/);
});

test("paused site is not intercepted", async () => {
  const { w, sent, ta } = setup(() => verdict("block"), { disabledSites: ["claude.ai"] });
  assert.equal(paste(w, ta, LONG).defaultPrevented, false);
  assert.equal(sent.length, 0);
});

function drop(w, el, files) {
  const e = new w.DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: { files } });
  el.dispatchEvent(e);
  return e;
}

test("dropped PDF goes to /check_file (PG_CHECK_FILE) and a block shows the upload overlay", async () => {
  const { w, sent } = setup(() => verdict("block"));
  const zone = w.document.getElementById("zone");
  const f = new w.File([new Uint8Array([37, 80, 68, 70])], "layoff-plan.pdf", { type: "application/pdf" });
  const e = drop(w, zone, [f]);
  assert.equal(e.defaultPrevented, true);
  await tick();
  assert.equal(sent[0].type, "PG_CHECK_FILE");
  assert.equal(sent[0].name, "layoff-plan.pdf");
  assert.equal(Buffer.from(sent[0].b64, "base64").toString(), "%PDF");
  const ov = w.document.getElementById("pg-overlay");
  assert.match(ov.querySelector(".pg-title").textContent, /BLOCK \(layoff-plan.pdf\)/);
  assert.match(ov.querySelector("#pg-redact").textContent, /Copy redacted/);
});

test("dropped text file is read client side and sent as PG_CHECK with file source", async () => {
  const { w, sent } = setup(() => verdict("allow"));
  const zone = w.document.getElementById("zone");
  let replayed = 0;
  zone.addEventListener("drop", () => replayed++);
  drop(w, zone, [new w.File(["hello world, this is a note"], "notes.md")]);
  await tick();
  assert.equal(sent[0].type, "PG_CHECK");
  assert.equal(sent[0].source, "claude.ai file:notes.md");
  assert.equal(replayed, 1, "allowed drop is replayed to the page once");
});

test("dropped image is not intercepted", async () => {
  const { w, sent } = setup(() => verdict("block"));
  const e = drop(w, w.document.getElementById("zone"), [new w.File([new Uint8Array(4)], "photo.png")]);
  assert.equal(e.defaultPrevented, false);
  assert.equal(sent.length, 0);
});

test("unreadable file (HTTP 422) is let through with a clear toast", async () => {
  const { w } = setup(() => ({ ok: false, error: "Error: HTTP 422: the PDF is password protected" }));
  const zone = w.document.getElementById("zone");
  let replayed = 0;
  zone.addEventListener("drop", () => replayed++);
  drop(w, zone, [new w.File([new Uint8Array(4)], "locked.pdf")]);
  await tick();
  assert.match(w.document.getElementById("pg-toast").textContent, /could not read locked.pdf/);
  assert.equal(replayed, 1);
});

test("file picker: worst verdict across files wins and Cancel clears the input", async () => {
  const { w, sent } = setup((m) => verdict(m.name === "b.pdf" ? "block" : "coach"));
  const input = w.document.createElement("input");
  input.type = "file";
  w.document.body.appendChild(input);
  const files = [new w.File(["x".repeat(30)], "a.txt"), new w.File([new Uint8Array(4)], "b.pdf")];
  Object.defineProperty(input, "files", { value: files });
  input.dispatchEvent(new w.Event("change", { bubbles: true }));
  await tick();
  assert.equal(sent.length, 2);
  const ov = w.document.getElementById("pg-overlay");
  assert.match(ov.querySelector(".pg-title").textContent, /BLOCK \(b.pdf\)/);
  ov.querySelector("#pg-cancel").click();
  assert.equal(input.value, "");
});

test("why-this-matched panel: side by side rows, marks highlighted, HTML escaped, max 3 rows", async () => {
  const at = (t) => { const i = t.indexOf("the quick brown"); return [[i, i + 15]]; };
  const row = (i, extra = {}) => { const pt = `<img src=x onerror=alert(${i})> the quick brown fox & more`, st = `<b>src</b> the quick brown fox ${i}`;
    return { paste_span: [0, 5], paste_text: pt, paste_marks: at(pt), source_doc: "a.md", source_text: st, source_span: [0, 9],
      source_marks: at(st), kind: "ngram", score: 0.9, ...extra }; };
  const sm = { kind: "doc", path: "<i>memo.md</i>", source: "<i>memo.md</i>", lines: [1, 2], unit: "paragraphs", similarity: 0.8,
    method: "fingerprint", snippet: "s", matches: [row(1), row(2), row(3, { kind: "semantic", paste_marks: [], source_marks: [] }), row(4)] };
  const { w, ta } = setup(() => verdict("coach", { semantic_match: sm }));
  paste(w, ta, LONG);
  await tick();
  const ov = w.document.getElementById("pg-overlay");
  assert.equal(ov.querySelectorAll(".pg-why-row").length, 3);
  assert.equal(ov.querySelector("img"), null);
  assert.equal(ov.querySelector(".pg-why b"), null);
  assert.equal(ov.querySelector(".pg-why-head").textContent, "Your pasteSource: <i>memo.md</i>");
  const cells = ov.querySelectorAll(".pg-why-row")[0].querySelectorAll(".pg-why-cell");
  assert.equal(cells[0].querySelector("mark").textContent, "the quick brown");
  assert.equal(cells[1].querySelector("mark").textContent, "the quick brown");
  assert.ok(cells[0].textContent.includes("<img src=x onerror=alert(1)>"));
  assert.equal(ov.querySelectorAll(".pg-why-row")[2].querySelector("mark"), null);
  assert.ok(ov.classList.contains("pg-wide"));
});

test("no matches list: overlay has no why-panel", async () => {
  const { w, ta } = setup(() => verdict("coach", { semantic_match: { kind: "doc", path: "a.md", lines: [1, 2], similarity: 0.7, method: "embedding", snippet: "x" } }));
  paste(w, ta, LONG);
  await tick();
  assert.equal(w.document.querySelector("#pg-overlay .pg-why"), null);
});
