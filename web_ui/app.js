/* =====================================================================
   SteamScope 3.0 NEXT — Controlador Frontend (pywebview API Bridge)
   ===================================================================== */

const RING_CIRCUMFERENCE = 2 * Math.PI * 29;

const PHASE_INFO = {
  deals: {
    phase: "FASE 2 · EXPLORACIÓN",
    title: "Ofertas & Búsqueda de Steam",
    desc: "Escaneo multi-hilo con precios regionales AR en lote, filtros jerárquicos de 2 niveles, píldoras KPI, 3 modos de vista (Normal, Compacta, Grilla) y Changuito con Budget Tracker."
  },
  radar: {
    phase: "FASE 5 · MULTI-TIENDA",
    title: "Radar Epic Games & GOG",
    desc: "Monitor de juegos 100% gratis semanales en Epic Games Store y catálogo sin DRM de GOG con alertas de tiempo límite y reclamo directo."
  },
  atl: {
    phase: "FASE 4 · CENTINELA",
    title: "Historial de Récords ATL",
    desc: "Registro completo de mínimos históricos detectados en tu Watchlist y escaneos, con alertas interactivas y apertura directa de Ficha Técnica."
  },
  watchlist: {
    phase: "FASE 4 · SEGUIMIENTO",
    title: "Mi Watchlist & Precios Objetivo",
    desc: "Importación rápida de Wishlist de Steam, comprobación paralela de rebajas, etiquetas personalizadas y alertas por Precio Objetivo (🎯)."
  },
  library: {
    phase: "FASE 4 · CUENTA STEAM",
    title: "Mi Biblioteca, Valuador & Radar Co-op",
    desc: "Lectura en 0 ms desde caché SQLite paginada, valuador de cuenta ($/hora y juegos 0 hs), sorteo de backlog y cruce multijugador con amigos."
  },
  cards: {
    phase: "FASE 4 · INVENTARIO",
    title: "Gestor de Cromos & Billetera Steam",
    desc: "Valorizador inteligente de cromos acumulables calculando el -15% de comisión de mercado para financiar compras."
  },
  dashboard: {
    phase: "FASE 5 · ANALÍTICA GPU",
    title: "Dashboard Visual de Estadísticas",
    desc: "Gráficos interactivos en vivo de distribución de descuentos, top géneros, estado de tu backlog y juegos más jugados."
  },
  versus: {
    phase: "FASE 3 · COMPARATIVA",
    title: "Comparador Cara a Cara (Versus)",
    desc: "Enfrentá dos juegos lado a lado en precio USD/ARS, descuento, mínimo histórico, Metacritic, peso en disco y ProtonDB."
  },
  roulette: {
    phase: "FASE 5 · SORTEO 60 FPS",
    title: "Ruleta Loot Box (Spin-In-Place)",
    desc: "Sorteo fluido a 60 FPS sobre ofertas destacadas o tu backlog sin cerrar la ventana y con validación anti-duplicados."
  },
  events: {
    phase: "FASE 5 · CALENDARIO",
    title: "Eventos Oficiales de Steam & Calculadora ARS",
    desc: "Cuenta regresiva para próximas rebajas estacionales de Valve y simulador de cotización Tarjeta vs. Cripto / Web."
  },
  settings: {
    phase: "FASE 5 · CONFIGURACIÓN",
    title: "Ajustes, API Key, Discord & Backup",
    desc: "Configuración de Steam ID, API Key, Dólar en vivo, Discord Webhook, Gestor de Blacklist y respaldo portátil en .zip."
  }
};

const state = {
  bootstrap: null,
  cc: null,
  activeTab: "command_center",
  moneda: "USD",
  searchDebounce: null
};

function hexToRgbTuple(hex) {
  const clean = (hex || "#38bdf8").replace("#", "");
  const full = clean.length === 3 ? clean.split("").map(c => c + c).join("") : clean;
  const num = parseInt(full, 16);
  if (Number.isNaN(num)) return "56, 189, 248";
  return `${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}`;
}

function getContrastText(hex) {
  const clean = (hex || "#38bdf8").replace("#", "");
  const full = clean.length === 3 ? clean.split("").map(c => c + c).join("") : clean;
  const r = parseInt(full.substring(0, 2), 16) || 0;
  const g = parseInt(full.substring(2, 4), 16) || 0;
  const b = parseInt(full.substring(4, 6), 16) || 0;
  const yiq = (r * 299 + g * 587 + b * 114) / 1000;
  return yiq >= 150 ? "#09090b" : "#ffffff";
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showToast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2600);
}

function applySkinPalette(skinId, palette) {
  if (!palette) return;
  const r = document.documentElement.style;
  const mode = palette.mode === "Light" ? "Light" : "Dark";
  document.documentElement.setAttribute("data-mode", mode);

  r.setProperty("--win-bg", palette.win_bg || "#242424");
  r.setProperty("--panel-bg", palette.panel_bg || "#2b2b2b");
  r.setProperty("--card-bg", palette.card_bg || "#181b20");
  r.setProperty("--card-glass", `rgba(${hexToRgbTuple(palette.card_bg || "#181b20")}, 0.85)`);
  r.setProperty("--card-hover", palette.card_hover || "#22262e");
  r.setProperty("--price-bg", palette.price_bg || "#121418");
  r.setProperty("--border", palette.border || "#282c34");
  r.setProperty("--accent", palette.accent || "#38bdf8");
  r.setProperty("--accent-rgb", hexToRgbTuple(palette.accent || "#38bdf8"));
  r.setProperty("--accent-2", palette.accent_2 || "#1f538d");
  r.setProperty("--accent-text", getContrastText(palette.accent || "#38bdf8"));
  r.setProperty("--text", palette.text || "#f8fafc");
  r.setProperty("--subtext", palette.subtext || "#cbd5e1");
  r.setProperty("--deal-badge", palette.deal_badge || "#4c6b22");
  r.setProperty("--deal-text", palette.deal_text || "#beee11");

  const sel = document.getElementById("hud-skin-select");
  if (sel && sel.value !== skinId) sel.value = skinId;
}

function setRing(ringId, pctId, pct, customCenterText = null) {
  const ring = document.getElementById(ringId);
  const pctEl = document.getElementById(pctId);
  const clamped = Math.max(0, Math.min(100, Number(pct) || 0));
  if (ring) {
    ring.style.strokeDasharray = `${RING_CIRCUMFERENCE}`;
    ring.style.strokeDashoffset = `${RING_CIRCUMFERENCE * (1 - clamped / 100)}`;
  }
  if (pctEl) pctEl.textContent = customCenterText !== null ? customCenterText : `${Math.round(clamped)}%`;
}

function formatPrice(usdVal) {
  const usd = Number(usdVal) || 0;
  const fx = state.cc?.fx || { dolar_referencia: 1000, dolar_cripto_ref: 1150, impuestos_pct: 60 };
  if (state.moneda === "ARS (Cripto)") {
    return `$${Math.round(usd * fx.dolar_cripto_ref).toLocaleString("es-AR")} ARS`;
  }
  if (state.moneda === "ARS (Tarjeta)") {
    const mult = 1 + (fx.impuestos_pct / 100);
    return `$${Math.round(usd * fx.dolar_referencia * mult).toLocaleString("es-AR")} ARS`;
  }
  return `$${usd.toFixed(2)} USD`;
}

function renderCommandCenter(cc) {
  if (!cc) return;
  state.cc = cc;
  const fx = cc.fx || {};
  state.moneda = fx.moneda || state.moneda;

  const currSel = document.getElementById("hud-currency-select");
  if (currSel && currSel.value !== state.moneda) currSel.value = state.moneda;

  const dolarBase = Number(fx.dolar_referencia || 1000);
  const dolarCripto = Number(fx.dolar_cripto_ref || Math.round(dolarBase * 1.15));
  const impPct = Number(fx.impuestos_pct ?? 60);
  const dolarTarjeta = Math.round(dolarBase * (1 + impPct / 100));

  document.getElementById("hud-dolar-lbl").textContent = `$${Math.round(dolarBase).toLocaleString("es-AR")}`;
  document.getElementById("hud-cripto-lbl").textContent = `🪙 $${Math.round(dolarCripto).toLocaleString("es-AR")}`;
  document.getElementById("cc-fx-imp").textContent = `Imp: +${impPct}%`;
  document.getElementById("cc-fx-tarjeta").textContent = `$${dolarTarjeta.toLocaleString("es-AR")} ARS`;
  document.getElementById("cc-fx-cripto").textContent = `$${Math.round(dolarCripto).toLocaleString("es-AR")} ARS`;

  // KPI 1: Récords ATL
  const atlCnt = cc.atl?.count || 0;
  document.getElementById("kpi-atl-num").textContent = String(atlCnt);
  document.getElementById("kpi-atl-meta").textContent = atlCnt > 0
    ? `Último: ${cc.atl.recent[0]?.titulo || "Detectado"}`
    : "Sin alertas capturadas aún";
  setRing("ring-atl", "ring-atl-pct", Math.min(100, atlCnt * 10), String(atlCnt));

  const navAtl = document.getElementById("nav-atl-badge");
  if (navAtl) {
    navAtl.textContent = String(atlCnt);
    navAtl.style.display = atlCnt > 0 ? "inline-flex" : "none";
  }

  // KPI 2: Watchlist
  const wlTotal = cc.watchlist?.total || 0;
  const wlTargets = cc.watchlist?.with_target || 0;
  const wlPct = wlTotal > 0 ? Math.round((wlTargets / wlTotal) * 100) : 0;
  document.getElementById("kpi-wl-num").textContent = String(wlTotal);
  document.getElementById("kpi-wl-targets").textContent = `${wlTargets} con meta 🎯`;
  document.getElementById("cc-wl-badge").textContent = `${wlTotal} juegos`;
  setRing("ring-wl", "ring-wl-pct", wlPct);

  // KPI 3: Backlog Jugado
  const libTotal = cc.backlog?.total || 0;
  const sinJugar = cc.backlog?.sin_jugar || 0;
  const jugadosPct = libTotal > 0 ? Math.round(((libTotal - sinJugar) / libTotal) * 100) : 0;
  document.getElementById("kpi-lib-num").textContent = String(libTotal);
  document.getElementById("kpi-lib-hours").textContent = `${cc.backlog?.horas_totales || 0} hs`;
  document.getElementById("kpi-lib-unplayed").textContent = `${sinJugar} sin estrenar`;
  setRing("ring-lib", "ring-lib-pct", jugadosPct);

  // KPI 4: Changuito
  const cart = cc.cart || {};
  const cartTotalTxt = formatPrice(cart.total_usd || 0);
  document.getElementById("kpi-cart-num").textContent = cartTotalTxt;
  document.getElementById("kpi-cart-sub").textContent = `${cart.count || 0} juegos · Ahorro ${formatPrice(cart.ahorro_usd || 0)}`;
  document.getElementById("kpi-cart-budget").textContent = cart.budget_usd > 0 ? `Tope $${cart.budget_usd} USD` : "Sin tope";
  document.getElementById("hud-cart-lbl").textContent = `${cart.count || 0} · ${cartTotalTxt}`;
  setRing("ring-cart", "ring-cart-pct", cart.budget_usd > 0 ? cart.budget_pct : (cart.count > 0 ? 100 : 0));

  // Lista Watchlist
  const wlEl = document.getElementById("cc-watchlist-list");
  const wlItems = cc.watchlist?.items || [];
  if (!wlItems.length) {
    wlEl.innerHTML = `<div class="empty-state">Tu Watchlist está vacía. Agregá juegos desde Ofertas o sincronizá tu Wishlist.</div>`;
  } else {
    wlEl.innerHTML = wlItems.map(it => `
      <div class="cc-row">
        <div class="cc-row-main">
          <div class="cc-row-title">${escapeHtml(it.titulo)}</div>
          <div class="cc-row-sub">
            ${it.tag ? `🏷️ ${escapeHtml(it.tag)} · ` : ""}
            ${it.target_price > 0 ? `🎯 Meta: $${it.target_price.toFixed(2)} USD` : `AppID ${escapeHtml(it.appid)}`}
          </div>
        </div>
        <span class="cc-price-tag">${escapeHtml(formatPrice(it.precio_usd))}</span>
      </div>
    `).join("");
  }

  // Lista ATL
  const atlEl = document.getElementById("cc-atl-list");
  const atlItems = cc.atl?.recent || [];
  if (!atlItems.length) {
    atlEl.innerHTML = `<div class="empty-state">Todavía no hay récords ATL registrados en el historial local.</div>`;
  } else {
    atlEl.innerHTML = atlItems.map(a => `
      <div class="cc-row">
        <div class="cc-row-main">
          <div class="cc-row-title">${escapeHtml(a.titulo)}</div>
          <div class="cc-row-sub">📅 ${escapeHtml(a.fecha)}</div>
        </div>
        <span class="cc-discount-tag">-${a.descuento}%</span>
        <span class="cc-price-tag">${escapeHtml(formatPrice(a.precio_usd))}</span>
      </div>
    `).join("");
  }
}

function navigateTo(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });

  const ccView = document.getElementById("view-command_center");
  const dynView = document.getElementById("view-dynamic");

  if (tabId === "command_center") {
    ccView.style.display = "block";
    dynView.style.display = "none";
    return;
  }

  ccView.style.display = "none";
  dynView.style.display = "block";

  if (tabId === "deals" && window.DealsView) {
    window.DealsView.mount(dynView);
    return;
  }

  if (tabId === "versus" && window.FichaView) {
    window.FichaView.mountVersus(dynView);
    return;
  }

  if (tabId === "watchlist" && window.AccountView) {
    window.AccountView.mountWatchlist(dynView);
    return;
  }

  if (tabId === "atl" && window.AccountView) {
    window.AccountView.mountATL(dynView);
    return;
  }

  if (tabId === "library" && window.AccountView) {
    window.AccountView.mountLibrary(dynView);
    return;
  }

  if (tabId === "cards" && window.AccountView) {
    window.AccountView.mountCards(dynView);
    return;
  }

  if (window.ToolsView) {
    if (tabId === "radar") { window.ToolsView.mountRadar(dynView); return; }
    if (tabId === "dashboard") { window.ToolsView.mountDashboard(dynView); return; }
    if (tabId === "roulette") { window.ToolsView.mountRoulette(dynView); return; }
    if (tabId === "events") { window.ToolsView.mountEvents(dynView); return; }
    if (tabId === "settings") { window.ToolsView.mountSettings(dynView); return; }
  }

  const info = PHASE_INFO[tabId] || { phase: "PRÓXIMAMENTE", title: tabId, desc: "Módulo en migración hacia SteamScope 3.0 NEXT." };
  dynView.innerHTML = `
    <div class="glass-card phase-placeholder">
      <span class="phase-badge">${escapeHtml(info.phase)}</span>
      <h2>${escapeHtml(info.title)}</h2>
      <p>${escapeHtml(info.desc)}</p>
      <button class="btn-primary-accent" id="btn-back-cc">← Volver al Centro de Mando</button>
    </div>
  `;
  document.getElementById("btn-back-cc")?.addEventListener("click", () => navigateTo("command_center"));
}

async function openCartModal() {
  openModal("modal-cart");
  const res = await window.pywebview.api.get_cart();
  renderCartModal(res);
}

function renderCartModal(res) {
  const body = document.getElementById("cart-modal-body");
  if (!body) return;
  const items = res?.items || [];
  const s = res?.summary || {};
  const status = s.budget_status || "none";
  const pctClamp = Math.min(100, Number(s.budget_pct || 0));

  let budgetLabel = "Presupuesto sin tope";
  if (status === "over") {
    budgetLabel = `🚨 Excedido (+$${Math.abs(s.remaining_usd).toFixed(2)} USD sobre $${s.budget_usd.toFixed(2)})`;
  } else if (status === "warn") {
    budgetLabel = `⚠️ Cerca del límite (${s.budget_pct}% · Quedan $${s.remaining_usd.toFixed(2)} USD)`;
  } else if (status === "ok") {
    budgetLabel = `🎯 Dentro del presupuesto (${s.budget_pct}% · Quedan $${s.remaining_usd.toFixed(2)} USD)`;
  }

  body.innerHTML = `
    <div class="cart-summary-grid">
      <div class="cart-stat-box">
        <span>💵 Total USD</span>
        <strong>$${Number(s.total_usd || 0).toFixed(2)} USD</strong>
      </div>
      <div class="cart-stat-box">
        <span>💳 ARS Tarjeta</span>
        <strong>$${Number(s.total_ars_tarjeta || 0).toLocaleString("es-AR")} ARS</strong>
      </div>
      <div class="cart-stat-box">
        <span>🪙 ARS Cripto</span>
        <strong>$${Number(s.total_ars_cripto || 0).toLocaleString("es-AR")} ARS</strong>
      </div>
    </div>

    <div class="budget-box">
      <div class="budget-head">
        <strong>${escapeHtml(budgetLabel)}</strong>
        <div style="display:flex;gap:6px;align-items:center">
          <input type="number" id="cart-budget-input" class="t-input" style="width:110px" min="0" max="9999" step="1" placeholder="Tope USD" value="${s.budget_usd > 0 ? s.budget_usd : ""}" />
          <button type="button" class="btn-ghost" id="btn-save-budget">Fijar Tope</button>
        </div>
      </div>
      ${s.budget_usd > 0 ? `<div class="budget-track"><div class="budget-fill ${status}" style="width:${pctClamp}%"></div></div>` : ""}
      <div style="font-size:11.5px;color:var(--subtext)">
        🎉 Ahorro acumulado en rebajas: <strong>$${Number(s.ahorro_usd || 0).toFixed(2)} USD</strong> (${s.ahorro_pct || 0}% OFF global)
      </div>
    </div>

    <div class="cart-items-scroll">
      ${items.length ? items.map(it => `
        <div class="cc-row">
          <div class="cc-row-main">
            <div class="cc-row-title">${escapeHtml(it.titulo)}</div>
            <div class="cc-row-sub">-${Number(it.descuento || 0)}% · Normal $${Number(it.precio_normal_usd || 0).toFixed(2)} USD</div>
          </div>
          <span class="cc-price-tag">${escapeHtml(formatPrice(it.precio_oferta_usd))}</span>
          <button type="button" class="btn-ghost btn-cart-rm" data-appid="${escapeHtml(it.appid)}">✕</button>
        </div>
      `).join("") : `<div class="empty-state">Tu changuito está vacío. Sumá juegos desde el Explorador de Ofertas.</div>`}
    </div>

    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
      <button type="button" class="btn-danger" id="btn-clear-cart" ${items.length ? "" : "disabled"}>🗑 Vaciar Changuito</button>
      <button type="button" class="btn-primary-accent" id="btn-cart-done">Listo</button>
    </div>
  `;

  document.getElementById("btn-save-budget")?.addEventListener("click", async () => {
    const val = Number(document.getElementById("cart-budget-input")?.value || 0);
    const upd = await window.pywebview.api.set_cart_budget(val);
    if (upd?.ok) {
      renderCommandCenter(upd.command_center);
      renderCartModal(upd.cart);
      showToast(val > 0 ? `🎯 Presupuesto fijado en $${val.toFixed(2)} USD` : "🎯 Tope desactivado");
    }
  });

  document.getElementById("btn-clear-cart")?.addEventListener("click", async () => {
    const upd = await window.pywebview.api.clear_cart();
    if (upd?.ok) {
      renderCommandCenter(upd.command_center);
      renderCartModal(upd.cart);
      if (state.activeTab === "deals" && window.DealsView) window.DealsView.refresh();
      showToast("🗑 Changuito vaciado");
    }
  });

  document.getElementById("btn-cart-done")?.addEventListener("click", () => closeModal("modal-cart"));

  body.querySelectorAll(".btn-cart-rm").forEach(btn => {
    btn.addEventListener("click", async () => {
      const target = items.find(i => String(i.appid) === btn.dataset.appid);
      if (!target) return;
      const upd = await window.pywebview.api.toggle_cart_item(target);
      if (upd?.ok) {
        renderCommandCenter(upd.command_center);
        renderCartModal(upd.cart);
        if (state.activeTab === "deals" && window.DealsView) window.DealsView.refresh();
      }
    });
  });
}

function openModal(id) {
  document.getElementById(id)?.classList.add("open");
}

function closeModal(id) {
  document.getElementById(id)?.classList.remove("open");
}

async function runSpotlightSearch(query) {
  const box = document.getElementById("spotlight-results");
  if (!box) return;
  if ((query || "").trim().length < 2) {
    box.innerHTML = `<div class="empty-state">Escribí al menos 2 caracteres para buscar al instante en tu catálogo local…</div>`;
    return;
  }
  const res = await window.pywebview.api.global_search(query);
  const items = res?.results || [];
  if (!items.length) {
    box.innerHTML = `<div class="empty-state">Sin coincidencias para "${escapeHtml(query)}".</div>`;
    return;
  }
  box.innerHTML = items.map((it, idx) => `
    <div class="search-row" data-idx="${idx}">
      <span class="search-cat">${escapeHtml(it.kind)}</span>
      <div class="search-main">
        <div class="search-title">${escapeHtml(it.title)}</div>
        <div class="search-sub">${escapeHtml(it.subtitle)}</div>
      </div>
      <span class="kbd-badge">${escapeHtml(it.badge || "")}</span>
    </div>
  `).join("");

  box.querySelectorAll(".search-row").forEach(row => {
    row.addEventListener("click", () => {
      const it = items[Number(row.dataset.idx)];
      closeModal("modal-spotlight");
      if (it?.tab) navigateTo(it.tab);
    });
  });
}

async function openPatchNotes() {
  openModal("modal-notes");
  const body = document.getElementById("notes-body");
  body.innerHTML = `<div class="empty-state">Cargando notas de versión...</div>`;
  const notes = await window.pywebview.api.get_patch_notes();
  body.innerHTML = (notes || []).map(n => `
    <div class="glass-card" style="padding:12px 14px;display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong style="color:var(--accent)">${escapeHtml(n.version)}</strong>
        <span style="font-size:11px;color:var(--subtext)">${escapeHtml(n.fecha)}</span>
      </div>
      <ul style="padding-left:18px;display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--subtext)">
        ${(n.cambios || []).map(c => `<li>${escapeHtml(c)}</li>`).join("")}
      </ul>
    </div>
  `).join("");
}

async function openUpdateModal() {
  openModal("modal-update");
  const body = document.getElementById("update-body");
  body.innerHTML = `<div class="empty-state">Consultando última versión en GitHub...</div>`;
  const res = await window.pywebview.api.check_updates();
  if (!res || !res.ok) {
    body.innerHTML = `
      <div>No se pudo verificar actualizaciones (${escapeHtml(res?.error || "sin conexión")}).</div>
      <button class="btn-primary-accent" id="btn-upd-web">Abrir Releases en GitHub</button>
    `;
    document.getElementById("btn-upd-web")?.addEventListener("click", () => {
      window.pywebview.api.open_external_url(res?.fallback_url || "https://github.com/Patoma89/SteamScope/releases");
    });
    return;
  }

  if (res.has_update) {
    body.innerHTML = `
      <div>🚀 <strong>¡Nueva versión disponible!</strong> (${escapeHtml(res.current_version)} → <strong>v${escapeHtml(res.latest_version)}</strong>)</div>
      <ul style="padding-left:18px;font-size:12px;color:var(--subtext)">
        ${(res.notas || []).map(n => `<li>${escapeHtml(n)}</li>`).join("")}
      </ul>
      <button class="btn-primary-accent" id="btn-upd-dl">Descargar Actualización</button>
    `;
    document.getElementById("btn-upd-dl")?.addEventListener("click", () => {
      window.pywebview.api.open_external_url(res.url);
    });
  } else {
    body.innerHTML = `
      <div>✅ Estás usando la última versión disponible (<strong>v${escapeHtml(res.current_version)}</strong>).</div>
    `;
  }
}

function wireEvents() {
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => navigateTo(btn.dataset.tab));
  });

  document.querySelectorAll("[data-goto]").forEach(el => {
    el.addEventListener("click", () => navigateTo(el.dataset.goto));
  });

  document.getElementById("btn-explore-deals")?.addEventListener("click", () => navigateTo("deals"));

  document.getElementById("btn-collapse")?.addEventListener("click", async () => {
    const shell = document.getElementById("app-shell");
    const collapsed = shell.classList.toggle("collapsed");
    await window.pywebview.api.set_sidebar_collapsed(collapsed);
  });

  document.getElementById("hud-skin-select")?.addEventListener("change", async (e) => {
    const res = await window.pywebview.api.set_skin(e.target.value);
    if (res?.ok) {
      applySkinPalette(res.skin_id, res.palette);
      showToast(`🎨 Skin aplicada: ${res.skin_id}`);
    }
  });

  document.getElementById("hud-currency-select")?.addEventListener("change", async (e) => {
    const res = await window.pywebview.api.set_moneda(e.target.value);
    if (res?.ok) {
      state.moneda = res.moneda;
      renderCommandCenter(res.command_center);
      if (state.activeTab === "deals" && window.DealsView) {
        window.DealsView.refreshPrices();
      }
      if (["watchlist", "atl", "library", "cards"].includes(state.activeTab) && window.AccountView) {
        window.AccountView.refreshActive(state.activeTab);
      }
      if (document.getElementById("modal-cart")?.classList.contains("open")) {
        const cartRes = await window.pywebview.api.get_cart();
        renderCartModal(cartRes);
      }
      showToast(`💱 Moneda cambiada a ${res.moneda}`);
    }
  });

  document.getElementById("hud-cart-chip")?.addEventListener("click", openCartModal);
  document.getElementById("btn-close-cart")?.addEventListener("click", () => closeModal("modal-cart"));

  document.getElementById("btn-topmost")?.addEventListener("click", async () => {
    const res = await window.pywebview.api.toggle_always_on_top();
    const btn = document.getElementById("btn-topmost");
    btn?.classList.toggle("active", Boolean(res?.always_on_top));
    showToast(res?.always_on_top ? "📌 Ventana fijada siempre encima" : "📌 Ventana liberada");
  });

  // Modales
  document.getElementById("btn-open-search")?.addEventListener("click", () => {
    openModal("modal-spotlight");
    setTimeout(() => document.getElementById("spotlight-input")?.focus(), 40);
  });

  document.getElementById("spotlight-input")?.addEventListener("input", (e) => {
    clearTimeout(state.searchDebounce);
    const q = e.target.value;
    state.searchDebounce = setTimeout(() => runSpotlightSearch(q), 90);
  });

  document.getElementById("btn-socials")?.addEventListener("click", () => openModal("modal-socials"));
  document.getElementById("btn-close-socials")?.addEventListener("click", () => closeModal("modal-socials"));
  document.getElementById("btn-patch-notes")?.addEventListener("click", openPatchNotes);
  document.getElementById("btn-close-notes")?.addEventListener("click", () => closeModal("modal-notes"));
  document.getElementById("btn-github-update")?.addEventListener("click", openUpdateModal);
  document.getElementById("btn-close-update")?.addEventListener("click", () => closeModal("modal-update"));

  document.querySelectorAll("[data-ext-url]").forEach(btn => {
    btn.addEventListener("click", () => {
      window.pywebview.api.open_external_url(btn.dataset.extUrl);
    });
  });

  document.querySelectorAll(".modal-backdrop").forEach(bd => {
    bd.addEventListener("click", (e) => {
      if (e.target === bd) bd.classList.remove("open");
    });
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openModal("modal-spotlight");
      setTimeout(() => document.getElementById("spotlight-input")?.focus(), 40);
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
      e.preventDefault();
      navigateTo("deals");
      setTimeout(() => document.getElementById("deals-smart-query")?.focus(), 60);
    } else if (e.key === "F5") {
      e.preventDefault();
      if (state.activeTab === "deals" && window.DealsView) {
        window.DealsView.scanOrSearch();
      } else if (["watchlist", "atl", "library", "cards"].includes(state.activeTab) && window.AccountView) {
        window.AccountView.refreshActive(state.activeTab);
      } else {
        window.pywebview.api.get_command_center_data().then(renderCommandCenter);
      }
    } else if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop.open").forEach(m => m.classList.remove("open"));
      document.getElementById("deal-context-menu")?.classList.remove("open");
    }
  });

  document.addEventListener("click", (e) => {
    const menu = document.getElementById("deal-context-menu");
    if (menu && menu.classList.contains("open") && !menu.contains(e.target)) {
      menu.classList.remove("open");
    }
  });
}

window.SteamScopeUI = {
  formatPrice,
  escapeHtml,
  showToast,
  renderCommandCenter,
  openCartModal,
  openModal,
  closeModal,
  navigateTo,
  getState: () => state,
};

const TAB_ORDER = [
  "command_center", "deals", "radar", "atl", "watchlist",
  "library", "cards", "dashboard", "versus", "roulette", "events", "settings"
];

window.SteamScopeGamepad = {
  onConnection: (connected) => {
    const chip = document.getElementById("hud-gamepad-chip");
    if (chip) chip.style.display = connected ? "inline-flex" : "none";
    showToast(connected ? "🎮 Mando XInput detectado y activo" : "🎮 Mando desconectado");
  },
  onAction: (action) => {
    if (action === "spotlight") {
      openModal("modal-spotlight");
      setTimeout(() => document.getElementById("spotlight-input")?.focus(), 40);
    } else if (action === "roulette") {
      navigateTo("roulette");
    } else if (action === "radar") {
      navigateTo("radar");
    } else if (action === "tab_prev" || action === "tab_next") {
      const idx = Math.max(0, TAB_ORDER.indexOf(state.activeTab));
      const delta = action === "tab_next" ? 1 : -1;
      const next = TAB_ORDER[(idx + delta + TAB_ORDER.length) % TAB_ORDER.length];
      navigateTo(next);
    }
  },
};

async function initApp() {
  if (!window.pywebview || !window.pywebview.api) return;
  const boot = await window.pywebview.api.get_bootstrap();
  state.bootstrap = boot;
  state.moneda = boot.moneda || "USD";

  const verLbl = document.getElementById("app-ver-lbl");
  if (verLbl) verLbl.textContent = `v${boot.version}`;

  if (boot.sidebar_collapsed) {
    document.getElementById("app-shell")?.classList.add("collapsed");
  }

  const skinSelect = document.getElementById("hud-skin-select");
  if (skinSelect) {
    skinSelect.innerHTML = (boot.skins_meta || []).map(s =>
      `<option value="${escapeHtml(s.id)}">🎨 ${escapeHtml(s.label)}</option>`
    ).join("");
  }

  applySkinPalette(boot.skin_id, boot.skins?.[boot.skin_id]);
  renderCommandCenter(boot.command_center);
}

document.addEventListener("DOMContentLoaded", () => {
  wireEvents();
  if (window.pywebview && window.pywebview.api) {
    initApp();
  } else {
    window.addEventListener("pywebviewready", initApp);
  }
});
