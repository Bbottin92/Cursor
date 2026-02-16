(() => {
  const statusIndicator = document.getElementById("status-indicator");
  const loadedAt = document.getElementById("loaded-at");

  if (!statusIndicator || !loadedAt) {
    return;
  }

  statusIndicator.textContent = "Online";
  statusIndicator.style.color = "#16a34a";
  loadedAt.textContent = new Date().toLocaleString();
})();
