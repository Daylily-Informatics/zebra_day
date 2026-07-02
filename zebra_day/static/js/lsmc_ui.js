(function () {
  const themes = ["original", "light", "dark", "ssf", "viridis", "viridis-dark"];
  const themeLabels = { ssf: "S.SF", viridis: "Viridis", "viridis-dark": "Viridis Dark" };
  const globalStorageKey = "lsmc.ui.theme";
  const modeStoragePrefix = "lsmc.ui.theme.mode.";
  const serviceStoragePrefix = "lsmc.ui.theme.service.";
  const defaultTheme = "original";

  const service = document.documentElement.dataset.lsmcService || "zebra-day";

  function validTheme(theme) {
    return themes.includes(theme);
  }

  function serviceModeKey() {
    return `${modeStoragePrefix}${service}`;
  }

  function serviceThemeKey() {
    return `${serviceStoragePrefix}${service}`;
  }

  function isGlobalThemeMode() {
    return window.localStorage.getItem(serviceModeKey()) !== "service";
  }

  function currentTheme() {
    if (!isGlobalThemeMode()) {
      const serviceTheme = window.localStorage.getItem(serviceThemeKey());
      if (validTheme(serviceTheme)) return serviceTheme;
    }
    const globalTheme = window.localStorage.getItem(globalStorageKey);
    return validTheme(globalTheme) ? globalTheme : defaultTheme;
  }

  function applyTheme(theme, options = {}) {
    const value = validTheme(theme) ? theme : defaultTheme;
    document.documentElement.dataset.theme = value;
    if (options.persist !== false) {
      if (isGlobalThemeMode()) {
        window.localStorage.setItem(globalStorageKey, value);
      } else {
        window.localStorage.setItem(serviceThemeKey(), value);
      }
    }
    return value;
  }

  function setThemeMode(globalMode) {
    window.localStorage.setItem(serviceModeKey(), globalMode ? "global" : "service");
  }

  async function syncThemeFromBroker(select, globalCheckbox) {
    const response = await fetch("/api/v1/me/preferences", { credentials: "same-origin" });
    if (!response.ok) return;
    const payload = await response.json();
    const preferences = (payload && payload.preferences) || {};
    const serviceThemes = preferences.service_themes || preferences.theme_by_service || {};
    const theme = isGlobalThemeMode() ? preferences.theme : serviceThemes[service];
    if (!validTheme(theme)) return;
    applyTheme(theme, { persist: false });
    if (isGlobalThemeMode()) {
      window.localStorage.setItem(globalStorageKey, theme);
    } else {
      window.localStorage.setItem(serviceThemeKey(), theme);
    }
    if (select) select.value = theme;
    if (globalCheckbox) globalCheckbox.checked = isGlobalThemeMode();
    if (globalCheckbox) globalCheckbox.checked = isGlobalThemeMode();
  }

  async function persistThemeToBroker(theme) {
    const body = isGlobalThemeMode() ? { theme } : { service_themes: { [service]: theme } };
    await fetch("/api/v1/me/preferences", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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

    const label = document.createElement("label");
    label.textContent = "Theme";
    const select = document.createElement("select");
    for (const theme of themes) select.appendChild(new Option(themeLabels[theme] || theme, theme));
    select.value = currentTheme();
    label.appendChild(select);

    const modeLabel = document.createElement("label");
    modeLabel.className = "lsmc-theme-global";
    const globalCheckbox = document.createElement("input");
    globalCheckbox.type = "checkbox";
    globalCheckbox.checked = isGlobalThemeMode();
    modeLabel.append(globalCheckbox, document.createTextNode("Global"));

    select.addEventListener("change", () => {
      applyTheme(select.value);
      persistThemeToBroker(select.value).catch(() => {});
    });
    globalCheckbox.addEventListener("change", () => {
      setThemeMode(globalCheckbox.checked);
      select.value = currentTheme();
      applyTheme(select.value);
      persistThemeToBroker(select.value).catch(() => {});
    });

    wrap.append(label, modeLabel);
    document.body.appendChild(wrap);
    syncThemeFromBroker(select, globalCheckbox).catch(() => {});
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
