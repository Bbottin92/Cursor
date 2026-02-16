function formatNow() {
  return new Date().toLocaleString();
}

function updateStatus() {
  const connectionEl = document.getElementById("connection-status");
  const pathEl = document.getElementById("current-path");
  const timeEl = document.getElementById("current-time");
  const yearEl = document.getElementById("year");

  if (!connectionEl || !pathEl || !timeEl || !yearEl) {
    return;
  }

  connectionEl.textContent = navigator.onLine ? "online" : "offline";
  pathEl.textContent = window.location.pathname;
  timeEl.textContent = formatNow();
  yearEl.textContent = String(new Date().getFullYear());
}

updateStatus();
window.addEventListener("online", updateStatus);
window.addEventListener("offline", updateStatus);
