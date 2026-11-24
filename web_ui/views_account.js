/* =====================================================================
   SteamScope 3.0 NEXT — Watchlist, Récords ATL, Biblioteca Co-op & Cromos
   ===================================================================== */

(function () {
  const ui = () => window.SteamScopeUI;

  const accState = {
    wl: { search: "", tag: "Todas las etiquetas", items: [], editingAppId: null, editMode: null, banner: "" },
    lib: { search: "", filter_mode: "all", sort_by: "horas_desc", page: 1, total_pages: 1, data: null },
    cards: { result: null },
    container: null,
  };

  /* ==================== 1. MI WATCHLIST ==================== */
  async function mountWatchlist(container) {
    accState.container = container;
    const esc = ui().escapeHtml;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">MI <span>WATCHLIST</span></h1>
          <div style="font-size:12px;color:var(--subtext)" id="wl-summary-line">Cargando seguimiento...</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <input type="text" class="t-input" id="wl-steamid-input" placeholder="Steam ID o Vanity..." style="width:165px" />
          <button type="button" class="btn-ghost" id="btn-wl-sync">🔄 Importar Wishlist</button>
          <button type="button" class="btn-primary-accent" id="btn-wl-drops">🔥 Comprobar Rebajas</button>
        </div>
      </div>

      <div id="wl-banner-slot"></div>

      <div class="glass-card search-toolbar">
        <input type="text" class="t-input t-input-grow" id="wl-search-input" placeholder="Buscar en tu Watchlist..." value="${esc(accState.wl.search)}" />
        <select class="t-select" id="wl-tag-select">
          <option value="Todas las etiquetas">🏷️ Todas las etiquetas</option>
        </select>
      </div>

      <div id="wl-list-area"></div>
    `;

    let tDeb = null;
    document.getElementById("wl-search-input")?.addEventListener("input", (e) => {
      accState.wl.search = e.target.value;
      clearTimeout(tDeb);
      tDeb = setTimeout(_loadWatchlist, 140);
    });

    document.getElementById("wl-tag-select")?.addEventListener("change", (e) => {
      accState.wl.tag = e.target.value;
      _loadWatchlist();
    });

    document.getElementById("btn-wl-sync")?.addEventListener("click", async () => {
      const sid = document.getElementById("wl-steamid-input")?.value.trim();
      ui().showToast("⏳ Importando Wishlist de Steam...");
      const res = await window.pywebview.api.sync_steam_wishlist(sid || null);
      if (!res?.ok) {
        ui().showToast(`⚠️ ${res?.error || "No se pudo importar"}`);
        return;
      }
      ui().renderCommandCenter(res.command_center);
      ui().showToast(`✅ Wishlist sincronizada (${res.imported_count} juegos)`);
      await _loadWatchlist();
    });

    document.getElementById("btn-wl-drops")?.addEventListener("click", async () => {
      ui().showToast("🔍 Comprobando precios en Argentina...");
      const res = await window.pywebview.api.check_watchlist_drops();
      if (!res?.ok) {
        ui().showToast(`⚠️ ${res?.error || "No se pudo comprobar"}`);
        return;
      }
      ui().renderCommandCenter(res.command_center);
      const dCnt = (res.drops || []).length;
      const tCnt = (res.target_hits || []).length;
      const aCnt = (res.atl_hits || []).length;
      accState.wl.banner = dCnt || tCnt || aCnt
        ? `🔥 Detectadas ${dCnt} rebaja(s) · 🎯 ${tCnt} meta(s) cumplida(s) · ⭐ ${aCnt} récord(s) ATL`
        : "✅ Todos los precios revisados. Sin nuevas rebajas por ahora.";
      await _loadWatchlist();
    });

    await _loadWatchlist();
  }

  async function _loadWatchlist() {
    const res = await window.pywebview.api.get_watchlist({
      search: accState.wl.search,
      tag: accState.wl.tag,
    });
    if (!res?.ok) return;
    accState.wl.items = res.items || [];

    const sidInput = document.getElementById("wl-steamid-input");
    if (sidInput && !sidInput.value && res.steam_id) sidInput.value = res.steam_id;

    const tagSel = document.getElementById("wl-tag-select");
    if (tagSel) {
      const esc = ui().escapeHtml;
      tagSel.innerHTML = `<option value="Todas las etiquetas">🏷️ Todas las etiquetas</option>` +
        (res.tags || []).map(t => `<option value="${esc(t)}" ${accState.wl.tag === t ? "selected" : ""}>🏷️ ${esc(t)}</option>`).join("");
    }

    const sumEl = document.getElementById("wl-summary-line");
    if (sumEl) {
      sumEl.textContent = `${res.total} juegos en lista · Total estimado: ${ui().formatPrice(res.total_usd)}`;
    }

    const bannerEl = document.getElementById("wl-banner-slot");
    if (bannerEl) {
      bannerEl.innerHTML = accState.wl.banner
        ? `<div class="regional-banner better" style="margin-bottom:10px">${ui().escapeHtml(accState.wl.banner)}</div>`
        : "";
    }

    _renderWatchlistItems();
  }

  function _renderWatchlistItems() {
    const area = document.getElementById("wl-list-area");
    if (!area) return;
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    const items = accState.wl.items;

    if (!items.length) {
      area.innerHTML = `<div class="glass-card empty-state">No hay juegos en tu Watchlist con el filtro actual.</div>`;
      return;
    }

    area.innerHTML = `
      <div class="deals-container view-normal">
        ${items.map(it => {
          const isEditing = accState.wl.editingAppId === String(it.appid);
          return `
            <article class="deal-card-item ${it.es_atl ? "is-atl" : ""}" data-appid="${esc(it.appid)}">
              <img class="deal-cover" src="${esc(it.header_url)}" alt="${esc(it.titulo)}" loading="lazy" onerror="this.src='${esc(it.thumb_url)}'" />
              <div class="deal-body">
                <div class="deal-badges-row">
                  ${it.es_atl ? `<span class="d-badge atl">⭐ RÉCORD ATL</span>` : ""}
                  ${it.cumple_target ? `<span class="d-badge target-hit-badge">🎯 META CUMPLIDA</span>` : ""}
                  ${it.tag ? `<span class="d-badge">🏷️ ${esc(it.tag)}</span>` : ""}
                  ${it.target_price > 0 ? `<span class="d-badge">🎯 Meta: $${Number(it.target_price).toFixed(2)} USD</span>` : ""}
                </div>
                <div class="deal-title">${esc(it.titulo)}</div>
                <div class="deal-sub">
                  ${it.note ? `📝 ${esc(it.note)}` : `Guardado: ${esc(it.fecha)}`}
                </div>
                ${isEditing ? `
                  <div class="inline-editor-pop" data-stop="1">
                    ${accState.wl.editMode === "tag" ? `
                      <input type="text" class="t-input" id="wl-inline-input" style="width:180px" placeholder="Ej: RPG, Co-op..." value="${esc(it.tag || "")}" />
                    ` : `
                      <input type="number" class="t-input" id="wl-inline-input" style="width:140px" min="0" max="9999" step="0.5" placeholder="USD (0 quita)" value="${it.target_price > 0 ? it.target_price : ""}" />
                    `}
                    <button type="button" class="btn-primary-accent" style="height:30px;padding:0 12px" id="btn-wl-inline-save">Guardar</button>
                    <button type="button" class="btn-ghost" style="height:30px" id="btn-wl-inline-cancel">Cancelar</button>
                  </div>
                ` : ""}
              </div>
              <div class="deal-right">
                <div class="deal-price-pill">
                  ${it.descuento > 0 ? `<span class="deal-pct">-${it.descuento}%</span>` : ""}
                  <div class="deal-prices">
                    ${it.precio_normal_usd > it.precio_oferta_usd ? `<span class="deal-old">${esc(fmt(it.precio_normal_usd))}</span>` : ""}
                    <span class="deal-now">${esc(fmt(it.precio_oferta_usd))}</span>
                  </div>
                </div>
                <div class="deal-actions">
                  <button type="button" class="act-btn btn-wl-tag" data-appid="${esc(it.appid)}" title="Asignar Etiqueta">🏷️</button>
                  <button type="button" class="act-btn btn-wl-target" data-appid="${esc(it.appid)}" title="Precio Objetivo (USD)">🎯</button>
                  <button type="button" class="act-btn ${it.in_cart ? "active" : ""} btn-wl-cart" data-appid="${esc(it.appid)}" title="Changuito">🛒</button>
                  <button type="button" class="act-btn btn-wl-web" data-appid="${esc(it.appid)}" title="Steam Web (-21%)">🌐</button>
                  <button type="button" class="act-btn btn-wl-rm" data-appid="${esc(it.appid)}" title="Quitar de Watchlist">🗑</button>
                </div>
              </div>
            </article>
          `;
        }).join("")}
      </div>
    `;

    area.querySelectorAll("[data-stop='1']").forEach(el => el.addEventListener("click", e => e.stopPropagation()));

    area.querySelectorAll(".deal-card-item").forEach(card => {
      card.addEventListener("click", () => {
        const it = items.find(x => String(x.appid) === card.dataset.appid);
        if (it && window.FichaView) window.FichaView.openFicha(it.appid, it);
      });
    });

    area.querySelectorAll(".btn-wl-tag").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        accState.wl.editingAppId = btn.dataset.appid;
        accState.wl.editMode = "tag";
        _renderWatchlistItems();
        document.getElementById("wl-inline-input")?.focus();
      });
    });

    area.querySelectorAll(".btn-wl-target").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        accState.wl.editingAppId = btn.dataset.appid;
        accState.wl.editMode = "target";
        _renderWatchlistItems();
        document.getElementById("wl-inline-input")?.focus();
      });
    });

    document.getElementById("btn-wl-inline-cancel")?.addEventListener("click", (e) => {
      e.stopPropagation();
      accState.wl.editingAppId = null;
      _renderWatchlistItems();
    });

    document.getElementById("btn-wl-inline-save")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      const aid = accState.wl.editingAppId;
      const val = document.getElementById("wl-inline-input")?.value ?? "";
      if (accState.wl.editMode === "tag") {
        await window.pywebview.api.set_watchlist_tag(aid, val);
        ui().showToast("🏷️ Etiqueta actualizada");
      } else {
        const r = await window.pywebview.api.set_watchlist_target_price(aid, Number(val || 0));
        if (r?.ok) ui().renderCommandCenter(r.command_center);
        ui().showToast("🎯 Precio objetivo actualizado");
      }
      accState.wl.editingAppId = null;
      await _loadWatchlist();
    });

    area.querySelectorAll(".btn-wl-cart").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const it = items.find(x => String(x.appid) === btn.dataset.appid);
        if (!it) return;
        const r = await window.pywebview.api.toggle_cart_item(it);
        if (r?.ok) {
          ui().renderCommandCenter(r.command_center);
          await _loadWatchlist();
        }
      });
    });

    area.querySelectorAll(".btn-wl-web").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        window.pywebview.api.open_external_url(`https://store.steampowered.com/app/${btn.dataset.appid}`);
      });
    });

    area.querySelectorAll(".btn-wl-rm").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const it = items.find(x => String(x.appid) === btn.dataset.appid);
        if (!it) return;
        const r = await window.pywebview.api.toggle_watchlist_item(it);
        if (r?.ok) {
          ui().renderCommandCenter(r.command_center);
          ui().showToast(`🗑 "${it.titulo}" quitado de Watchlist`);
          await _loadWatchlist();
        }
      });
    });
  }

  /* ==================== 2. HISTORIAL RÉCORDS ATL ==================== */
  async function mountATL(container) {
    accState.container = container;
    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">HISTORIAL DE <span>RÉCORDS ATL</span></h1>
          <div style="font-size:12px;color:var(--subtext)" id="atl-count-line">Cargando mínimos históricos...</div>
        </div>
        <button type="button" class="btn-danger" id="btn-atl-clear">🗑 Limpiar Historial</button>
      </div>
      <div id="atl-list-area"></div>
    `;

    document.getElementById("btn-atl-clear")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.clear_atl_history();
      if (r?.ok) {
        ui().renderCommandCenter(r.command_center);
        ui().showToast("🗑 Historial ATL vaciado");
        await _loadATL();
      }
    });

    await _loadATL();
  }

  async function _loadATL() {
    const res = await window.pywebview.api.get_atl_history(100);
    const items = res?.items || [];
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;

    const cntEl = document.getElementById("atl-count-line");
    if (cntEl) cntEl.textContent = `${items.length} récord(s) históricos registrados localmente.`;

    const area = document.getElementById("atl-list-area");
    if (!area) return;
    if (!items.length) {
      area.innerHTML = `<div class="glass-card empty-state">Todavía no hay récords ATL registrados. Escaneá ofertas o comprobá rebajas en tu Watchlist.</div>`;
      return;
    }

    area.innerHTML = `
      <div class="deals-container view-normal">
        ${items.map(a => `
          <article class="deal-card-item is-atl" data-appid="${esc(a.appid)}" style="cursor:pointer">
            <img class="deal-cover" src="https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${esc(a.appid)}/header.jpg" alt="${esc(a.titulo)}" loading="lazy" />
            <div class="deal-body">
              <div class="deal-badges-row"><span class="d-badge atl">⭐ RÉCORD HISTÓRICO</span></div>
              <div class="deal-title">${esc(a.titulo)}</div>
              <div class="deal-sub">📅 Detectado el ${esc(a.fecha)} · AppID ${esc(a.appid)}</div>
            </div>
            <div class="deal-right">
              <div class="deal-price-pill">
                <span class="deal-pct">-${Number(a.desc_pct || 0)}%</span>
                <div class="deal-prices"><span class="deal-now">${esc(fmt(a.precio_usd))}</span></div>
              </div>
            </div>
          </article>
        `).join("")}
      </div>
    `;

    area.querySelectorAll(".deal-card-item").forEach(card => {
      card.addEventListener("click", () => {
        if (window.FichaView) window.FichaView.openFicha(card.dataset.appid);
      });
    });
  }

  /* ==================== 3. MI BIBLIOTECA & CO-OP ==================== */
  async function mountLibrary(container) {
    accState.container = container;
    const esc = ui().escapeHtml;
    const l = accState.lib;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">MI BIBLIOTECA <span>&amp; RADAR CO-OP</span></h1>
          <div style="font-size:12px;color:var(--subtext)" id="lib-status-line">Caché SQLite instantánea (0 ms).</div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <button type="button" class="btn-primary-accent" id="btn-lib-sync">🔄 Sincronizar Biblioteca</button>
          <button type="button" class="btn-ghost" id="btn-lib-valuate">💰 Valuar Cuenta</button>
          <button type="button" class="btn-ghost" id="btn-lib-random">🎲 ¿A qué juego hoy?</button>
        </div>
      </div>

      <div class="account-metrics-grid" id="lib-metrics-grid"></div>
      <div id="lib-coop-banner"></div>

      <div class="glass-card search-toolbar">
        <input type="text" class="t-input t-input-grow" id="lib-search-input" placeholder="Filtrar biblioteca por nombre..." value="${esc(l.search)}" />
        <div class="segmented-control" id="lib-filter-seg">
          ${[
            ["all", "Todos"],
            ["unplayed", "Sin estrenar"],
            ["played", "Jugados"],
            ["coop", "Co-op en común"],
          ].map(([id, lbl]) => `
            <button type="button" class="seg-btn ${l.filter_mode === id ? "active" : ""}" data-lfilter="${id}">${lbl}</button>
          `).join("")}
        </div>
        <select class="t-select" id="lib-sort-select">
          <option value="horas_desc" ${l.sort_by === "horas_desc" ? "selected" : ""}>Más jugados</option>
          <option value="horas_asc" ${l.sort_by === "horas_asc" ? "selected" : ""}>Menos jugados</option>
          <option value="titulo_asc" ${l.sort_by === "titulo_asc" ? "selected" : ""}>Alfabético</option>
          <option value="precio_desc" ${l.sort_by === "precio_desc" ? "selected" : ""}>Mayor valor</option>
        </select>
      </div>

      <div class="glass-card search-toolbar">
        <input type="text" class="t-input t-input-grow" id="lib-friend-input" placeholder="Radar Co-op: Steam ID o URL de tu amigo..." />
        <button type="button" class="btn-ghost" id="btn-lib-coop">🤝 Cruzar Bibliotecas</button>
      </div>

      <div id="lib-list-area"></div>

      <div class="glass-card pagination-bar" id="lib-pagination" style="display:none">
        <div style="font-size:12px;color:var(--subtext)" id="lib-pag-summary"></div>
        <div class="pag-controls">
          <button type="button" class="btn-ghost" id="btn-lib-prev">◀ Anterior</button>
          <span class="kbd-badge" id="lib-pag-lbl">Pág 1 / 1</span>
          <button type="button" class="btn-ghost" id="btn-lib-next">Siguiente ▶</button>
        </div>
      </div>
    `;

    let tDeb = null;
    document.getElementById("lib-search-input")?.addEventListener("input", (e) => {
      accState.lib.search = e.target.value;
      accState.lib.page = 1;
      clearTimeout(tDeb);
      tDeb = setTimeout(_loadLibrary, 120);
    });

    document.querySelectorAll("#lib-filter-seg .seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        accState.lib.filter_mode = btn.dataset.lfilter;
        accState.lib.page = 1;
        document.querySelectorAll("#lib-filter-seg .seg-btn").forEach(b => b.classList.toggle("active", b === btn));
        _loadLibrary();
      });
    });

    document.getElementById("lib-sort-select")?.addEventListener("change", (e) => {
      accState.lib.sort_by = e.target.value;
      accState.lib.page = 1;
      _loadLibrary();
    });

    document.getElementById("btn-lib-sync")?.addEventListener("click", async () => {
      ui().showToast("⏳ Descargando biblioteca de Steam...");
      const r = await window.pywebview.api.sync_steam_library();
      if (!r?.ok) {
        ui().showToast(`⚠️ ${r?.error || "Error al sincronizar"}`);
        return;
      }
      ui().renderCommandCenter(r.command_center);
      ui().showToast(`✅ Biblioteca sincronizada: ${r.count} juegos`);
      await _loadLibrary();
    });

    document.getElementById("btn-lib-valuate")?.addEventListener("click", async () => {
      ui().showToast("💰 Valuando juegos pendientes en Steam...");
      const r = await window.pywebview.api.valuate_library(120);
      if (!r?.ok) {
        ui().showToast(`⚠️ ${r?.error || "Error al valuar"}`);
        return;
      }
      ui().renderCommandCenter(r.command_center);
      ui().showToast(`💰 Valuación actualizada (${r.updated_count} juegos)`);
      await _loadLibrary();
    });

    document.getElementById("btn-lib-random")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.pick_random_backlog();
      if (!r?.ok || !r.game) {
        ui().showToast(`⚠️ ${r?.error || "Sin juegos disponibles"}`);
        return;
      }
      ui().showToast(`🎲 Salió sorteado: ${r.game.titulo}`);
      if (window.FichaView) window.FichaView.openFicha(r.game.appid, r.game);
    });

    document.getElementById("btn-lib-coop")?.addEventListener("click", async () => {
      const fid = document.getElementById("lib-friend-input")?.value.trim();
      if (!fid) {
        ui().showToast("⚠️ Ingresá el Steam ID de tu amigo");
        return;
      }
      ui().showToast("🤝 Cruzando bibliotecas...");
      const r = await window.pywebview.api.cross_friend_library(fid);
      if (!r?.ok) {
        ui().showToast(`⚠️ ${r?.error || "No se pudo cruzar"}`);
        return;
      }
      accState.lib.filter_mode = "coop";
      accState.lib.page = 1;
      document.querySelectorAll("#lib-filter-seg .seg-btn").forEach(b => b.classList.toggle("active", b.dataset.lfilter === "coop"));
      ui().showToast(`🤝 ¡${r.common_count} juegos en común encontrados!`);
      await _loadLibrary();
    });

    document.getElementById("btn-lib-prev")?.addEventListener("click", () => {
      if (accState.lib.page > 1) { accState.lib.page -= 1; _loadLibrary(); }
    });
    document.getElementById("btn-lib-next")?.addEventListener("click", () => {
      if (accState.lib.page < accState.lib.total_pages) { accState.lib.page += 1; _loadLibrary(); }
    });

    await _loadLibrary();
  }

  async function _loadLibrary() {
    const res = await window.pywebview.api.get_library({
      search: accState.lib.search,
      filter_mode: accState.lib.filter_mode,
      sort_by: accState.lib.sort_by,
      page: accState.lib.page,
      per_page: 30,
    });
    if (!res?.ok) return;
    accState.lib.data = res;
    accState.lib.page = res.page;
    accState.lib.total_pages = res.total_pages;

    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    const m = res.metrics || {};
    const v = res.valuation || {};

    const metricsGrid = document.getElementById("lib-metrics-grid");
    if (metricsGrid) {
      metricsGrid.innerHTML = `
        <div class="metric-tile"><span>Total Juegos</span><strong>${m.total || 0}</strong></div>
        <div class="metric-tile"><span>Sin Estrenar (&lt;0.1h)</span><strong>${m.sin_jugar || 0} (${m.pct_sin_jugar || 0}%)</strong></div>
        <div class="metric-tile"><span>Horas Totales</span><strong>${m.horas_totales || 0} hs</strong></div>
        <div class="metric-tile"><span>Valor Cuenta · $/h</span><strong>${esc(fmt(v.total_value_usd || 0))} · $${Number(v.cost_per_hour_usd || 0).toFixed(2)}/h</strong></div>
      `;
    }

    const coopEl = document.getElementById("lib-coop-banner");
    if (coopEl) {
      if (res.friend_id) {
        coopEl.innerHTML = `
          <div class="coop-banner">
            <span>🤝 Cruzando con Steam ID ${esc(res.friend_id)} — ${res.friend_common_count} juegos en común</span>
            <button type="button" class="btn-ghost" id="btn-lib-clear-coop" style="height:28px">Limpiar Cruce</button>
          </div>
        `;
        document.getElementById("btn-lib-clear-coop")?.addEventListener("click", async () => {
          await window.pywebview.api.clear_friend_cross();
          accState.lib.filter_mode = "all";
          document.querySelectorAll("#lib-filter-seg .seg-btn").forEach(b => b.classList.toggle("active", b.dataset.lfilter === "all"));
          await _loadLibrary();
        });
      } else {
        coopEl.innerHTML = "";
      }
    }

    const area = document.getElementById("lib-list-area");
    const items = res.items || [];
    if (area) {
      if (!items.length) {
        area.innerHTML = `<div class="glass-card empty-state">No hay juegos en la biblioteca con este filtro.</div>`;
      } else {
        area.innerHTML = `
          <div class="deals-container view-compact">
            ${items.map(g => `
              <article class="deal-card-item" data-appid="${esc(g.appid)}" style="cursor:pointer">
                <img class="deal-cover" src="${esc(g.thumb_url)}" alt="${esc(g.titulo)}" loading="lazy" />
                <div class="deal-body">
                  <div class="deal-badges-row">
                    ${g.horas < 0.1 ? `<span class="d-badge">🆕 Sin estrenar</span>` : `<span class="d-badge deck">⏱️ ${g.horas} hs</span>`}
                    ${g.in_common_coop ? `<span class="d-badge free">🤝 En común Co-op</span>` : ""}
                  </div>
                  <div class="deal-title">${esc(g.titulo)}</div>
                </div>
                <div class="deal-right">
                  ${g.price_usd >= 0 ? `<span class="cc-price-tag">${esc(fmt(g.price_usd))}</span>` : `<span class="panel-hint">Sin valuar</span>`}
                </div>
              </article>
            `).join("")}
          </div>
        `;
        area.querySelectorAll(".deal-card-item").forEach(card => {
          card.addEventListener("click", () => {
            if (window.FichaView) window.FichaView.openFicha(card.dataset.appid);
          });
        });
      }
    }

    const pag = document.getElementById("lib-pagination");
    if (pag) {
      pag.style.display = res.total_filtered > 0 ? "flex" : "none";
      document.getElementById("lib-pag-summary").textContent = `Página ${res.page} de ${res.total_pages} · ${res.total_filtered} juegos`;
      document.getElementById("lib-pag-lbl").textContent = `Pág ${res.page} / ${res.total_pages}`;
      document.getElementById("btn-lib-prev").disabled = res.page <= 1;
      document.getElementById("btn-lib-next").disabled = res.page >= res.total_pages;
    }
  }

  /* ==================== 4. GESTOR DE CROMOS & BILLETERA ==================== */
  async function mountCards(container) {
    accState.container = container;
    const bootSid = ui().getState()?.cc ? (await window.pywebview.api.get_watchlist()).steam_id : "";
    const esc = ui().escapeHtml;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">GESTOR DE <span>CROMOS &amp; BILLETERA</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Calculá cuánto saldo Steam podés fondear vendiendo tus cromos (-15% comisión).</div>
        </div>
        <div style="display:flex;gap:8px">
          <button type="button" class="btn-ghost" id="btn-cards-market">🛒 Mercado Steam</button>
          <button type="button" class="btn-ghost" id="btn-cards-badges">🏅 Mis Medallas</button>
        </div>
      </div>

      <div class="glass-card search-toolbar">
        <input type="text" class="t-input t-input-grow" id="cards-steamid-input" placeholder="Steam ID de 17 dígitos o Vanity URL (perfil e inventario públicos)..." value="${esc(bootSid || "")}" />
        <button type="button" class="btn-primary-accent" id="btn-cards-analyze">🔍 Analizar Inventario</button>
        <button type="button" class="btn-ghost" id="btn-cards-refresh">🔄 Forzar Refresco</button>
      </div>

      <div id="cards-results-area">
        ${accState.cards.result ? "" : `<div class="glass-card empty-state">Ingresá tu Steam ID y tocá <strong>Analizar Inventario</strong> para valorar tus cromos.</div>`}
      </div>
    `;

    document.getElementById("btn-cards-analyze")?.addEventListener("click", () => _runCardsAnalysis(false));
    document.getElementById("btn-cards-refresh")?.addEventListener("click", () => _runCardsAnalysis(true));
    document.getElementById("btn-cards-market")?.addEventListener("click", () => {
      window.pywebview.api.open_external_url("https://steamcommunity.com/market/");
    });
    document.getElementById("btn-cards-badges")?.addEventListener("click", () => {
      const sid = document.getElementById("cards-steamid-input")?.value.trim();
      const url = sid ? `https://steamcommunity.com/profiles/${encodeURIComponent(sid)}/badges/` : "https://steamcommunity.com/market/";
      window.pywebview.api.open_external_url(url);
    });

    if (accState.cards.result) _renderCardsResult(accState.cards.result);
  }

  async function _runCardsAnalysis(forceRefresh) {
    const sid = document.getElementById("cards-steamid-input")?.value.trim() || null;
    const area = document.getElementById("cards-results-area");
    if (area) area.innerHTML = `<div class="skeleton-list"><div class="skeleton-card"></div><div class="skeleton-card"></div></div>`;

    const res = await window.pywebview.api.analyze_trading_cards(sid, forceRefresh);
    accState.cards.result = res;
    _renderCardsResult(res);
  }

  function _renderCardsResult(res) {
    const area = document.getElementById("cards-results-area");
    if (!area) return;
    const esc = ui().escapeHtml;
    if (!res?.ok) {
      area.innerHTML = `<div class="glass-card empty-state">⚠️ ${esc(res?.error || "No se pudo analizar el inventario.")}</div>`;
      return;
    }

    const juegos = res.juegos || [];
    area.innerHTML = `
      <div class="account-metrics-grid">
        <div class="metric-tile"><span>Total Cromos</span><strong>${res.total_cromos || 0}</strong></div>
        <div class="metric-tile"><span>Juegos con Cromos</span><strong>${res.total_juegos || 0}</strong></div>
        <div class="metric-tile"><span>Valor Bruto</span><strong>$${Number(res.valor_bruto_usd || 0).toFixed(2)} USD</strong></div>
        <div class="metric-tile"><span>Saldo Neto (-15% Fee)</span><strong style="color:var(--emerald)">$${Number(res.valor_neto_usd || 0).toFixed(2)} USD ($${Number(res.valor_neto_ars || 0).toLocaleString("es-AR")} ARS)</strong></div>
      </div>

      <div class="cc-list" style="max-height:480px">
        ${juegos.length ? juegos.map(j => {
          const cnt = Number(j.cantidad || 0);
          const estNeto = (cnt * 0.06 * 0.85).toFixed(2);
          return `
            <div class="cards-row">
              <div>
                <strong>${esc(j.game_name || "Juego")}</strong>
                <div style="font-size:11.5px;color:var(--subtext)">${cnt} cromo(s) vendible(s) · AppID ${esc(j.appid || "N/D")}</div>
              </div>
              <span class="cc-price-tag">~$${estNeto} USD neto</span>
            </div>
          `;
        }).join("") : `<div class="empty-state">No se encontraron cromos comercializables en tu inventario.</div>`}
      </div>
    `;
  }

  window.AccountView = {
    mountWatchlist,
    mountATL,
    mountLibrary,
    mountCards,
    refreshActive: (tabId) => {
      if (tabId === "watchlist") _loadWatchlist();
      else if (tabId === "atl") _loadATL();
      else if (tabId === "library") _loadLibrary();
      else if (tabId === "cards" && accState.cards.result) _renderCardsResult(accState.cards.result);
    },
  };
})();
