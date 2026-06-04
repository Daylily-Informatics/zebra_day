(function () {
  const themes = ["original", "lsmc", "dark", "light", "tacky"];
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
    for (const theme of themes) select.appendChild(new Option(theme, theme));
    select.value = currentTheme();
    select.addEventListener("change", () => applyTheme(select.value));
    document.body.appendChild(wrap);
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
