// Cookie Sync (dual boot)
// Keeps a shared cookies file up to date while Brave runs, and loads it
// when Brave starts if the other OS saved something newer.

const HOST = "com.cookiesync.host";
const CHUNK = 250000; // characters per read; native replies are capped at 1 MB
const SAVE_DELAY_MS = 2000;

let saveTimer = null;
let quietUntil = 0; // ignore the cookie changes our own import causes
let chain = Promise.resolve(); // runs one sync job at a time

// ---------- helpers ----------

function native(msg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage(HOST, msg, (reply) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!reply || !reply.ok) return reject(new Error((reply && reply.error) || "No reply from helper"));
      resolve(reply);
    });
  });
}

function queue(job) {
  chain = chain.then(job, job).catch((e) => setStatus("Error: " + e.message, true));
  return chain;
}

async function setStatus(text, isError = false) {
  await chrome.storage.local.set({ status: text, statusAt: Date.now(), statusError: isError });
}

async function getLastSync() {
  return (await chrome.storage.local.get("lastSync")).lastSync || 0;
}

async function collectCookies() {
  let cookies;
  try {
    // Includes partitioned (CHIPS) cookies on newer Chromium.
    cookies = await chrome.cookies.getAll({ partitionKey: {} });
  } catch {
    cookies = await chrome.cookies.getAll({});
  }
  return cookies;
}

function cookieKey(c) {
  const pk = c.partitionKey ? c.partitionKey.topLevelSite || "" : "";
  return [c.name, c.domain, c.path, pk].join("\u0001");
}

function cookieUrl(c) {
  const host = c.domain.startsWith(".") ? c.domain.slice(1) : c.domain;
  return `http${c.secure ? "s" : ""}://${host}${c.path}`;
}

function setDetails(c) {
  const d = {
    url: cookieUrl(c),
    name: c.name,
    value: c.value,
    path: c.path,
    secure: c.secure,
    httpOnly: c.httpOnly,
    sameSite: c.sameSite,
  };
  if (!c.hostOnly) d.domain = c.domain;
  if (!c.session && c.expirationDate) d.expirationDate = c.expirationDate;
  if (c.partitionKey) d.partitionKey = c.partitionKey;
  return d;
}

// ---------- save ----------

async function saveNow(reason) {
  const info = await native({ cmd: "info" });
  const lastSync = await getLastSync();
  if (info.exists && info.savedAt > lastSync) {
    // The other OS wrote a newer file that we haven't loaded yet.
    // Load it instead of overwriting it.
    await loadNow("newer file found");
    return;
  }
  const cookies = await collectCookies();
  const { os } = await chrome.runtime.getPlatformInfo();
  const savedAt = Date.now();
  await native({
    cmd: "save",
    payload: JSON.stringify({ version: 1, savedAt, machine: os, cookies }),
  });
  await chrome.storage.local.set({ lastSync: savedAt });
  await chrome.storage.session.set({ dirty: false });
  await setStatus(`Saved ${cookies.length} cookies (${reason})`);
}

// ---------- load ----------

async function readFile() {
  let text = "";
  let offset = 0;
  for (;;) {
    const r = await native({ cmd: "read", offset, length: CHUNK });
    text += r.chunk;
    offset += r.chunk.length;
    if (offset >= r.total || r.chunk.length === 0) break;
  }
  return JSON.parse(text);
}

async function loadNow(reason) {
  const data = await readFile();
  if (!data || !Array.isArray(data.cookies) || data.cookies.length === 0) {
    throw new Error("Shared file is empty or damaged; not loading it");
  }

  const now = Date.now() / 1000;
  const wanted = new Map();
  for (const c of data.cookies) {
    if (!c.session && c.expirationDate && c.expirationDate < now) continue;
    wanted.set(cookieKey(c), c);
  }

  const current = await collectCookies();
  const currentMap = new Map(current.map((c) => [cookieKey(c), c]));

  let set = 0, removed = 0, failed = 0;
  quietUntil = Infinity;

  for (const [key, c] of wanted) {
    const have = currentMap.get(key);
    if (have && have.value === c.value && have.expirationDate === c.expirationDate) continue;
    try {
      const ok = await chrome.cookies.set(setDetails(c));
      ok ? set++ : failed++;
    } catch {
      failed++;
    }
  }

  // Cookies this OS has but the newer file doesn't (e.g. you logged out on
  // the other OS) are removed so both sides end up identical.
  for (const [key, c] of currentMap) {
    if (wanted.has(key)) continue;
    const details = { url: cookieUrl(c), name: c.name };
    if (c.partitionKey) details.partitionKey = c.partitionKey;
    try {
      await chrome.cookies.remove(details);
      removed++;
    } catch {}
  }

  quietUntil = Date.now() + 3000;
  await chrome.storage.local.set({ lastSync: data.savedAt });
  await chrome.storage.session.set({ dirty: false });
  await setStatus(
    `Loaded from ${data.machine || "other OS"}: ${set} set, ${removed} removed` +
      (failed ? `, ${failed} skipped` : "") + ` (${reason})`
  );

  if (set + removed > 0) {
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) {
      if (t.url && /^https?:/.test(t.url)) chrome.tabs.reload(t.id);
    }
  }
}

// ---------- startup check ----------

async function checkForNewer(reason) {
  const info = await native({ cmd: "info" });
  const lastSync = await getLastSync();
  if (info.exists && info.savedAt > lastSync) {
    await loadNow(reason);
  } else {
    await setStatus(info.exists ? "Up to date" : "No shared file yet; it will be created on first save");
  }
  await chrome.storage.session.set({ ready: true });
}

async function ensureReady() {
  const { ready } = await chrome.storage.session.get("ready");
  if (!ready) await queue(() => checkForNewer("Brave started"));
}

// ---------- events ----------

chrome.runtime.onStartup.addListener(() => queue(() => checkForNewer("Brave started")));
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("periodic", { periodInMinutes: 1 });
  queue(() => checkForNewer("extension installed"));
});

// If Brave was kept running in the background, opening a new window
// is the moment you come back to it.
chrome.windows.onCreated.addListener(() => queue(() => checkForNewer("window opened")));

chrome.cookies.onChanged.addListener(async () => {
  if (Date.now() < quietUntil) return;
  await chrome.storage.session.set({ dirty: true });
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    await ensureReady();
    queue(() => saveNow("cookies changed"));
  }, SAVE_DELAY_MS);
});

// Save straight away when the last window closes (Brave quitting).
chrome.windows.onRemoved.addListener(async () => {
  const wins = await chrome.windows.getAll();
  if (wins.length === 0) {
    clearTimeout(saveTimer);
    queue(() => saveNow("Brave closing"));
  }
});

chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name !== "periodic") return;
  await ensureReady();
  const { dirty } = await chrome.storage.session.get("dirty");
  if (dirty) queue(() => saveNow("periodic"));
});

// Buttons in the popup
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  const jobs = {
    save: () => saveNow("manual"),
    load: () => loadNow("manual"),
    ping: async () => {
      const r = await native({ cmd: "info" });
      await setStatus(`Helper OK. File: ${r.path}${r.exists ? "" : " (not created yet)"}`);
    },
  };
  if (jobs[msg.cmd]) {
    queue(jobs[msg.cmd]).then(() => reply({ done: true }));
    return true;
  }
  if (msg.cmd === "details") {
    details().then(reply, (e) => reply({ error: e.message }));
    return true;
  }
});

// Profile sync result + extensions installed on the other system but not here.
// (Brave doesn't let one extension install others, so the popup links to them.)
async function details() {
  const info = await native({ cmd: "info" });
  const snap = await native({ cmd: "extensions" });
  const here = new Set((await chrome.management.getAll()).map((e) => e.id));
  here.add(chrome.runtime.id);
  return {
    profile: info.profile || {},
    machine: snap.machine,
    missing: (snap.extensions || []).filter((e) => !here.has(e.id)),
  };
}
