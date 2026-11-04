async function render() {
  const { status, statusAt, statusError } = await chrome.storage.local.get(["status", "statusAt", "statusError"]);
  const el = document.getElementById("status");
  el.textContent = status || "Nothing yet";
  el.className = statusError ? "err" : "";
  document.getElementById("when").textContent = statusAt ? new Date(statusAt).toLocaleString() : "";
}

function extName(e) {
  return e.name && !e.name.startsWith("__MSG_") ? e.name : `Extension ${e.id}`;
}

function renderDetails(d) {
  const ps = document.getElementById("pstatus");
  const pw = document.getElementById("pwhen");
  const box = document.getElementById("missing");
  box.textContent = "";
  if (!d || d.error) {
    ps.textContent = "Helper not reachable: " + ((d && d.error) || "no reply");
    ps.className = "box err";
    return;
  }
  const p = d.profile || {};
  ps.textContent = p.message || "Not synced yet. Start Brave from the \"Brave (Sync)\" shortcut / menu entry.";
  ps.className = p.error ? "box err" : "box";
  pw.textContent = p.at ? new Date(p.at).toLocaleString() : "";

  if (!d.missing || d.missing.length === 0) return;
  const title = document.createElement("div");
  title.textContent = `Installed on ${d.machine || "the other system"} but not here:`;
  const ul = document.createElement("ul");
  for (const e of d.missing) {
    const li = document.createElement("li");
    if (e.unpacked) {
      li.textContent = `${extName(e)} (unpacked: load it by hand)`;
    } else {
      const a = document.createElement("a");
      a.textContent = extName(e);
      a.title = "Open its store page";
      a.addEventListener("click", () =>
        chrome.tabs.create({ url: `https://chromewebstore.google.com/detail/${e.id}` }));
      li.appendChild(a);
    }
    ul.appendChild(li);
  }
  box.append(title, ul);
}

document.querySelectorAll("button").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll("button").forEach((x) => (x.disabled = true));
    chrome.runtime.sendMessage({ cmd: b.dataset.cmd }, () => {
      document.querySelectorAll("button").forEach((x) => (x.disabled = false));
      render();
    });
  });
});

chrome.storage.onChanged.addListener(render);
render();
chrome.runtime.sendMessage({ cmd: "details" }, renderDetails);
