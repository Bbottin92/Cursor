(function attachLiquidGovErrorHandler() {
  function report(kind, payload) {
    try {
      const line = `[${new Date().toISOString()}] ${kind}: ${JSON.stringify(payload)}`;
      console.error(line);
    } catch (error) {
      console.error("error-handler failure");
    }
  }

  window.addEventListener("error", (event) => {
    report("window.error", {
      message: event.message,
      source: event.filename,
      line: event.lineno,
      column: event.colno
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    report("window.unhandledrejection", {
      reason: String(event.reason || "unknown")
    });
  });
})();
