/* =====================================================================
   SteamScope 3.0 NEXT — Radar Epic/GOG, Ruleta, Dashboard, Eventos & Ajustes
   ===================================================================== */

(function () {
  const ui = () => window.SteamScopeUI;

  const toolsState = {
    rouletteMode: "deals",
    lastRouletteAppId: "",
    rouletteSpinning: false,
  };

  /* ==================== 1. RADAR MULTI-TIENDA (EPIC & GOG) ==================== */
  async function mountRadar(container) {
    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">RADAR MULTI-TIENDA <span>EPIC &amp; GOG</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Juegos 100% gratis semanales en Epic Games Store y promociones DRM-Free en GOG.</div>
        </div>
        <button type="button" class="btn-primary-accent" id="btn-radar-refresh">🔄 Actualizar Radar</button>
      </div>
      <div id="radar-gog-bar" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px"></div>
      <div id="radar-content-area"><div class="skeleton-list"><div class="skeleton-card"></div><div class="skeleton-card"></div></div></div>
    `;

    document.getElementById("btn-radar-refresh")?.addEventListener("click", () => _loadRadar(true));
    await _loadRadar(false);
  }

  async function _loadRadar(forceRefresh) {
    const res = await window.pywebview.api.get_free_games_radar(forceRefresh);
    const esc = ui().escapeHtml;
    const gogBar = document.getElementById("radar-gog-bar");
    if (gogBar && res?.gog_links) {
      gogBar.innerHTML = res.gog_links.map(g => `
        <button type="button" class="btn-ghost btn-gog-link" data-url="${esc(g.url)}">${esc(g.label)} ↗</button>
      `).join("");
      gogBar.querySelectorAll(".btn-gog-link").forEach(btn => {
        btn.addEventListener("click", () => window.pywebview.api.open_external_url(btn.dataset.url));
      });
    }

    const area = document.getElementById("radar-content-area");
    if (!area) return;
    const activos = res?.activos || [];
    const proximos = res?.proximos || [];
    const all = [...activos, ...proximos];

    if (!all.length) {
      area.innerHTML = `<div class="glass-card empty-state">No se pudieron cargar promociones gratuitas en este momento.</div>`;
      return;
    }

    area.innerHTML = `
      <div class="radar-grid">
        ${all.map(g => `
          <article class="radar-card ${g.es_activo ? "active-promo" : ""}">
            ${g.imagen_url ? `<img class="radar-cover" src="${esc(g.imagen_url)}" alt="${esc(g.titulo)}" loading="lazy" />` : ""}
            <div class="radar-body">
              <div class="deal-badges-row">
                <span class="d-badge ${g.es_activo ? "free" : "atl"}">${esc(g.estado_texto)}</span>
                ${g.precio_original_usd > 0 ? `<span class="d-badge">Antes $${Number(g.precio_original_usd).toFixed(2)} USD</span>` : ""}
              </div>
              <strong style="font-size:16px">${esc(g.titulo)}</strong>
              <p style="font-size:12px;color:var(--subtext);line-height:1.45">${esc(g.descripcion)}</p>
              <div style="margin-top:auto;display:flex;justify-content:space-between;align-items:center;gap:8px;padding-top:8px">
                <span style="font-size:11px;color:var(--subtext)">${g.fecha_fin ? `Hasta: ${esc(g.fecha_fin)}` : "Epic Games Store"}</span>
                <button type="button" class="btn-primary-accent btn-claim-epic" style="height:32px;padding:0 14px" data-url="${esc(g.url_tienda)}">
                  ${g.es_activo ? "🎁 Reclamar Gratis ↗" : "👀 Ver en Epic ↗"}
                </button>
              </div>
            </div>
          </article>
        `).join("")}
      </div>
    `;

    area.querySelectorAll(".btn-claim-epic").forEach(btn => {
      btn.addEventListener("click", () => window.pywebview.api.open_external_url(btn.dataset.url));
    });
  }

  /* ==================== 2. RULETA LOOT BOX (60 FPS SPIN-IN-PLACE) ==================== */
  function mountRoulette(container) {
    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">RULETA <span>LOOT BOX</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Giro continuo Spin-In-Place a 60 FPS para descubrir ofertas o elegir qué jugar de tu backlog.</div>
        </div>
        <div class="segmented-control" id="roulette-mode-seg">
          <button type="button" class="seg-btn ${toolsState.rouletteMode === "deals" ? "active" : ""}" data-rmode="deals">🔥 Ofertas Steam</button>
          <button type="button" class="seg-btn ${toolsState.rouletteMode === "backlog" ? "active" : ""}" data-rmode="backlog">🎮 Mi Backlog</button>
        </div>
      </div>

      <div class="glass-card roulette-stage">
        <div class="roulette-reel" id="roulette-reel">🎰 Tocá "Girar Ruleta" para sortear</div>
        <button type="button" class="btn-primary-accent" id="btn-spin-roulette" style="height:42px;padding:0 26px;font-size:14px">
          🎲 Girar Ruleta
        </button>
        <div id="roulette-result-slot" style="width:100%;max-width:720px"></div>
      </div>
    `;

    document.querySelectorAll("#roulette-mode-seg .seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        toolsState.rouletteMode = btn.dataset.rmode;
        document.querySelectorAll("#roulette-mode-seg .seg-btn").forEach(b => b.classList.toggle("active", b === btn));
      });
    });

    document.getElementById("btn-spin-roulette")?.addEventListener("click", _runSpin);
  }

  async function _runSpin() {
    if (toolsState.rouletteSpinning) return;
    toolsState.rouletteSpinning = true;
    const reel = document.getElementById("roulette-reel");
    const slot = document.getElementById("roulette-result-slot");
    if (slot) slot.innerHTML = "";
    if (reel) {
      reel.classList.add("spinning");
      reel.textContent = "⏳ Preparando sorteo...";
    }

    const res = await window.pywebview.api.spin_roulette(toolsState.rouletteMode, toolsState.lastRouletteAppId);
    if (!res?.ok || !res.item) {
      toolsState.rouletteSpinning = false;
      reel?.classList.remove("spinning");
      if (reel) reel.textContent = `⚠️ ${res?.error || "Sin candidatos disponibles"}`;
      return;
    }

    const pool = (res.pool_titles && res.pool_titles.length) ? res.pool_titles : [res.item.titulo];
    let step = 0;
    const totalSteps = 22;

    const tick = () => {
      if (!reel || !document.body.contains(reel)) {
        toolsState.rouletteSpinning = false;
        return;
      }
      if (step < totalSteps) {
        reel.textContent = `🎲 ${pool[step % pool.length]}`;
        step += 1;
        const delay = 35 + Math.floor((step / totalSteps) * 140);
        setTimeout(tick, delay);
      } else {
        reel.classList.remove("spinning");
        reel.textContent = `🎉 ${res.item.titulo}`;
        toolsState.lastRouletteAppId = String(res.item.appid || "");
        toolsState.rouletteSpinning = false;
        _renderRouletteResult(res.mode, res.item);
      }
    };
    tick();
  }

  function _renderRouletteResult(mode, item) {
    const slot = document.getElementById("roulette-result-slot");
    if (!slot) return;
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    const isDeal = mode === "deals";

    slot.innerHTML = `
      <div class="deal-card-item ${item.es_atl ? "is-atl" : ""}" style="margin-top:6px">
        <img class="deal-cover" src="${esc(item.header_url || item.thumb_url)}" alt="${esc(item.titulo)}" onerror="this.src='${esc(item.thumb_url || "")}'" />
        <div class="deal-body">
          <div class="deal-title">${esc(item.titulo)}</div>
          <div class="deal-sub">
            ${isDeal ? `${esc(fmt(item.precio_oferta_usd))} · -${Number(item.descuento || 0)}% OFF` : `⏱️ ${Number(item.horas || 0)} hs jugadas en tu biblioteca`}
          </div>
        </div>
        <div class="deal-actions">
          <button type="button" class="btn-primary-accent" id="btn-rl-ficha" style="height:32px;padding:0 12px">🖥️ Ficha</button>
          ${isDeal ? `<button type="button" class="btn-ghost" id="btn-rl-cart">🛒 Changuito</button>` : ""}
        </div>
      </div>
    `;

    document.getElementById("btn-rl-ficha")?.addEventListener("click", () => {
      if (window.FichaView) window.FichaView.openFicha(item.appid, item);
    });
    document.getElementById("btn-rl-cart")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.toggle_cart_item(item);
      if (r?.ok) {
        ui().renderCommandCenter(r.command_center);
        ui().showToast(r.in_cart ? `🛒 "${item.titulo}" sumado al changuito` : `🛒 "${item.titulo}" quitado`);
      }
    });
  }

  /* ==================== 3. DASHBOARD VISUAL GPU ==================== */
  function _renderBars(rows, unit = "") {
    const esc = ui().escapeHtml;
    if (!rows || !rows.length) return `<div class="empty-state">Sin datos cargados todavía.</div>`;
    const maxVal = Math.max(...rows.map(r => Number(r.count ?? r.horas ?? 0)), 1);
    return rows.map(r => {
      const val = Number(r.count ?? r.horas ?? 0);
      const label = r.label || r.titulo || "";
      const pct = Math.max(4, Math.round((val / maxVal) * 100));
      return `
        <div class="bar-row">
          <div class="bar-row-head">
            <span>${esc(label)}</span>
            <strong>${val}${esc(unit)}</strong>
          </div>
          <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        </div>
      `;
    }).join("");
  }

  async function mountDashboard(container) {
    const res = await window.pywebview.api.get_dashboard_stats();
    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">DASHBOARD <span>VISUAL GPU</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Métricas en vivo sobre ${res?.deals_total || 0} ofertas escaneadas y ${res?.library_total || 0} juegos en tu biblioteca.</div>
        </div>
        <div style="display:flex;gap:8px">
          <button type="button" class="btn-ghost" id="btn-dash-csv-wl">📊 Exportar Watchlist CSV</button>
          <button type="button" class="btn-ghost" id="btn-dash-csv-lib">📊 Exportar Biblioteca CSV</button>
        </div>
      </div>

      <div class="dashboard-grid">
        <div class="glass-card chart-card">
          <div class="ficha-section-title">🏷️ Distribución de Descuentos</div>
          ${_renderBars(res?.discount_buckets || [])}
        </div>
        <div class="glass-card chart-card">
          <div class="ficha-section-title">🎮 Top Géneros / Tags (Ofertas)</div>
          ${_renderBars(res?.top_genres || [])}
        </div>
        <div class="glass-card chart-card">
          <div class="ficha-section-title">📚 Estado de tu Backlog</div>
          ${_renderBars(res?.backlog_breakdown || [])}
        </div>
        <div class="glass-card chart-card">
          <div class="ficha-section-title">⏱️ Top Juegos Más Jugados</div>
          ${_renderBars(res?.top_played || [], " hs")}
        </div>
      </div>
    `;

    document.getElementById("btn-dash-csv-wl")?.addEventListener("click", () => _triggerCsv("watchlist"));
    document.getElementById("btn-dash-csv-lib")?.addEventListener("click", () => _triggerCsv("library"));
  }

  async function _triggerCsv(scope) {
    const r = await window.pywebview.api.export_csv(scope, null);
    if (r?.cancelled) return;
    ui().showToast(r?.ok ? `✅ CSV exportado (${r.rows} filas)` : `⚠️ ${r?.error || "Error al exportar"}`);
  }

  /* ==================== 4. EVENTOS STEAM & CALCULADORA ARS ==================== */
  async function mountEvents(container) {
    const res = await window.pywebview.api.get_steam_events();
    const esc = ui().escapeHtml;
    const fx = res?.fx || { dolar_referencia: 1000, dolar_cripto_ref: 1150, impuestos_pct: 60 };

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">EVENTOS STEAM <span>&amp; CALCULADORA ARS</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Calendario oficial de Valve y simulador en tiempo real Tarjeta vs. Cripto / Web.</div>
        </div>
        <button type="button" class="btn-primary-accent" id="btn-ev-fx">💵 Actualizar Dólar en Vivo</button>
      </div>

      <div class="events-grid">
        ${(res?.events || []).map(ev => `
          <div class="glass-card panel-card">
            <div class="panel-header">
              <strong>${esc(ev.name)}</strong>
              <span class="d-badge ${ev.status === "active" ? "free" : (ev.status === "upcoming" ? "atl" : "")}">
                ${ev.status === "active" ? "🔥 ACTIVO AHORA" : (ev.status === "upcoming" ? `⏳ En ${ev.days_left} días` : "Finalizado")}
              </span>
            </div>
            <div style="font-size:12px;color:var(--subtext)">📅 ${esc(ev.start_display)} al ${esc(ev.end_display)} · Tipo: ${esc(ev.type)}</div>
          </div>
        `).join("")}
      </div>

      <div class="glass-card panel-card">
        <div class="ficha-section-title">🧮 Calculadora Rápida USD → ARS</div>
        <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center">
          <input type="number" class="t-input" id="calc-usd-input" value="10" min="0" step="0.5" style="width:140px" />
          <span style="font-size:12px;color:var(--subtext)">USD</span>
          <div id="calc-ars-output" style="display:flex;gap:12px;flex-wrap:wrap;margin-left:auto"></div>
        </div>
      </div>
    `;

    const updateCalc = () => {
      const usd = Number(document.getElementById("calc-usd-input")?.value || 0);
      const tarjeta = Math.round(usd * fx.dolar_referencia * (1 + fx.impuestos_pct / 100));
      const cripto = Math.round(usd * fx.dolar_cripto_ref);
      const out = document.getElementById("calc-ars-output");
      if (out) {
        out.innerHTML = `
          <span class="cc-price-tag">💳 Tarjeta (+${fx.impuestos_pct}%): $${tarjeta.toLocaleString("es-AR")} ARS</span>
          <span class="cc-price-tag" style="color:var(--emerald)">🪙 Cripto / Steam Web: $${cripto.toLocaleString("es-AR")} ARS</span>
        `;
      }
    };
    updateCalc();
    document.getElementById("calc-usd-input")?.addEventListener("input", updateCalc);

    document.getElementById("btn-ev-fx")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.refresh_live_fx();
      if (!r?.ok) {
        ui().showToast(`⚠️ ${r?.error || "Sin conexión"}`);
        return;
      }
      fx.dolar_referencia = r.dolar_referencia;
      fx.dolar_cripto_ref = r.dolar_cripto_ref;
      ui().renderCommandCenter(r.command_center);
      updateCalc();
      ui().showToast(`💵 Dólar actualizado: Oficial $${r.dolar_referencia} / Cripto $${r.dolar_cripto_ref}`);
    });
  }

  /* ==================== 5. AJUSTES, BLACKLIST & BACKUP ==================== */
  async function mountSettings(container) {
    const res = await window.pywebview.api.get_settings();
    const blRes = await window.pywebview.api.get_blacklist();
    const s = res?.settings || {};
    const esc = ui().escapeHtml;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">AJUSTES <span>&amp; MANTENIMIENTO</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Configuración persistente compartida con SteamScope v2.0.1.</div>
        </div>
        <button type="button" class="btn-primary-accent" id="btn-set-save">💾 Guardar Configuración</button>
      </div>

      <div class="glass-card panel-card" style="margin-bottom:14px">
        <div class="settings-grid">
          <div class="filter-field"><label>Steam ID / Vanity URL</label><input type="text" class="t-input" id="set-steam-id" value="${esc(s.steam_id)}" /></div>
          <div class="filter-field"><label>Steam API Key (Opcional)</label><input type="password" class="t-input" id="set-api-key" value="${esc(s.steam_api_key)}" /></div>
          <div class="filter-field"><label>Dólar Oficial Ref (ARS)</label><input type="number" class="t-input" id="set-dolar" value="${s.dolar_referencia}" step="1" /></div>
          <div class="filter-field"><label>Dólar Cripto Ref (ARS)</label><input type="number" class="t-input" id="set-cripto" value="${s.dolar_cripto_ref}" step="1" /></div>
          <div class="filter-field"><label>Impuestos Tarjeta (%)</label><input type="number" class="t-input" id="set-imp" value="${s.impuestos_pct}" step="1" /></div>
          <div class="filter-field"><label>Umbral Alerta Descuento (%)</label><input type="number" class="t-input" id="set-umbral" value="${s.umbral_alerta_pct}" min="1" max="100" /></div>
          <div class="filter-field"><label>Discord Webhook URL</label><input type="text" class="t-input" id="set-webhook" value="${esc(s.discord_webhook)}" placeholder="https://discord.com/api/webhooks/..." /></div>
          <div class="filter-field">
            <label>Al Minimizar</label>
            <select class="t-select" id="set-minimizar" style="border-radius:8px">
              ${["Preguntar", "Barra", "Bandeja"].map(op => `<option value="${op}" ${s.minimizar_a === op ? "selected" : ""}>${op}</option>`).join("")}
            </select>
          </div>
          <div class="filter-field"><label>Intervalo Centinela ATL (hs)</label><input type="number" class="t-input" id="set-intervalo" value="${s.watchdog_intervalo_hs}" min="1" max="72" /></div>
          <div style="display:flex;flex-direction:column;gap:6px;justify-content:flex-end">
            <label class="settings-check"><input type="checkbox" id="set-sfx" ${s.sfx_enabled ? "checked" : ""} /> 🔊 Sonidos SFX activados</label>
            <label class="settings-check"><input type="checkbox" id="set-watchdog" ${s.watchdog_activado ? "checked" : ""} /> 🔔 Centinela ATL automático</label>
          </div>
        </div>
      </div>

      <div class="glass-card panel-card" style="margin-bottom:14px">
        <div class="ficha-section-title">🧰 Mantenimiento, Backup y Exportación</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          <button type="button" class="btn-ghost" id="btn-set-fx-live">💵 Actualizar Dólar en Vivo</button>
          <button type="button" class="btn-ghost" id="btn-set-vacuum">⚡ Optimizar SQLite (VACUUM)</button>
          <button type="button" class="btn-ghost" id="btn-set-cache">🧹 Limpiar Caché de Imágenes</button>
          <button type="button" class="btn-ghost" id="btn-set-csv-wl">📊 Exportar Watchlist CSV</button>
          <button type="button" class="btn-ghost" id="btn-set-backup">💾 Backup Portátil (.zip)</button>
        </div>
      </div>

      <div class="glass-card panel-card">
        <div class="panel-header">
          <span class="ficha-section-title">🚫 Gestor de Blacklist (${(blRes?.items || []).length})</span>
          <button type="button" class="btn-danger" id="btn-bl-clear" style="height:28px">Vaciar Blacklist</button>
        </div>
        <div class="cc-list" id="set-blacklist-box" style="max-height:240px"></div>
      </div>
    `;

    _renderBlacklist(blRes?.items || []);

    document.getElementById("btn-set-save")?.addEventListener("click", async () => {
      const payload = {
        steam_id: document.getElementById("set-steam-id")?.value || "",
        steam_api_key: document.getElementById("set-api-key")?.value || "",
        dolar_referencia: Number(document.getElementById("set-dolar")?.value || 1000),
        dolar_cripto_ref: Number(document.getElementById("set-cripto")?.value || 1150),
        impuestos_pct: Number(document.getElementById("set-imp")?.value || 60),
        umbral_alerta_pct: Number(document.getElementById("set-umbral")?.value || 50),
        discord_webhook: document.getElementById("set-webhook")?.value || "",
        minimizar_a: document.getElementById("set-minimizar")?.value || "Preguntar",
        watchdog_intervalo_hs: Number(document.getElementById("set-intervalo")?.value || 6),
        sfx_enabled: Boolean(document.getElementById("set-sfx")?.checked),
        watchdog_activado: Boolean(document.getElementById("set-watchdog")?.checked),
      };
      const r = await window.pywebview.api.save_settings(payload);
      if (r?.ok) {
        ui().renderCommandCenter(r.command_center);
        ui().showToast("✅ Configuración guardada correctamente");
      } else {
        ui().showToast(`⚠️ ${r?.error || "Error al guardar"}`);
      }
    });

    document.getElementById("btn-set-fx-live")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.refresh_live_fx();
      if (r?.ok) {
        document.getElementById("set-dolar").value = r.dolar_referencia;
        document.getElementById("set-cripto").value = r.dolar_cripto_ref;
        ui().renderCommandCenter(r.command_center);
        ui().showToast("💵 Cotizaciones actualizadas");
      } else {
        ui().showToast(`⚠️ ${r?.error || "No se pudo actualizar"}`);
      }
    });

    document.getElementById("btn-set-vacuum")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.optimize_database();
      ui().showToast(r?.ok ? "⚡ Base SQLite compactada y optimizada" : "⚠️ No se pudo optimizar");
    });

    document.getElementById("btn-set-cache")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.clear_image_cache();
      ui().showToast(`🧹 ${r?.deleted || 0} archivos eliminados (${r?.freed_mb || 0} MB liberados)`);
    });

    document.getElementById("btn-set-csv-wl")?.addEventListener("click", () => _triggerCsv("watchlist"));

    document.getElementById("btn-set-backup")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.export_backup_zip(null);
      if (r?.cancelled) return;
      ui().showToast(r?.ok ? "💾 Backup .zip exportado" : `⚠️ ${r?.error || "Error al exportar"}`);
    });

    document.getElementById("btn-bl-clear")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.clear_blacklist();
      if (r?.ok) {
        _renderBlacklist([]);
        ui().showToast("🧹 Blacklist vaciada");
      }
    });
  }

  function _renderBlacklist(items) {
    const box = document.getElementById("set-blacklist-box");
    if (!box) return;
    const esc = ui().escapeHtml;
    if (!items.length) {
      box.innerHTML = `<div class="empty-state">No tenés juegos ignorados en la Blacklist.</div>`;
      return;
    }
    box.innerHTML = items.map(it => `
      <div class="cc-row">
        <div class="cc-row-main">
          <div class="cc-row-title">${esc(it.titulo)}</div>
          <div class="cc-row-sub">AppID ${esc(it.appid)}</div>
        </div>
        <button type="button" class="btn-ghost btn-bl-restore" data-appid="${esc(it.appid)}" style="height:28px">Restaurar</button>
      </div>
    `).join("");

    box.querySelectorAll(".btn-bl-restore").forEach(btn => {
      btn.addEventListener("click", async () => {
        const r = await window.pywebview.api.remove_from_blacklist(btn.dataset.appid);
        if (r?.ok) {
          _renderBlacklist(r.items || []);
          ui().showToast("♻️ Juego restaurado de la Blacklist");
        }
      });
    });
  }

  window.ToolsView = {
    mountRadar,
    mountRoulette,
    mountDashboard,
    mountEvents,
    mountSettings,
  };
})();
