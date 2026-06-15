(function () {
  const themes = ["original", "light", "dark", "cbf"];
  const themeLabels = { cbf: "CBF" };
  const storageKey = "lsmc.ui.theme";

  function currentTheme() {
    const stored = window.localStorage.getItem(storageKey);
    return themes.includes(stored) ? stored : "original";
  }

  function applyTheme(theme) {
    const value = themes.includes(theme) ? theme : "original";
    document.documentElement.dataset.theme = value;
    window.localStorage.setItem(storageKey, value);
  }

  async function syncThemeFromBroker(select) {
    const response = await fetch("/api/v1/me/preferences", { credentials: "same-origin" });
    if (!response.ok) return;
    const payload = await response.json();
    const theme = payload && payload.preferences && payload.preferences.theme;
    if (!themes.includes(theme)) return;
    applyTheme(theme);
    if (select) select.value = theme;
  }

  async function persistThemeToBroker(theme) {
    await fetch("/api/v1/me/preferences", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme }),
    });
  }

  function commandForPage() {
    const explicit = document.body.dataset.actionHelpCommand || "";
    if (explicit) return explicit;
    if (location.pathname.startsWith("/printers")) return "zebra-day printer list --help";
    if (location.pathname.startsWith("/templates")) return "zebra-day template list --help";
    if (location.pathname.startsWith("/print")) return "zebra-day template print --help";
    if (location.pathname.startsWith("/config")) return "zebra-day gui status --help";
    return `No CLI equivalent for zebra-day ${location.pathname}`;
  }

  function initThemeControl() {
    const wrap = document.createElement("div");
    wrap.className = "lsmc-theme-control";
    wrap.innerHTML = '<label>Theme <select></select></label>';
    const select = wrap.querySelector("select");
    for (const theme of themes) select.appendChild(new Option(themeLabels[theme] || theme, theme));
    select.value = currentTheme();
    select.addEventListener("change", () => {
      applyTheme(select.value);
      persistThemeToBroker(select.value).catch(() => {});
    });
    document.body.appendChild(wrap);
    syncThemeFromBroker(select).catch(() => {});
  }

  function initActionHelp() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lsmc-action-help-button";
    button.textContent = "?";
    const panel = document.createElement("aside");
    panel.className = "lsmc-action-help-panel";
    panel.hidden = true;
    panel.innerHTML = '<strong>Action Help</strong><pre></pre><button type="button">Copy</button>';
    const output = panel.querySelector("pre");
    button.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      output.textContent = commandForPage();
    });
    panel.querySelector("button").addEventListener("click", () => navigator.clipboard?.writeText(output.textContent || ""));
    document.body.append(button, panel);
  }

  applyTheme(currentTheme());
  document.addEventListener("DOMContentLoaded", () => {
    initThemeControl();
    initActionHelp();
  });
})();
