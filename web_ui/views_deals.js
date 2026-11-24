/* =====================================================================
   SteamScope 3.0 NEXT — Vista de Ofertas, Filtros 2 Niveles & Changuito
   ===================================================================== */

(function () {
  const ui = () => window.SteamScopeUI;

  const dealsState = {
    initialized: false,
    meta: null,
    items: [],
    kpis: { all: 0, atl: 0, free: 0, sub: 0, cards: 0, coop: 0, avg_usd: 0 },
    page: 1,
    totalPages: 1,
    totalFiltered: 0,
    totalRaw: 0,
    vista: "Normal",
    filtersOpen: true,
    kpiFilter: "all",
    scanning: false,
    localTimer: null,
    params: {
      query: "",
      descuento: "Cualquier Descuento",
      precio_rango: "Cualquier Precio",
      precio_max_usd: "",
      calidad: "Cualquier Calidad",
      modalidad: "Cualquiera",
      cat_padre: "Todas las Categorías",
      subcat: "Todas las subcategorías",
      limite: 100,
      sort_by: "Mayor Descuento",
      local_filter: "",
    },
  };

  function _viewClass(vista) {
    if (vista === "Compacta") return "view-compact";
    if (vista === "Grilla") return "view-grid";
    return "view-normal";
  }

  function _findItem(appid) {
    return dealsState.items.find(i => String(i.appid) === String(appid)) || null;
  }

  async function mount(container) {
    if (!dealsState.meta) {
      dealsState.meta = await window.pywebview.api.get_deals_metadata();
      dealsState.vista = dealsState.meta.vista || "Normal";
    }

    const esc = ui().escapeHtml;
    const m = dealsState.meta;
    const p = dealsState.params;

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">EXPLORADOR DE <span>OFERTAS STEAM</span></h1>
          <div style="font-size:12px;color:var(--subtext)" id="deals-status-line">
            Listo para escanear descuentos reales en Argentina (USD / Tarjeta / Cripto).
          </div>
        </div>
        <div class="segmented-control" id="deals-view-seg">
          ${["Compacta", "Normal", "Grilla"].map(v => `
            <button type="button" class="seg-btn ${dealsState.vista === v ? "active" : ""}" data-vista="${v}">${v}</button>
          `).join("")}
        </div>
      </div>

      <div class="glass-card search-toolbar">
        <input type="text" class="t-input t-input-grow" id="deals-smart-query" placeholder="Buscar juego por nombre en Steam (o dejar vacío para escanear top rebajas)..." value="${esc(p.query)}" />
        <select class="t-select" id="deals-recents-select" title="Búsquedas recientes">
          <option value="">🕒 Recientes</option>
          ${(m.recientes || []).map(r => `<option value="${esc(r)}">${esc(r)}</option>`).join("")}
        </select>
        <button type="button" class="btn-primary-accent" id="btn-deals-scan">🔍 Escanear / Buscar</button>
        <button type="button" class="btn-ghost" id="btn-deals-toggle-filters">${dealsState.filtersOpen ? "🔼 Filtros" : "🔽 Filtros"}</button>
        <button type="button" class="btn-ghost" id="btn-deals-save-preset" title="Guardar preset favorito">⭐</button>
        <button type="button" class="btn-ghost" id="btn-deals-load-preset" title="Cargar preset favorito">📂</button>
        <button type="button" class="btn-ghost" id="btn-deals-reset" title="Restablecer filtros">🧹</button>
      </div>

      <div class="glass-card filters-panel ${dealsState.filtersOpen ? "" : "hidden"}" id="deals-filters-panel">
        <div class="filter-field">
          <label>Descuento</label>
          <select class="t-select" id="f-descuento">
            ${m.descuentos.map(d => `<option value="${esc(d)}" ${p.descuento === d ? "selected" : ""}>${esc(d)}</option>`).join("")}
          </select>
        </div>
        <div class="filter-field">
          <label>Rango de Precio</label>
          <select class="t-select" id="f-precio-rango">
            ${m.precios.map(pr => `<option value="${esc(pr)}" ${p.precio_rango === pr ? "selected" : ""}>${esc(pr)}</option>`).join("")}
          </select>
        </div>
        <div class="filter-field">
          <label>Precio Máx (USD)</label>
          <input type="text" class="t-input" id="f-precio-max" placeholder="Ej: 12.50" value="${esc(p.precio_max_usd)}" />
        </div>
        <div class="filter-field">
          <label>Calidad / Reseñas</label>
          <select class="t-select" id="f-calidad">
            ${m.calidades.map(c => `<option value="${esc(c)}" ${p.calidad === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
          </select>
        </div>
        <div class="filter-field">
          <label>Categoría Steam</label>
          <select class="t-select" id="f-cat-padre">
            ${Object.keys(m.categorias).map(c => `<option value="${esc(c)}" ${p.cat_padre === c ? "selected" : ""}>${esc(c)}</option>`).join("")}
          </select>
        </div>
        <div class="filter-field">
          <label>Subgénero / Subcategoría</label>
          <select class="t-select" id="f-subcat"></select>
        </div>
        <div class="filter-field">
          <label>Modalidad</label>
          <select class="t-select" id="f-modalidad">
            ${m.modalidades.map(mo => `<option value="${esc(mo)}" ${p.modalidad === mo ? "selected" : ""}>${esc(mo)}</option>`).join("")}
          </select>
        </div>
        <div class="filter-field">
          <label>Límite de Escaneo</label>
          <select class="t-select" id="f-limite">
            ${m.limites.map(l => `<option value="${l}" ${Number(p.limite) === l ? "selected" : ""}>${l} ofertas</option>`).join("")}
          </select>
        </div>
      </div>

      <div class="subbar-row">
        <input type="text" class="t-input" style="min-width:250px;flex:1" id="deals-local-filter" placeholder="⚡ Filtrar resultados cargados en vivo (título o tag)..." value="${esc(p.local_filter)}" />
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:12px;color:var(--subtext);font-weight:700">Ordenar:</span>
          <select class="t-select" id="f-sort-by">
            ${m.ordenes.map(o => `<option value="${esc(o)}" ${p.sort_by === o ? "selected" : ""}>${esc(o)}</option>`).join("")}
          </select>
          <button type="button" class="btn-ghost" id="btn-deals-open-cart">🛒 Ver Changuito</button>
        </div>
      </div>

      <div class="kpi-pills-bar" id="deals-kpi-bar" style="display:none"></div>

      <div id="deals-results-area"></div>

      <div class="glass-card pagination-bar" id="deals-pagination" style="display:none">
        <div style="font-size:12px;color:var(--subtext)" id="deals-pag-summary"></div>
        <div class="pag-controls">
          <button type="button" class="btn-ghost" id="btn-deals-prev">◀ Anterior</button>
          <span class="kbd-badge" id="deals-pag-lbl">Pág 1 / 1</span>
          <button type="button" class="btn-ghost" id="btn-deals-next">Siguiente ▶</button>
        </div>
      </div>
    `;

    _populateSubcategories(p.cat_padre, p.subcat);
    _bindViewEvents();

    if (dealsState.totalRaw > 0) {
      await queryAndRender();
    } else {
      _renderEmptyPrompt();
    }
  }

  function _populateSubcategories(catPadre, selectedSub) {
    const subSel = document.getElementById("f-subcat");
    if (!subSel || !dealsState.meta) return;
    const subs = dealsState.meta.categorias[catPadre] || ["Todas las subcategorías"];
    const esc = ui().escapeHtml;
    subSel.innerHTML = subs.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
    subSel.value = subs.includes(selectedSub) ? selectedSub : subs[0];
    dealsState.params.subcat = subSel.value;
  }

  function _bindViewEvents() {
    document.getElementById("btn-deals-scan")?.addEventListener("click", scanOrSearch);
    document.getElementById("deals-smart-query")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") scanOrSearch();
    });

    document.getElementById("deals-recents-select")?.addEventListener("change", (e) => {
      if (!e.target.value) return;
      document.getElementById("deals-smart-query").value = e.target.value;
      dealsState.params.query = e.target.value;
      e.target.value = "";
      scanOrSearch();
    });

    document.querySelectorAll("#deals-view-seg .seg-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const v = btn.dataset.vista;
        dealsState.vista = v;
        document.querySelectorAll("#deals-view-seg .seg-btn").forEach(b => b.classList.toggle("active", b === btn));
        await window.pywebview.api.set_vista(v);
        _renderCards();
      });
    });

    document.getElementById("btn-deals-toggle-filters")?.addEventListener("click", () => {
      dealsState.filtersOpen = !dealsState.filtersOpen;
      document.getElementById("deals-filters-panel")?.classList.toggle("hidden", !dealsState.filtersOpen);
      document.getElementById("btn-deals-toggle-filters").textContent = dealsState.filtersOpen ? "🔼 Filtros" : "🔽 Filtros";
    });

    document.getElementById("f-cat-padre")?.addEventListener("change", (e) => {
      dealsState.params.cat_padre = e.target.value;
      _populateSubcategories(e.target.value, "");
      dealsState.page = 1;
      queryAndRender();
    });

    ["f-descuento", "f-precio-rango", "f-calidad", "f-subcat", "f-modalidad", "f-sort-by"].forEach(id => {
      document.getElementById(id)?.addEventListener("change", () => {
        _syncParamsFromDOM();
        dealsState.page = 1;
        queryAndRender();
      });
    });

    document.getElementById("f-limite")?.addEventListener("change", () => {
      _syncParamsFromDOM();
    });

    document.getElementById("f-precio-max")?.addEventListener("input", () => {
      clearTimeout(dealsState.localTimer);
      dealsState.localTimer = setTimeout(() => {
        _syncParamsFromDOM();
        dealsState.page = 1;
        queryAndRender();
      }, 220);
    });

    document.getElementById("deals-local-filter")?.addEventListener("input", () => {
      clearTimeout(dealsState.localTimer);
      dealsState.localTimer = setTimeout(() => {
        _syncParamsFromDOM();
        dealsState.page = 1;
        queryAndRender();
      }, 140);
    });

    document.getElementById("btn-deals-save-preset")?.addEventListener("click", async () => {
      _syncParamsFromDOM();
      await window.pywebview.api.save_filter_preset(dealsState.params);
      ui().showToast("⭐ Preset de filtros guardado");
    });

    document.getElementById("btn-deals-load-preset")?.addEventListener("click", async () => {
      const res = await window.pywebview.api.load_filter_preset();
      if (!res?.ok) {
        ui().showToast("⚠️ No hay preset guardado todavía");
        return;
      }
      Object.assign(dealsState.params, res.preset);
      await mount(document.getElementById("view-dynamic"));
      ui().showToast("📂 Preset cargado");
    });

    document.getElementById("btn-deals-reset")?.addEventListener("click", async () => {
      dealsState.kpiFilter = "all";
      dealsState.page = 1;
      dealsState.params = {
        query: "",
        descuento: "Cualquier Descuento",
        precio_rango: "Cualquier Precio",
        precio_max_usd: "",
        calidad: "Cualquier Calidad",
        modalidad: "Cualquiera",
        cat_padre: "Todas las Categorías",
        subcat: "Todas las subcategorías",
        limite: 100,
        sort_by: "Mayor Descuento",
        local_filter: "",
      };
      await mount(document.getElementById("view-dynamic"));
      ui().showToast("🧹 Filtros restablecidos");
    });

    document.getElementById("btn-deals-open-cart")?.addEventListener("click", () => ui().openCartModal());

    document.getElementById("btn-deals-prev")?.addEventListener("click", () => {
      if (dealsState.page > 1) {
        dealsState.page -= 1;
        queryAndRender();
      }
    });

    document.getElementById("btn-deals-next")?.addEventListener("click", () => {
      if (dealsState.page < dealsState.totalPages) {
        dealsState.page += 1;
        queryAndRender();
      }
    });
  }

  function _syncParamsFromDOM() {
    const val = (id, fb = "") => document.getElementById(id)?.value ?? fb;
    dealsState.params.query = val("deals-smart-query").trim();
    dealsState.params.descuento = val("f-descuento", "Cualquier Descuento");
    dealsState.params.precio_rango = val("f-precio-rango", "Cualquier Precio");
    dealsState.params.precio_max_usd = val("f-precio-max").trim();
    dealsState.params.calidad = val("f-calidad", "Cualquier Calidad");
    dealsState.params.cat_padre = val("f-cat-padre", "Todas las Categorías");
    dealsState.params.subcat = val("f-subcat", "Todas las subcategorías");
    dealsState.params.modalidad = val("f-modalidad", "Cualquiera");
    dealsState.params.limite = Number(val("f-limite", 100)) || 100;
    dealsState.params.sort_by = val("f-sort-by", "Mayor Descuento");
    dealsState.params.local_filter = val("deals-local-filter");
  }

  function _renderEmptyPrompt() {
    const area = document.getElementById("deals-results-area");
    if (!area) return;
    area.innerHTML = `
      <div class="glass-card phase-placeholder" style="margin:26px auto">
        <span class="phase-badge">MOTOR LISTO</span>
        <h2>Escaneá ofertas reales o buscá un título</h2>
        <p>Presioná <strong>Escanear / Buscar</strong> para consultar CheapShark + precios regionales de Argentina en paralelo y detectar Mínimos Históricos (ATL).</p>
        <button type="button" class="btn-primary-accent" id="btn-empty-scan">🚀 Escanear Top Ofertas Ahora</button>
      </div>
    `;
    document.getElementById("btn-empty-scan")?.addEventListener("click", scanOrSearch);
  }

  function _renderSkeleton() {
    const area = document.getElementById("deals-results-area");
    if (!area) return;
    area.innerHTML = `<div class="skeleton-list">${Array(6).fill(`<div class="skeleton-card"></div>`).join("")}</div>`;
  }

  async function scanOrSearch() {
    if (dealsState.scanning) return;
    _syncParamsFromDOM();
    dealsState.scanning = true;
    dealsState.kpiFilter = "all";
    dealsState.page = 1;

    const status = document.getElementById("deals-status-line");
    if (status) {
      status.textContent = dealsState.params.query
        ? `Buscando "${dealsState.params.query}" en Steam (región AR)...`
        : `Escaneando catálogo de ofertas (objetivo: ${dealsState.params.limite})...`;
    }
    _renderSkeleton();

    try {
      const res = await window.pywebview.api.search_or_scan_deals({
        ...dealsState.params,
        kpi_filter: dealsState.kpiFilter,
        page: 1,
      });

      if (!res?.ok) {
        if (status) status.textContent = res?.error || "Error al consultar ofertas.";
        ui().showToast(`⚠️ ${res?.error || "Error de red"}`);
        _renderEmptyPrompt();
        return;
      }

      if (Array.isArray(res.recientes) && dealsState.meta) {
        dealsState.meta.recientes = res.recientes;
        const recSel = document.getElementById("deals-recents-select");
        if (recSel) {
          const esc = ui().escapeHtml;
          recSel.innerHTML = `<option value="">🕒 Recientes</option>` +
            res.recientes.map(r => `<option value="${esc(r)}">${esc(r)}</option>`).join("");
        }
      }

      _applyQueryResult(res);
      const cc = await window.pywebview.api.get_command_center_data();
      ui().renderCommandCenter(cc);
    } finally {
      dealsState.scanning = false;
    }
  }

  async function queryAndRender() {
    if (dealsState.totalRaw === 0) {
      _renderEmptyPrompt();
      return;
    }
    _syncParamsFromDOM();
    const res = await window.pywebview.api.query_deals({
      ...dealsState.params,
      kpi_filter: dealsState.kpiFilter,
      page: dealsState.page,
    });
    if (res?.ok) _applyQueryResult(res);
  }

  function _applyQueryResult(res) {
    dealsState.items = res.items || [];
    dealsState.kpis = res.kpis || dealsState.kpis;
    dealsState.page = res.page || 1;
    dealsState.totalPages = res.total_pages || 1;
    dealsState.totalFiltered = res.total_filtered || 0;
    dealsState.totalRaw = res.total_raw || dealsState.totalRaw;

    const status = document.getElementById("deals-status-line");
    if (status) {
      status.textContent = `Mostrando ${dealsState.items.length} de ${dealsState.totalFiltered} ofertas filtradas (${dealsState.totalRaw} escaneadas).`;
    }
    _renderKPIBar();
    _renderCards();
    _renderPagination();
  }

  function _renderKPIBar() {
    const bar = document.getElementById("deals-kpi-bar");
    if (!bar) return;
    if (dealsState.totalRaw === 0) {
      bar.style.display = "none";
      return;
    }
    const k = dealsState.kpis;
    bar.style.display = "flex";
    const pills = [
      { id: "all", label: `📦 Todos (${k.all})` },
      { id: "atl", label: `⭐ Récords ATL (${k.atl})` },
      { id: "free", label: `🎁 100% Gratis (${k.free})` },
      { id: "sub", label: `🟢 Suscripción (${k.sub})` },
      { id: "cards", label: `🃏 Cromos (${k.cards})` },
      { id: "coop", label: `🤝 Co-op / Multi (${k.coop})` },
    ];
    bar.innerHTML = pills.map(pi => `
      <button type="button" class="kpi-filter-pill ${dealsState.kpiFilter === pi.id ? "active" : ""}" data-kpi="${pi.id}">
        ${pi.label}
      </button>
    `).join("") + `<span class="kpi-avg-label">💰 Promedio: ${ui().escapeHtml(ui().formatPrice(k.avg_usd || 0))}</span>`;

    bar.querySelectorAll(".kpi-filter-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.kpi;
        dealsState.kpiFilter = (dealsState.kpiFilter === mode && mode !== "all") ? "all" : mode;
        dealsState.page = 1;
        queryAndRender();
      });
    });
  }

  function _renderCards() {
    const area = document.getElementById("deals-results-area");
    if (!area) return;
    if (!dealsState.items.length) {
      area.innerHTML = `<div class="glass-card empty-state">Ningún juego coincide con los filtros actuales. Probá relajar algún criterio.</div>`;
      return;
    }
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;

    area.innerHTML = `
      <div class="deals-container ${_viewClass(dealsState.vista)}">
        ${dealsState.items.map(it => {
          const isFree = it.descuento === 100 || (it.precio_oferta_usd === 0 && it.descuento > 0);
          const priceNow = isFree ? "GRATIS" : fmt(it.precio_oferta_usd);
          const priceOld = it.precio_normal_usd > it.precio_oferta_usd ? fmt(it.precio_normal_usd) : "";
          const imgUrl = dealsState.vista === "Compacta" ? it.thumb_url : (it.header_url || it.thumb_url);

          return `
            <article class="deal-card-item ${it.es_atl ? "is-atl" : ""}" data-appid="${esc(it.appid)}">
              <img class="deal-cover" src="${esc(imgUrl)}" alt="${esc(it.titulo)}" loading="lazy" onerror="this.src='${esc(it.thumb_url)}'" />
              <div class="deal-body">
                <div class="deal-badges-row">
                  ${it.es_atl ? `<span class="d-badge atl">⭐ RÉCORD ATL</span>` : ""}
                  ${isFree ? `<span class="d-badge free">🎁 100% GRATIS</span>` : ""}
                  ${it.es_bug ? `<span class="d-badge bug">⚡ POSIBLE BUG</span>` : ""}
                  ${it.es_deck ? `<span class="d-badge deck">🟢 Deck</span>` : ""}
                  ${it.tiene_cromos ? `<span class="d-badge">🃏 Cromos</span>` : ""}
                  ${it.suscripcion ? `<span class="d-badge" style="color:${esc(it.suscripcion.color)}">${esc(it.suscripcion.label)}</span>` : ""}
                </div>
                <div class="deal-title" title="${esc(it.titulo)}">${esc(it.titulo)}</div>
                <div class="deal-sub">
                  ${esc(it.modalidad)} · ⭐ ${esc(it.rating)}% · ${esc(it.termometro?.label || "")}
                </div>
              </div>
              <div class="deal-right">
                <div class="deal-price-pill">
                  ${it.descuento > 0 ? `<span class="deal-pct">-${it.descuento}%</span>` : ""}
                  <div class="deal-prices">
                    ${priceOld ? `<span class="deal-old">${esc(priceOld)}</span>` : ""}
                    <span class="deal-now">${esc(priceNow)}</span>
                  </div>
                </div>
                <div class="deal-actions">
                  <button type="button" class="act-btn btn-deal-vs" data-appid="${esc(it.appid)}" title="Comparar Cara a Cara (Versus)">⚔️</button>
                  <button type="button" class="act-btn ${it.in_cart ? "active" : ""} btn-deal-cart" data-appid="${esc(it.appid)}" title="Sumar / Quitar del Changuito">🛒</button>
                  <button type="button" class="act-btn ${it.in_watchlist ? "active" : ""} btn-deal-wl" data-appid="${esc(it.appid)}" title="Guardar / Quitar de Watchlist">⭐</button>
                  <button type="button" class="act-btn btn-deal-web" data-appid="${esc(it.appid)}" title="Abrir Steam Web (-21% Impuestos)">🌐</button>
                </div>
              </div>
            </article>
          `;
        }).join("")}
      </div>
    `;

    area.querySelectorAll(".btn-deal-cart").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const item = _findItem(btn.dataset.appid);
        if (!item) return;
        const res = await window.pywebview.api.toggle_cart_item(item);
        if (res?.ok) {
          item.in_cart = res.in_cart;
          btn.classList.toggle("active", res.in_cart);
          ui().renderCommandCenter(res.command_center);
          ui().showToast(res.in_cart ? `🛒 "${item.titulo}" sumado al changuito` : `🛒 "${item.titulo}" quitado`);
        }
      });
    });

    area.querySelectorAll(".btn-deal-wl").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const item = _findItem(btn.dataset.appid);
        if (!item) return;
        const res = await window.pywebview.api.toggle_watchlist_item(item);
        if (res?.ok) {
          item.in_watchlist = res.in_watchlist;
          btn.classList.toggle("active", res.in_watchlist);
          ui().renderCommandCenter(res.command_center);
          ui().showToast(res.in_watchlist ? `⭐ "${item.titulo}" guardado en Watchlist` : `⭐ "${item.titulo}" quitado`);
        }
      });
    });

    area.querySelectorAll(".btn-deal-vs").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const item = _findItem(btn.dataset.appid);
        if (item && window.FichaView) window.FichaView.selectForVersus(item);
      });
    });

    area.querySelectorAll(".btn-deal-web").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        window.pywebview.api.open_external_url(`https://store.steampowered.com/app/${btn.dataset.appid}`);
      });
    });

    area.querySelectorAll(".deal-card-item").forEach(card => {
      card.addEventListener("click", () => {
        const item = _findItem(card.dataset.appid);
        if (item && window.FichaView) window.FichaView.openFicha(item.appid, item);
      });
      card.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        const item = _findItem(card.dataset.appid);
        if (item) _openContextMenu(e.clientX, e.clientY, item);
      });
    });
  }

  function _openContextMenu(x, y, item) {
    const menu = document.getElementById("deal-context-menu");
    if (!menu) return;
    const esc = ui().escapeHtml;
    const actions = [
      { id: "ficha", label: "🖥️ Ver Ficha Técnica" },
      { id: "vs", label: "⚔️ Comparar Cara a Cara (Versus)" },
      { id: "web", label: "🌐 Abrir en Steam Web (-21% Impuestos)" },
      { id: "steam", label: "🚀 Abrir en App de Steam" },
      { id: "cart", label: item.in_cart ? "🛒 Quitar del Changuito" : "🛒 Sumar al Changuito" },
      { id: "wl", label: item.in_watchlist ? "⭐ Quitar de Watchlist" : "⭐ Guardar en Watchlist" },
      { id: "share", label: "📋 Copiar Ficha (WhatsApp / Discord)" },
      { id: "discord", label: "📢 Publicar en Discord Webhook" },
      { id: "steamdb", label: "🌍 Comparar Precios (SteamDB)" },
      { id: "hltb", label: "⏳ Ver Duración (HowLongToBeat)" },
      { id: "yt", label: "▶ Buscar Gameplay en YouTube" },
      { id: "bl", label: "🚫 Ignorar Juego (Blacklist)", danger: true },
    ];

    menu.innerHTML = actions.map(a => `
      <button type="button" class="ctx-item ${a.danger ? "danger" : ""}" data-act="${a.id}">${esc(a.label)}</button>
    `).join("");

    const left = Math.min(x, window.innerWidth - 260);
    const top = Math.min(y, window.innerHeight - 360);
    menu.style.left = `${Math.max(8, left)}px`;
    menu.style.top = `${Math.max(8, top)}px`;
    menu.classList.add("open");

    menu.querySelectorAll(".ctx-item").forEach(btn => {
      btn.addEventListener("click", async () => {
        menu.classList.remove("open");
        const act = btn.dataset.act;
        if (act === "ficha") {
          if (window.FichaView) window.FichaView.openFicha(item.appid, item);
        } else if (act === "vs") {
          if (window.FichaView) window.FichaView.selectForVersus(item);
        } else if (act === "web") {
          window.pywebview.api.open_external_url(`https://store.steampowered.com/app/${item.appid}`);
        } else if (act === "steam") {
          window.pywebview.api.open_external_url(`steam://store/${item.appid}`);
        } else if (act === "steamdb") {
          window.pywebview.api.open_external_url(`https://steamdb.info/app/${item.appid}/`);
        } else if (act === "hltb") {
          window.pywebview.api.open_external_url(`https://howlongtobeat.com/?q=${encodeURIComponent(item.titulo)}`);
        } else if (act === "yt") {
          window.pywebview.api.open_external_url(`https://www.youtube.com/results?search_query=${encodeURIComponent(item.titulo + " gameplay")}`);
        } else if (act === "cart") {
          const r = await window.pywebview.api.toggle_cart_item(item);
          if (r?.ok) { ui().renderCommandCenter(r.command_center); queryAndRender(); }
        } else if (act === "wl") {
          const r = await window.pywebview.api.toggle_watchlist_item(item);
          if (r?.ok) { ui().renderCommandCenter(r.command_center); queryAndRender(); }
        } else if (act === "share") {
          const r = await window.pywebview.api.get_share_text(item);
          if (r?.ok && navigator.clipboard) {
            await navigator.clipboard.writeText(r.text);
            ui().showToast("📋 Ficha copiada al portapapeles");
          }
        } else if (act === "discord") {
          const r = await window.pywebview.api.send_discord_webhook(item);
          ui().showToast(r?.ok ? "📢 Oferta publicada en Discord" : `⚠️ ${r?.error || "Error Webhook"}`);
        } else if (act === "bl") {
          const r = await window.pywebview.api.add_to_blacklist(item.appid, item.titulo);
          if (r?.ok) {
            ui().showToast(`🚫 "${item.titulo}" añadido a ignorados`);
            queryAndRender();
          }
        }
      });
    });
  }

  function _renderPagination() {
    const bar = document.getElementById("deals-pagination");
    if (!bar) return;
    if (dealsState.totalRaw === 0) {
      bar.style.display = "none";
      return;
    }
    bar.style.display = "flex";
    document.getElementById("deals-pag-summary").textContent =
      `Página ${dealsState.page} de ${dealsState.totalPages} · ${dealsState.totalFiltered} resultados`;
    document.getElementById("deals-pag-lbl").textContent = `Pág ${dealsState.page} / ${dealsState.totalPages}`;
    document.getElementById("btn-deals-prev").disabled = dealsState.page <= 1;
    document.getElementById("btn-deals-next").disabled = dealsState.page >= dealsState.totalPages;
  }

  window.DealsView = {
    mount,
    scanOrSearch,
    getLoadedItems: () => dealsState.items,
    refresh: () => queryAndRender(),
    refreshPrices: () => {
      _renderKPIBar();
      _renderCards();
    },
  };
})();
