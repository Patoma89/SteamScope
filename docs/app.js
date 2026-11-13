const SKIN_PALETTES = {
  "Neón P89": {
    mode: "Dark", win_bg: "#09090b", panel_bg: "#121217", card_bg: "#111318",
    card_hover: "#1a1d26", border: "#262936", accent: "#00f0ff", accent_2: "#ff003c",
    text: "#ffffff", subtext: "#cbd5e1", price_bg: "#0b0c10", deal_badge: "#a4d007", deal_text: "#0b0c10"
  },
  "Steam Deck OLED": {
    mode: "Dark", win_bg: "#000000", panel_bg: "#0a0c0f", card_bg: "#0e1116",
    card_hover: "#161b22", border: "#1f242c", accent: "#1a9fff", accent_2: "#00e676",
    text: "#ffffff", subtext: "#cbd5e1", price_bg: "#050608", deal_badge: "#1a9fff", deal_text: "#ffffff"
  },
  "Oscuro": {
    mode: "Dark", win_bg: "#242424", panel_bg: "#2b2b2b", card_bg: "#181b20",
    card_hover: "#22262e", border: "#282c34", accent: "#38bdf8", accent_2: "#1f538d",
    text: "#f8fafc", subtext: "#cbd5e1", price_bg: "#121418", deal_badge: "#4c6b22", deal_text: "#beee11"
  },
  "Claro": {
    mode: "Light", win_bg: "#ebebeb", panel_bg: "#dbdbdb", card_bg: "#ffffff",
    card_hover: "#f1f5f9", border: "#cbd5e1", accent: "#1976d2", accent_2: "#00695c",
    text: "#0f172a", subtext: "#334155", price_bg: "#f1f5f9", deal_badge: "#2e7d32", deal_text: "#ffffff"
  },
  "Modo Drácula": {
    mode: "Dark", win_bg: "#191a21", panel_bg: "#21222c", card_bg: "#282a36",
    card_hover: "#343746", border: "#44475a", accent: "#ff5555", accent_2: "#bd93f9",
    text: "#f8f8f2", subtext: "#b3c2e6", price_bg: "#1e1f29", deal_badge: "#ff5555", deal_text: "#ffffff"
  },
  "Retro Synthwave": {
    mode: "Dark", win_bg: "#120322", panel_bg: "#1c0636", card_bg: "#240946",
    card_hover: "#310d5e", border: "#ff00ea", accent: "#00f0ff", accent_2: "#ff00ea",
    text: "#fff0ff", subtext: "#e8bfff", price_bg: "#140328", deal_badge: "#ff00ea", deal_text: "#ffffff"
  },
  "Terminal Pip-Boy": {
    mode: "Dark", win_bg: "#050b05", panel_bg: "#091409", card_bg: "#0c1c0c",
    card_hover: "#132a13", border: "#39ff14", accent: "#39ff14", accent_2: "#22c55e",
    text: "#39ff14", subtext: "#86efac", price_bg: "#040804", deal_badge: "#39ff14", deal_text: "#040804"
  },
  "Halloween Terror": {
    mode: "Dark", win_bg: "#0c0a0e", panel_bg: "#141118", card_bg: "#1c1722",
    card_hover: "#292133", border: "#ff7518", accent: "#ff7518", accent_2: "#9d4edd",
    text: "#fdf0d5", subtext: "#d8cdc9", price_bg: "#100d14", deal_badge: "#ff7518", deal_text: "#ffffff"
  }
};

function getContrastText(hex) {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  return yiq >= 150 ? "#09090b" : "#ffffff";
}

function applySkin(name) {
  const pal = SKIN_PALETTES[name];
  if (!pal) return;

  const root = document.documentElement;
  root.setAttribute("data-skin", name);
  root.style.setProperty("--win-bg", pal.win_bg);
  root.style.setProperty("--panel-bg", pal.panel_bg);
  root.style.setProperty("--card-bg", pal.card_bg);
  root.style.setProperty("--card-hover", pal.card_hover);
  root.style.setProperty("--border", pal.border);
  root.style.setProperty("--accent", pal.accent);
  root.style.setProperty("--accent-2", pal.accent_2);
  root.style.setProperty("--accent-text", getContrastText(pal.accent));
  root.style.setProperty("--text", pal.text);
  root.style.setProperty("--subtext", pal.subtext);
  root.style.setProperty("--price-bg", pal.price_bg);
  root.style.setProperty("--deal-badge", pal.deal_badge);
  root.style.setProperty("--deal-text", pal.deal_text);

  const navSelect = document.getElementById("nav-skin-select");
  if (navSelect && navSelect.value !== name) {
    navSelect.value = name;
  }

  document.querySelectorAll(".skin-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.skinName === name);
  });
}

function initSkinsGrid() {
  const grid = document.getElementById("skins-grid");
  if (!grid) return;

  Object.entries(SKIN_PALETTES).forEach(([name, pal]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "skin-card";
    btn.dataset.skinName = name;
    btn.innerHTML = `
      <div class="skin-swatches">
        <span class="skin-swatch" style="background:${pal.win_bg}"></span>
        <span class="skin-swatch" style="background:${pal.panel_bg}"></span>
        <span class="skin-swatch" style="background:${pal.accent}"></span>
        <span class="skin-swatch" style="background:${pal.accent_2}"></span>
        <span class="skin-swatch" style="background:${pal.deal_badge}"></span>
      </div>
      <strong>${name}</strong>
      <span>Modo ${pal.mode === "Light" ? "Claro" : "Oscuro"}</span>
    `;
    btn.addEventListener("click", () => applySkin(name));
    grid.appendChild(btn);
  });
}

function initCurrencyToggle() {
  const buttons = document.querySelectorAll(".curr-btn");
  const oldPrices = document.querySelectorAll(".price-old");
  const nowPrices = document.querySelectorAll(".price-now");

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const curr = btn.dataset.curr;
      buttons.forEach((b) => b.classList.toggle("active", b === btn));

      oldPrices.forEach((el) => {
        if (el.dataset[curr]) el.textContent = el.dataset[curr];
      });
      nowPrices.forEach((el) => {
        if (el.dataset[curr]) el.textContent = el.dataset[curr];
      });
    });
  });
}

function initFeatureTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(".tab-panel");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      tabBtns.forEach((b) => {
        const isActive = b === btn;
        b.classList.toggle("active", isActive);
        b.setAttribute("aria-selected", isActive ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.classList.toggle("active", panel.id === `tab-${target}`);
      });
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initSkinsGrid();
  initCurrencyToggle();
  initFeatureTabs();

  const navSelect = document.getElementById("nav-skin-select");
  if (navSelect) {
    navSelect.addEventListener("change", (e) => applySkin(e.target.value));
  }

  applySkin("Neón P89");
});
