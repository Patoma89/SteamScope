/* =====================================================================
   SteamScope 3.0 NEXT — Radar Epic/GOG, Ruleta, Dashboard, Eventos & Ajustes
   ===================================================================== */

(function () {
  const ui = () => window.SteamScopeUI;

  const toolsState = {
    rouletteMode: "deals",
    rouletteCount: 3,
    lastRouletteAppId: "",
    rouletteSpinning: false,
    radarFilter: "all",
    lastRadarData: null,
  };

  /* ==================== 1. RADAR MULTI-TIENDA (EPIC & GOG) ==================== */
  async function mountRadar(container) {
    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">RADAR MULTI-TIENDA <span>EPIC &amp; GOG</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Juegos 100% gratis semanales en Epic Games Store + catálogo gratuito y ofertas DRM-Free en GOG.</div>
        </div>
        <button type="button" class="btn-primary-accent" id="btn-radar-refresh">🔄 Actualizar Radar</button>
      </div>
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin-bottom:14px">
        <div class="segmented-control" id="radar-filter-seg">
          <button type="button" class="seg-btn ${toolsState.radarFilter === "all" ? "active" : ""}" data-rfilter="all">🌐 Todos</button>
          <button type="button" class="seg-btn ${toolsState.radarFilter === "epic" ? "active" : ""}" data-rfilter="epic">🎁 Epic Gratis</button>
          <button type="button" class="seg-btn ${toolsState.radarFilter === "gog_free" ? "active" : ""}" data-rfilter="gog_free">🎁 GOG Gratis</button>
          <button type="button" class="seg-btn ${toolsState.radarFilter === "gog_deals" ? "active" : ""}" data-rfilter="gog_deals">🔥 Ofertas GOG</button>
        </div>
        <div id="radar-gog-bar" style="display:flex;flex-wrap:wrap;gap:8px"></div>
      </div>
      <div id="radar-content-area"><div class="skeleton-list"><div class="skeleton-card"></div><div class="skeleton-card"></div></div></div>
    `;

    document.querySelectorAll("#radar-filter-seg .seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        toolsState.radarFilter = btn.dataset.rfilter;
        document.querySelectorAll("#radar-filter-seg .seg-btn").forEach(b => b.classList.toggle("active", b === btn));
        if (toolsState.lastRadarData) _renderRadarCards(toolsState.lastRadarData);
      });
    });

    document.getElementById("btn-radar-refresh")?.addEventListener("click", () => _loadRadar(true));
    await _loadRadar(false);
  }

  async function _loadRadar(forceRefresh) {
    const res = await window.pywebview.api.get_free_games_radar(forceRefresh);
    toolsState.lastRadarData = res;
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
    _renderRadarCards(res);
  }

  function _renderRadarCards(res) {
    const area = document.getElementById("radar-content-area");
    if (!area) return;
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    const filter = toolsState.radarFilter || "all";

    const epicItems = [...(res?.activos || []), ...(res?.proximos || [])];
    const gogFree = res?.gog_gratis || [];
    const gogDeals = res?.gog_ofertas || [];

    const showEpic = filter === "all" || filter === "epic";
    const showGogFree = filter === "all" || filter === "gog_free";
    const showGogDeals = filter === "all" || filter === "gog_deals";

    const chunks = [];

    if (showEpic && epicItems.length) {
      chunks.push(`
        <div class="ficha-section-title" style="margin:4px 0 10px">🎁 Epic Games Store (${epicItems.length})</div>
        <div class="radar-grid" style="margin-bottom:18px">
          ${epicItems.map(g => `
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
                  <button type="button" class="btn-primary-accent btn-claim-store" style="height:32px;padding:0 14px" data-url="${esc(g.url_tienda)}">
                    ${g.es_activo ? "🎁 Reclamar Gratis ↗" : "👀 Ver en Epic ↗"}
                  </button>
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      `);
    }

    if (showGogFree && gogFree.length) {
      chunks.push(`
        <div class="ficha-section-title" style="margin:4px 0 10px">🎁 Juegos Gratis en GOG DRM-Free (${gogFree.length})</div>
        <div class="radar-grid" style="margin-bottom:18px">
          ${gogFree.map(g => `
            <article class="radar-card active-promo">
              ${g.imagen_url ? `<img class="radar-cover" src="${esc(g.imagen_url)}" alt="${esc(g.titulo)}" loading="lazy" />` : ""}
              <div class="radar-body">
                <div class="deal-badges-row">
                  <span class="d-badge free">${esc(g.estado_texto)}</span>
                  <span class="d-badge">DRM-Free</span>
                </div>
                <strong style="font-size:16px">${esc(g.titulo)}</strong>
                <div style="margin-top:auto;display:flex;justify-content:space-between;align-items:center;gap:8px;padding-top:8px">
                  <span style="font-size:11px;color:var(--subtext)">GOG.com</span>
                  <button type="button" class="btn-primary-accent btn-claim-store" style="height:32px;padding:0 14px" data-url="${esc(g.url_tienda)}">
                    🎁 Ver Gratis en GOG ↗
                  </button>
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      `);
    }

    if (showGogDeals && gogDeals.length) {
      chunks.push(`
        <div class="ficha-section-title" style="margin:4px 0 10px">🔥 Ofertas Destacadas en GOG (${gogDeals.length})</div>
        <div class="radar-grid">
          ${gogDeals.map(g => `
            <article class="radar-card">
              ${g.imagen_url ? `<img class="radar-cover" src="${esc(g.imagen_url)}" alt="${esc(g.titulo)}" loading="lazy" />` : ""}
              <div class="radar-body">
                <div class="deal-badges-row">
                  <span class="d-badge atl">-${Number(g.descuento || 0)}% OFF</span>
                  <span class="d-badge">DRM-Free</span>
                </div>
                <strong style="font-size:16px">${esc(g.titulo)}</strong>
                <div style="margin-top:auto;display:flex;justify-content:space-between;align-items:center;gap:8px;padding-top:8px">
                  <div>
                    <strong style="font-size:14px;color:var(--accent)">${esc(fmt(g.precio_oferta_usd))}</strong>
                    ${g.precio_original_usd > g.precio_oferta_usd ? `<span style="font-size:11px;color:var(--subtext);text-decoration:line-through;margin-left:6px">${esc(fmt(g.precio_original_usd))}</span>` : ""}
                  </div>
                  <button type="button" class="btn-ghost btn-claim-store" style="height:32px;padding:0 14px" data-url="${esc(g.url_tienda)}">
                    🛒 Ver en GOG ↗
                  </button>
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      `);
    }

    if (!chunks.length) {
      area.innerHTML = `<div class="glass-card empty-state">No se pudieron cargar promociones en este filtro en este momento.</div>`;
      return;
    }

    area.innerHTML = chunks.join("");
    area.querySelectorAll(".btn-claim-store").forEach(btn => {
      btn.addEventListener("click", () => window.pywebview.api.open_external_url(btn.dataset.url));
    });
  }

  /* ==================== 2. RULETA LOOT BOX (60 FPS SPIN-IN-PLACE) ==================== */
  function _updateRoulettePrompt() {
    const reel = document.getElementById("roulette-reel");
    const slot = document.getElementById("roulette-result-slot");
    const spinBtn = document.getElementById("btn-spin-roulette");
    if (!reel || toolsState.rouletteSpinning) return;

    const cc = ui().getState().cc || {};
    const libTotal = Number(cc.backlog?.total || 0);
    const unplayed = Number(cc.backlog?.sin_jugar || 0);

    if (toolsState.rouletteMode === "backlog") {
      if (libTotal <= 0) {
        reel.textContent = "📚 Tu biblioteca local está vacía. Sincronizala en Mi Biblioteca para sortear tu backlog.";
        if (spinBtn) spinBtn.disabled = false;
        if (slot) {
          slot.innerHTML = `
            <div style="display:flex;justify-content:center;margin-top:8px">
              <button type="button" class="btn-ghost" id="btn-rl-go-lib">📚 Ir a sincronizar Mi Biblioteca →</button>
            </div>
          `;
          document.getElementById("btn-rl-go-lib")?.addEventListener("click", () => ui().navigateTo("library"));
        }
        return;
      }
      reel.textContent = `🎮 Backlog listo: ${libTotal} juegos (${unplayed} sin estrenar) · Sorteando ${toolsState.rouletteCount}`;
      if (slot) slot.innerHTML = "";
    } else {
      reel.textContent = `🔥 Ofertas listas · Tocá "Girar Ruleta" para sortear ${toolsState.rouletteCount} juego${toolsState.rouletteCount > 1 ? "s" : ""}`;
      if (slot) slot.innerHTML = "";
    }
  }

  function mountRoulette(container) {
    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">RULETA <span>LOOT BOX</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Giro continuo Spin-In-Place a 60 FPS para descubrir ofertas o elegir qué jugar de tu backlog.</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <div class="segmented-control" id="roulette-count-seg" title="Cantidad de juegos a sortear">
            ${[1, 3, 5].map(n => `<button type="button" class="seg-btn ${toolsState.rouletteCount === n ? "active" : ""}" data-rcount="${n}">${n} ${n === 1 ? "juego" : "juegos"}</button>`).join("")}
          </div>
          <div class="segmented-control" id="roulette-mode-seg">
            <button type="button" class="seg-btn ${toolsState.rouletteMode === "deals" ? "active" : ""}" data-rmode="deals">🔥 Ofertas Steam</button>
            <button type="button" class="seg-btn ${toolsState.rouletteMode === "backlog" ? "active" : ""}" data-rmode="backlog">🎮 Mi Backlog</button>
          </div>
        </div>
      </div>

      <div class="glass-card roulette-stage">
        <div class="roulette-reel" id="roulette-reel">🎰 Tocá "Girar Ruleta" para sortear</div>
        <button type="button" class="btn-primary-accent" id="btn-spin-roulette" style="height:42px;padding:0 26px;font-size:14px">
          🎲 Girar Ruleta
        </button>
        <div id="roulette-result-slot" style="width:100%;max-width:780px"></div>
      </div>
    `;

    _updateRoulettePrompt();

    document.querySelectorAll("#roulette-count-seg .seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        toolsState.rouletteCount = Number(btn.dataset.rcount || 1);
        document.querySelectorAll("#roulette-count-seg .seg-btn").forEach(b => b.classList.toggle("active", b === btn));
        _updateRoulettePrompt();
      });
    });

    document.querySelectorAll("#roulette-mode-seg .seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        toolsState.rouletteMode = btn.dataset.rmode;
        document.querySelectorAll("#roulette-mode-seg .seg-btn").forEach(b => b.classList.toggle("active", b === btn));
        _updateRoulettePrompt();
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

    const res = await window.pywebview.api.spin_roulette(
      toolsState.rouletteMode,
      toolsState.lastRouletteAppId,
      toolsState.rouletteCount
    );
    const items = (res?.items && res.items.length) ? res.items : (res?.item ? [res.item] : []);
    if (!res?.ok || !items.length) {
      toolsState.rouletteSpinning = false;
      reel?.classList.remove("spinning");
      if (reel) reel.textContent = `⚠️ ${res?.error || "Sin candidatos disponibles"}`;
      if (toolsState.rouletteMode === "backlog" && slot) {
        slot.innerHTML = `
          <div style="display:flex;justify-content:center;margin-top:8px">
            <button type="button" class="btn-ghost" id="btn-rl-empty-lib">📚 Sincronizar Mi Biblioteca →</button>
          </div>
        `;
        document.getElementById("btn-rl-empty-lib")?.addEventListener("click", () => ui().navigateTo("library"));
      }
      return;
    }

    const pool = (res.pool_titles && res.pool_titles.length) ? res.pool_titles : [items[0].titulo];
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
        reel.textContent = items.length > 1
          ? `🎉 ¡${items.length} juegos sorteados! (${items[0].titulo} y más)`
          : `🎉 ${items[0].titulo}`;
        toolsState.lastRouletteAppId = String(items[0].appid || "");
        toolsState.rouletteSpinning = false;
        _renderRouletteResult(res.mode, items);
      }
    };
    tick();
  }

  function _renderRouletteResult(mode, items) {
    const slot = document.getElementById("roulette-result-slot");
    if (!slot) return;
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    const isDeal = mode === "deals";

    slot.innerHTML = `
      <div class="roulette-results-grid">
        ${items.map((item, idx) => `
          <div class="deal-card-item ${item.es_atl ? "is-atl" : ""}">
            <img class="deal-cover" src="${esc(ui().steamCoverUrl(item.appid, item.cover_url || item.header_url))}" alt="${esc(item.titulo)}" onerror="window.SteamScopeUI.handleSteamImgError(this, '${esc(item.appid)}', this.alt)" />
            <div class="deal-body">
              <div class="deal-title">${esc(item.titulo)}</div>
              <div class="deal-sub">
                ${isDeal ? `${esc(fmt(item.precio_oferta_usd))} · -${Number(item.descuento || 0)}% OFF` : `⏱️ ${Number(item.horas || 0)} hs jugadas en tu biblioteca`}
              </div>
            </div>
            <div class="deal-actions">
              <button type="button" class="btn-primary-accent btn-rl-ficha" data-idx="${idx}" style="height:32px;padding:0 12px">🖥️ Ficha</button>
              ${isDeal
                ? `<button type="button" class="btn-ghost btn-rl-cart" data-idx="${idx}">🛒 Changuito</button>`
                : `<button type="button" class="btn-ghost btn-rl-play" data-appid="${esc(item.appid)}">▶ Jugar</button>`}
            </div>
          </div>
        `).join("")}
      </div>
    `;

    slot.querySelectorAll(".btn-rl-ficha").forEach(btn => {
      btn.addEventListener("click", () => {
        const item = items[Number(btn.dataset.idx)];
        if (item && window.FichaView) window.FichaView.openFicha(item.appid, item);
      });
    });
    slot.querySelectorAll(".btn-rl-cart").forEach(btn => {
      btn.addEventListener("click", async () => {
        const item = items[Number(btn.dataset.idx)];
        if (!item) return;
        const r = await window.pywebview.api.toggle_cart_item(item);
        if (r?.ok) {
          ui().renderCommandCenter(r.command_center);
          ui().showToast(r.in_cart ? `🛒 "${item.titulo}" sumado al changuito` : `🛒 "${item.titulo}" quitado`);
        }
      });
    });
    slot.querySelectorAll(".btn-rl-play").forEach(btn => {
      btn.addEventListener("click", () => {
        window.pywebview.api.open_external_url(`steam://run/${btn.dataset.appid}`);
      });
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
    const sum = res?.summary || {};
    const fmt = ui().formatPrice;
    const esc = ui().escapeHtml;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">DASHBOARD <span>VISUAL GPU</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Métricas en vivo sobre ${res?.deals_total || 0} ofertas escaneadas y ${res?.library_total || 0} juegos en tu biblioteca.</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          <button type="button" class="btn-primary-accent" id="btn-dash-scan-deals">🔍 Escanear Ofertas ahora</button>
          <button type="button" class="btn-ghost" id="btn-dash-csv-wl">📊 Exportar Watchlist CSV</button>
          <button type="button" class="btn-ghost" id="btn-dash-csv-lib">📊 Exportar Biblioteca CSV</button>
        </div>
      </div>

      <div class="dash-kpi-strip">
        <div class="glass-card dash-kpi-card">
          <span>💎 Valor de Biblioteca</span>
          <strong>${esc(fmt(sum.total_value_usd || 0))}</strong>
        </div>
        <div class="glass-card dash-kpi-card">
          <span>🧊 Dinero Sin Estrenar</span>
          <strong>${esc(fmt(sum.unplayed_value_usd || 0))}</strong>
        </div>
        <div class="glass-card dash-kpi-card">
          <span>⏱️ Costo por Hora (${Number(sum.horas_totales || 0)} hs)</span>
          <strong>$${Number(sum.cost_per_hour_usd || 0).toFixed(2)} USD/h</strong>
        </div>
        <div class="glass-card dash-kpi-card">
          <span>🏷️ Descuento Promedio (Ofertas)</span>
          <strong>${Number(sum.avg_discount_pct || 0)}% OFF</strong>
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

    document.getElementById("btn-dash-scan-deals")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-dash-scan-deals");
      if (btn) { btn.disabled = true; btn.textContent = "⏳ Escaneando..."; }
      ui().showToast("🔍 Escaneando ofertas en Steam para llenar el Dashboard...");
      const scanRes = await window.pywebview.api.search_or_scan_deals({ limite: 100 });
      if (!scanRes?.ok) {
        ui().showToast(`⚠️ ${scanRes?.error || "Error al escanear ofertas"}`);
        if (btn) { btn.disabled = false; btn.textContent = "🔍 Escanear Ofertas ahora"; }
        return;
      }
      await mountDashboard(container);
      ui().showToast(`✅ Dashboard actualizado con ${scanRes.total_raw || 0} ofertas`);
    });
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
    const fx = res?.fx || { dolar_referencia: 1000, dolar_cripto_ref: 1150, dolar_mep_ref: 1150, impuestos_pct: 51 };

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
      const mepVal = Number(fx.dolar_mep_ref || 0);
      const mepBadge = mepVal > 0
        ? `<span class="cc-price-tag" style="color:var(--accent)">🏛️ MEP: $${Math.round(usd * mepVal).toLocaleString("es-AR")} ARS</span>`
        : "";
      const out = document.getElementById("calc-ars-output");
      if (out) {
        out.innerHTML = `
          <span class="cc-price-tag">💳 Tarjeta (+${fx.impuestos_pct}%): $${tarjeta.toLocaleString("es-AR")} ARS</span>
          <span class="cc-price-tag" style="color:var(--emerald)">🪙 Cripto / Steam Web: $${cripto.toLocaleString("es-AR")} ARS</span>
          ${mepBadge}
        `;
      }
    };
    updateCalc();
    document.getElementById("calc-usd-input")?.addEventListener("input", updateCalc);

    document.getElementById("btn-ev-fx")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.refresh_live_fx(true);
      if (!r?.ok) {
        ui().showToast(`⚠️ ${r?.error || "Sin conexión"}`);
        return;
      }
      fx.dolar_referencia = r.dolar_referencia;
      fx.dolar_cripto_ref = r.dolar_cripto_ref;
      fx.dolar_mep_ref = r.dolar_mep_ref;
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
    const fxMeta = ui().getState().cc?.fx || {};
    const fxSource = s.fx_source || fxMeta.fx_source || "Manual";
    const fxUpdatedAt = s.fx_updated_at || fxMeta.fx_updated_at || "";
    const fxStatusTxt = `Fuente: ${fxSource}${fxUpdatedAt ? ` · Actualizado: ${fxUpdatedAt}` : ""}`;
    const esc = ui().escapeHtml;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">AJUSTES <span>&amp; MANTENIMIENTO</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Configuración persistente en AppData y base SQLite local.</div>
        </div>
        <button type="button" class="btn-primary-accent" id="btn-set-save">💾 Guardar Configuración</button>
      </div>

      <div class="glass-card panel-card" style="margin-bottom:14px">
        <div class="settings-grid">
          <div class="filter-field"><label>Steam ID / Vanity URL</label><input type="text" class="t-input" id="set-steam-id" value="${esc(s.steam_id)}" /></div>
          <div class="filter-field"><label>Steam API Key (Opcional)</label><input type="password" class="t-input" id="set-api-key" value="${esc(s.steam_api_key)}" /></div>
          <div class="filter-field"><label>Dólar Oficial Ref (ARS)</label><input type="number" class="t-input" id="set-dolar" value="${s.dolar_referencia}" step="1" /></div>
          <div class="filter-field"><label>Dólar Cripto Ref (ARS)</label><input type="number" class="t-input" id="set-cripto" value="${s.dolar_cripto_ref}" step="1" /></div>
          <div class="filter-field">
            <label>Impuestos Tarjeta (%)</label>
            <input type="number" class="t-input" id="set-imp" value="${s.impuestos_pct}" step="1" />
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
              <button type="button" class="btn-ghost btn-imp-preset" data-imp="51" style="height:22px;padding:0 7px;font-size:10.5px">51% Estándar AR</button>
              <button type="button" class="btn-ghost btn-imp-preset" data-imp="21" style="height:22px;padding:0 7px;font-size:10.5px">21% Solo IVA</button>
              <button type="button" class="btn-ghost btn-imp-preset" data-imp="0" style="height:22px;padding:0 7px;font-size:10.5px">0% MEP/USD</button>
            </div>
          </div>
          <div class="filter-field"><label>Umbral Alerta Descuento (%)</label><input type="number" class="t-input" id="set-umbral" value="${s.umbral_alerta_pct}" min="1" max="100" /></div>
          <div class="filter-field"><label>Discord Webhook URL</label><input type="text" class="t-input" id="set-webhook" value="${esc(s.discord_webhook)}" placeholder="https://discord.com/api/webhooks/..." /></div>
          <div class="filter-field">
            <label>Al Minimizar</label>
            <select class="t-select" id="set-minimizar" style="border-radius:8px">
              <option value="Barra" ${s.minimizar_a !== "Bandeja" ? "selected" : ""}>Barra de tareas</option>
              <option value="Bandeja" ${s.minimizar_a === "Bandeja" ? "selected" : ""}>Bandeja del sistema (2do plano)</option>
            </select>
          </div>
          <div class="filter-field"><label>Intervalo Centinela ATL (hs)</label><input type="number" class="t-input" id="set-intervalo" value="${s.watchdog_intervalo_hs}" min="1" max="72" /></div>
          <div style="display:flex;flex-direction:column;gap:6px;justify-content:flex-end">
            <label class="settings-check"><input type="checkbox" id="set-sfx" ${s.sfx_enabled ? "checked" : ""} /> 🔊 Sonidos SFX activados</label>
            <label class="settings-check"><input type="checkbox" id="set-watchdog" ${s.watchdog_activado ? "checked" : ""} /> 🔔 Centinela ATL automático</label>
            <label class="settings-check"><input type="checkbox" id="set-atl-sfx" ${s.alerta_sonido_atl !== false ? "checked" : ""} /> 🎵 Sonido especial en récords ATL</label>
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
          <span id="set-fx-status" style="font-size:11.5px;color:var(--subtext);align-self:center;margin-left:auto">${esc(fxStatusTxt)}</span>
        </div>
      </div>

      <div class="glass-card panel-card">
        <div class="panel-header">
          <span class="ficha-section-title">🚫 Gestor de Blacklist (<span id="set-blacklist-count">${(blRes?.items || []).length}</span>)</span>
          <button type="button" class="btn-danger" id="btn-bl-clear" style="height:28px">Vaciar Blacklist</button>
        </div>
        <div class="cc-list" id="set-blacklist-box" style="max-height:240px"></div>
      </div>
    `;

    _renderBlacklist(blRes?.items || []);

    container.querySelectorAll(".btn-imp-preset").forEach(btn => {
      btn.addEventListener("click", () => {
        const impInput = document.getElementById("set-imp");
        if (impInput) impInput.value = btn.dataset.imp;
      });
    });

    document.getElementById("btn-set-save")?.addEventListener("click", async () => {
      const impRaw = document.getElementById("set-imp")?.value;
      const payload = {
        steam_id: document.getElementById("set-steam-id")?.value || "",
        steam_api_key: document.getElementById("set-api-key")?.value || "",
        dolar_referencia: Number(document.getElementById("set-dolar")?.value || 1000),
        dolar_cripto_ref: Number(document.getElementById("set-cripto")?.value || 1150),
        impuestos_pct: impRaw === "" || impRaw === undefined ? 51 : Number(impRaw),
        umbral_alerta_pct: Number(document.getElementById("set-umbral")?.value || 50),
        discord_webhook: document.getElementById("set-webhook")?.value || "",
        minimizar_a: document.getElementById("set-minimizar")?.value || "Barra",
        watchdog_intervalo_hs: Number(document.getElementById("set-intervalo")?.value || 6),
        sfx_enabled: Boolean(document.getElementById("set-sfx")?.checked),
        watchdog_activado: Boolean(document.getElementById("set-watchdog")?.checked),
        alerta_sonido_atl: Boolean(document.getElementById("set-atl-sfx")?.checked),
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
      const r = await window.pywebview.api.refresh_live_fx(true);
      if (r?.ok) {
        document.getElementById("set-dolar").value = r.dolar_referencia;
        document.getElementById("set-cripto").value = r.dolar_cripto_ref;
        const statusEl = document.getElementById("set-fx-status");
        if (statusEl) {
          statusEl.textContent = `Fuente: ${r.fx_source || "En vivo"}${r.fx_updated_at ? ` · Actualizado: ${r.fx_updated_at}` : ""}`;
        }
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
    const countEl = document.getElementById("set-blacklist-count");
    if (countEl) countEl.textContent = String(items.length);
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
