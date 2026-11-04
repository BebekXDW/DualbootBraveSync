async function render() {
  const { status, statusAt, statusError } = await chrome.storage.local.get(["status", "statusAt", "statusError"]);
  const el = document.getElementById("status");
  el.textContent = status || "Nothing yet";
  el.className = statusError ? "err" : "";
  document.getElementById("when").textContent = statusAt ? new Date(statusAt).toLocaleString() : "";
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
