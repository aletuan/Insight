const DEFAULTS = {
  apiUrl: "http://localhost:8000",
  apiKey: "",
};

document.addEventListener("DOMContentLoaded", () => {
  // Load saved settings
  chrome.storage.sync.get(DEFAULTS, (items) => {
    document.getElementById("apiUrl").value = items.apiUrl;
    document.getElementById("apiKey").value = items.apiKey;
  });

  // Save settings
  document.getElementById("save").addEventListener("click", () => {
    const apiUrl = document.getElementById("apiUrl").value.replace(/\/+$/, "");
    const apiKey = document.getElementById("apiKey").value;

    chrome.storage.sync.set({ apiUrl, apiKey }, () => {
      const status = document.getElementById("status");
      status.textContent = "Saved.";
      setTimeout(() => { status.textContent = ""; }, 2000);
    });
  });
});
