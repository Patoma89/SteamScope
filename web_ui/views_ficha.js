/* =====================================================================
   SteamScope 3.0 NEXT — Ficha Técnica Pro, Lightbox HD & Comparador Versus
   ===================================================================== */

(function () {
  const ui = () => window.SteamScopeUI;

  const lbState = {
    wired: false,
    screenshots: [],
    index: 0,
    zoom: 1,
    panX: 0,
    panY: 0,
    dragging: false,
    startX: 0,
    startY: 0,
  };

  const versusState = {
    slotA: null,
    slotB: null,
    lastResult: null,
  };

  function _renderPriceHistorySVG(history, atlPrice) {
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    if (!history || history.length < 2) {
      return `<div class="empty-state" style="padding:14px">Historial local insuficiente aún.${atlPrice > 0 ? ` Mínimo histórico global: <strong>$${Number(atlPrice).toFixed(2)} USD</strong>.` : ""}</div>`;
    }

    const W = 760;
    const H = 120;
    const padX = 24;
    const padY = 16;
    const prices = history.map(p => Number(p.precio_usd || 0));
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices, minP + 0.5);
    const span = maxP - minP || 1;

    const coords = history.map((pt, i) => {
      const x = padX + (i / (history.length - 1)) * (W - padX * 2);
      const y = H - padY - ((Number(pt.precio_usd || 0) - minP) / span) * (H - padY * 2);
      return { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)), pt };
    });

    const linePts = coords.map(c => `${c.x},${c.y}`).join(" ");
    const areaPts = `${coords[0].x},${H - padY} ${linePts} ${coords[coords.length - 1].x},${H - padY}`;

    return `
      <svg class="chart-svg-box" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <defs>
          <linearGradient id="ssChartGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.35" />
            <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.02" />
          </linearGradient>
        </defs>
        <polygon points="${areaPts}" fill="url(#ssChartGrad)" />
        <polyline fill="none" stroke="var(--accent)" stroke-width="2.5" points="${linePts}" />
        ${coords.map(c => `
          <circle cx="${c.x}" cy="${c.y}" r="4" fill="var(--accent)">
            <title>${esc(c.pt.fecha)}: ${esc(fmt(c.pt.precio_usd))} ($${Number(c.pt.precio_usd).toFixed(2)} USD)</title>
          </circle>
        `).join("")}
      </svg>
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--subtext)">
        <span>Mínimo en registro: <strong>$${minP.toFixed(2)} USD</strong></span>
        ${atlPrice > 0 ? `<span>Mínimo histórico global: <strong>$${Number(atlPrice).toFixed(2)} USD</strong></span>` : ""}
        <span>Máximo en registro: <strong>$${maxP.toFixed(2)} USD</strong></span>
      </div>
    `;
  }

  async function openFicha(appid, itemRef = null) {
    const esc = ui().escapeHtml;
    const fmt = ui().formatPrice;
    const modalTitle = document.getElementById("ficha-modal-title");
    const body = document.getElementById("ficha-modal-body");
    if (!body) return;

    if (modalTitle) modalTitle.textContent = `🖥️ FICHA TÉCNICA — ${itemRef?.titulo || "Cargando..."}`;
    body.innerHTML = `<div class="skeleton-list">${Array(4).fill(`<div class="skeleton-card"></div>`).join("")}</div>`;
    ui().openModal("modal-ficha");

    document.getElementById("btn-close-ficha").onclick = () => ui().closeModal("modal-ficha");

    const data = await window.pywebview.api.get_game_details(String(appid), itemRef);
    if (!data?.ok) {
      body.innerHTML = `<div class="empty-state">⚠️ ${esc(data?.error || "No se pudo cargar la ficha técnica.")}</div>`;
      return;
    }

    if (modalTitle) modalTitle.textContent = `🖥️ ${data.titulo}`;
    const priceMain = data.is_free ? "GRATIS" : fmt(data.final_usd);
    const priceNormal = data.normal_usd > data.final_usd ? fmt(data.normal_usd) : "";
    const mcScore = data.metacritic?.score;

    const dealRef = itemRef || {
      appid: data.appid,
      titulo: data.titulo,
      precio_oferta_usd: data.final_usd,
      precio_normal_usd: data.normal_usd,
      descuento: data.discount_pct,
      rating: mcScore || "N/A",
      es_atl: data.atl?.is_atl_now,
      link: data.links.steam_web,
    };

    body.innerHTML = `
      <div class="ficha-top-grid">
        <img class="ficha-poster" src="${esc(data.poster_url)}" alt="${esc(data.titulo)}" onerror="this.src='${esc(data.header_image)}'" />
        <div class="ficha-head-info">
          <div class="deal-badges-row">
            ${data.atl?.is_atl_now ? `<span class="d-badge atl">⭐ MÍNIMO HISTÓRICO (ATL)</span>` : ""}
            ${data.is_free ? `<span class="d-badge free">🎁 GRATIS</span>` : ""}
            ${data.suscripcion ? `<span class="d-badge" style="color:${esc(data.suscripcion.color)}">${esc(data.suscripcion.label)}</span>` : ""}
            <span class="d-badge deck">🐧 ProtonDB: ${esc(data.protondb)}</span>
            ${mcScore ? `<span class="d-badge">🏆 Metacritic: ${esc(mcScore)}</span>` : ""}
            <span class="d-badge">💾 Disco: ${esc(data.disk_space)}</span>
          </div>

          <div class="ficha-title">${esc(data.titulo)}</div>
          <div class="ficha-meta-row">
            <span>🏢 ${esc((data.developers || []).join(", ") || "N/D")}</span>
            <span>📅 ${esc(data.release_date)}</span>
            <span>🏷️ ${esc((data.genres || []).slice(0, 4).join(" · ") || "Steam")}</span>
          </div>

          <p class="ficha-desc">${esc(data.short_description)}</p>

          <div class="ficha-stat-cards">
            <div class="ficha-stat">
              <span>Precio Actual</span>
              <strong>${esc(priceMain)} ${data.discount_pct > 0 ? `(-${data.discount_pct}%)` : ""}</strong>
            </div>
            <div class="ficha-stat">
              <span>Precio Lista</span>
              <strong>${esc(priceNormal || priceMain)}</strong>
            </div>
            <div class="ficha-stat">
              <span>Mínimo ATL</span>
              <strong>${data.atl?.price_usd > 0 ? `$${Number(data.atl.price_usd).toFixed(2)} USD` : "N/D"}</strong>
            </div>
            <div class="ficha-stat">
              <span>Reseñas</span>
              <strong>${data.reviews ? esc(data.reviews.summary) : "N/D"}</strong>
            </div>
          </div>

          <div class="regional-banner ${esc(data.regional?.status || "unknown")}">
            ${esc(data.regional?.label || "")}
            ${data.regional?.us_usd > 0 ? ` · EE.UU.: $${Number(data.regional.us_usd).toFixed(2)} vs AR: $${Number(data.regional.ar_usd).toFixed(2)} USD` : ""}
          </div>

          <div class="regional-banner" style="border-color:${esc(data.termometro?.color || "var(--border)")}">
            <strong style="color:${esc(data.termometro?.color || "var(--accent)")}">${esc(data.termometro?.label || "")}</strong>
            — ${esc(data.termometro?.desc || "")}
          </div>
        </div>
      </div>

      ${(data.screenshots || []).length ? `
        <div class="ficha-section-card">
          <div class="ficha-section-title">🖼️ Galería HD (${data.screenshots.length} capturas · clic para ampliar)</div>
          <div class="screens-strip">
            ${data.screenshots.map((s, idx) => `
              <img class="screen-thumb" src="${esc(s.thumb)}" data-sidx="${idx}" alt="Captura ${idx + 1}" loading="lazy" />
            `).join("")}
          </div>
        </div>
      ` : ""}

      <div class="ficha-section-card">
        <div class="ficha-section-title">📈 Historial de Precios</div>
        ${_renderPriceHistorySVG(data.price_history, data.atl?.price_usd || 0)}
      </div>

      ${(data.packages || []).length ? `
        <div class="ficha-section-card">
          <div class="ficha-section-title">📦 Ediciones y Bundles Detectados</div>
          <div class="cc-list" style="max-height:160px">
            ${data.packages.map(pk => `
              <div class="cc-row">
                <span class="cc-row-title">${esc(pk.name)}</span>
                <span class="cc-price-tag">${pk.discount_pct > 0 ? `-${pk.discount_pct}% · ` : ""}${esc(fmt(pk.price_usd))}</span>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}

      <div class="ficha-section-card">
        <div class="ficha-section-title">📝 Notas Personales Privadas</div>
        <textarea class="note-textarea" id="ficha-note-input" placeholder="Escribí tus apuntes sobre este juego (quedan guardados localmente en SQLite y sincronizados con Watchlist)...">${esc(data.personal_note || "")}</textarea>
        <div style="display:flex;justify-content:flex-end">
          <button type="button" class="btn-primary-accent" id="btn-ficha-save-note">💾 Guardar Nota</button>
        </div>
      </div>

      <div class="ficha-two-col">
        <div class="ficha-section-card">
          <div class="ficha-section-title">💻 Requisitos Mínimos</div>
          <pre class="req-pre">${esc(data.pc_requirements?.minimum || "No especificado.")}</pre>
        </div>
        <div class="ficha-section-card">
          <div class="ficha-section-title">🚀 Requisitos Recomendados</div>
          <pre class="req-pre">${esc(data.pc_requirements?.recommended || "No especificado.")}</pre>
        </div>
      </div>

      <div class="ficha-bottom-bar">
        <button type="button" class="btn-primary-accent" id="btn-ficha-cart">${data.in_cart ? "🛒 Quitar del Changuito" : "🛒 Sumar al Changuito"}</button>
        <button type="button" class="btn-ghost" id="btn-ficha-wl">${data.in_watchlist ? "⭐ En Watchlist" : "⭐ Guardar Watchlist"}</button>
        <button type="button" class="btn-ghost" id="btn-ficha-vs">⚔️ Fijar para Versus</button>
        <button type="button" class="btn-ghost" id="btn-ficha-share">📋 Compartir</button>
        <button type="button" class="btn-ghost" id="btn-ficha-web">🌐 Steam Web (-21%)</button>
        <button type="button" class="btn-ghost" id="btn-ficha-steam">🚀 App Steam</button>
        <button type="button" class="btn-ghost" id="btn-ficha-db">🌍 SteamDB</button>
        <button type="button" class="btn-ghost" id="btn-ficha-hltb">⏳ HLTB</button>
        <button type="button" class="btn-ghost" id="btn-ficha-yt">▶ Trailer</button>
        <button type="button" class="btn-danger" id="btn-ficha-close-btm" style="margin-left:auto">Cerrar</button>
      </div>
    `;

    body.querySelectorAll(".screen-thumb").forEach(img => {
      img.addEventListener("click", () => openLightbox(data.screenshots, Number(img.dataset.sidx)));
    });

    document.getElementById("btn-ficha-save-note")?.addEventListener("click", async () => {
      const txt = document.getElementById("ficha-note-input")?.value || "";
      const r = await window.pywebview.api.save_game_note(data.appid, txt);
      if (r?.ok) {
        ui().renderCommandCenter(r.command_center);
        ui().showToast("📝 Nota personal guardada y sincronizada");
      }
    });

    document.getElementById("btn-ficha-cart")?.addEventListener("click", async (e) => {
      const r = await window.pywebview.api.toggle_cart_item(dealRef);
      if (r?.ok) {
        e.target.textContent = r.in_cart ? "🛒 Quitar del Changuito" : "🛒 Sumar al Changuito";
        ui().renderCommandCenter(r.command_center);
        if (window.DealsView) window.DealsView.refresh();
      }
    });

    document.getElementById("btn-ficha-wl")?.addEventListener("click", async (e) => {
      const r = await window.pywebview.api.toggle_watchlist_item(dealRef);
      if (r?.ok) {
        e.target.textContent = r.in_watchlist ? "⭐ En Watchlist" : "⭐ Guardar Watchlist";
        ui().renderCommandCenter(r.command_center);
        if (window.DealsView) window.DealsView.refresh();
      }
    });

    document.getElementById("btn-ficha-vs")?.addEventListener("click", () => {
      ui().closeModal("modal-ficha");
      selectForVersus(dealRef);
    });

    document.getElementById("btn-ficha-share")?.addEventListener("click", async () => {
      const r = await window.pywebview.api.get_share_text(dealRef);
      if (r?.ok && navigator.clipboard) {
        await navigator.clipboard.writeText(r.text);
        ui().showToast("📋 Ficha copiada para WhatsApp / Discord");
      }
    });

    document.getElementById("btn-ficha-web")?.addEventListener("click", () => window.pywebview.api.open_external_url(data.links.steam_web));
    document.getElementById("btn-ficha-steam")?.addEventListener("click", () => window.pywebview.api.open_external_url(data.links.steam_desktop));
    document.getElementById("btn-ficha-db")?.addEventListener("click", () => window.pywebview.api.open_external_url(data.links.steamdb));
    document.getElementById("btn-ficha-hltb")?.addEventListener("click", () => window.pywebview.api.open_external_url(data.links.hltb));
    document.getElementById("btn-ficha-yt")?.addEventListener("click", () => window.pywebview.api.open_external_url(data.links.youtube));
    document.getElementById("btn-ficha-close-btm")?.addEventListener("click", () => ui().closeModal("modal-ficha"));
  }

  /* ==================== LIGHTBOX TÁCTICO HD ==================== */
  function _wireLightboxOnce() {
    if (lbState.wired) return;
    lbState.wired = true;

    const stage = document.getElementById("lightbox-stage");
    const modal = document.getElementById("lightbox-modal");

    document.getElementById("btn-close-lightbox")?.addEventListener("click", () => ui().closeModal("modal-lightbox"));
    document.getElementById("lb-prev")?.addEventListener("click", () => _stepLightbox(-1));
    document.getElementById("lb-next")?.addEventListener("click", () => _stepLightbox(1));
    document.getElementById("lb-zoom-in")?.addEventListener("click", () => _setZoom(lbState.zoom + 0.25));
    document.getElementById("lb-zoom-out")?.addEventListener("click", () => _setZoom(lbState.zoom - 0.25));
    document.getElementById("lb-zoom-reset")?.addEventListener("click", _resetZoom);
    document.getElementById("lb-fullscreen")?.addEventListener("click", () => {
      if (!document.fullscreenElement && modal?.requestFullscreen) {
        modal.requestFullscreen().catch(() => {});
      } else if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    });

    stage?.addEventListener("wheel", (e) => {
      e.preventDefault();
      _setZoom(lbState.zoom + (e.deltaY < 0 ? 0.2 : -0.2));
    }, { passive: false });

    stage?.addEventListener("mousedown", (e) => {
      lbState.dragging = true;
      lbState.startX = e.clientX - lbState.panX;
      lbState.startY = e.clientY - lbState.panY;
    });

    window.addEventListener("mousemove", (e) => {
      if (!lbState.dragging) return;
      lbState.panX = e.clientX - lbState.startX;
      lbState.panY = e.clientY - lbState.startY;
      _applyTransform();
    });

    window.addEventListener("mouseup", () => { lbState.dragging = false; });

    document.addEventListener("keydown", (e) => {
      const open = document.getElementById("modal-lightbox")?.classList.contains("open");
      if (!open) return;
      if (e.key === "ArrowLeft") _stepLightbox(-1);
      else if (e.key === "ArrowRight") _stepLightbox(1);
      else if (e.key === "F11") {
        e.preventDefault();
        document.getElementById("lb-fullscreen")?.click();
      }
    });
  }

  function _applyTransform() {
    const img = document.getElementById("lightbox-img");
    const lbl = document.getElementById("lb-zoom-lbl");
    if (img) img.style.transform = `translate(${lbState.panX}px, ${lbState.panY}px) scale(${lbState.zoom})`;
    if (lbl) lbl.textContent = `${Math.round(lbState.zoom * 100)}%`;
  }

  function _setZoom(next) {
    lbState.zoom = Math.max(0.5, Math.min(3.5, next));
    _applyTransform();
  }

  function _resetZoom() {
    lbState.zoom = 1;
    lbState.panX = 0;
    lbState.panY = 0;
    _applyTransform();
  }

  function _stepLightbox(delta) {
    if (!lbState.screenshots.length) return;
    lbState.index = (lbState.index + delta + lbState.screenshots.length) % lbState.screenshots.length;
    _renderLightboxFrame();
  }

  function _renderLightboxFrame() {
    const item = lbState.screenshots[lbState.index];
    const img = document.getElementById("lightbox-img");
    const cnt = document.getElementById("lb-counter");
    if (img && item) img.src = item.full || item.thumb;
    if (cnt) cnt.textContent = `${lbState.index + 1} / ${lbState.screenshots.length}`;
    _resetZoom();
  }

  function openLightbox(screenshots, startIndex = 0) {
    if (!screenshots || !screenshots.length) return;
    _wireLightboxOnce();
    lbState.screenshots = screenshots;
    lbState.index = Math.max(0, Math.min(screenshots.length - 1, startIndex));
    _renderLightboxFrame();
    ui().openModal("modal-lightbox");
  }

  /* ==================== COMPARADOR CARA A CARA (VERSUS) ==================== */
  function selectForVersus(item) {
    const aid = String(item.appid || "");
    if (!aid) return;

    if (!versusState.slotA || String(versusState.slotA.appid) === aid) {
      versusState.slotA = item;
      ui().showToast(`⚔️ "${item.titulo}" fijado como Juego A. Elegí el segundo juego.`);
      return;
    }

    versusState.slotB = item;
    ui().navigateTo("versus");
  }

  async function mountVersus(container) {
    const esc = ui().escapeHtml;
    const dealsPool = window.DealsView ? window.DealsView.getLoadedItems() : [];
    const wlPool = (ui().getState()?.cc?.watchlist?.items || []).map(w => ({ appid: w.appid, titulo: w.titulo }));
    const mergedMap = new Map();
    [...dealsPool, ...wlPool].forEach(it => {
      if (it?.appid) mergedMap.set(String(it.appid), it);
    });
    const candidates = Array.from(mergedMap.values());

    const valA = versusState.slotA?.appid || "";
    const valB = versusState.slotB?.appid || "";

    container.innerHTML = `
      <div class="deals-header">
        <div>
          <h1 class="deals-title">COMPARADOR <span>CARA A CARA (VERSUS)</span></h1>
          <div style="font-size:12px;color:var(--subtext)">Enfrentá dos títulos de Steam en paralelo y descubrí cuál conviene más hoy.</div>
        </div>
      </div>

      <div class="glass-card versus-picker">
        <div class="filter-field">
          <label>Juego A (AppID o Selección)</label>
          <div style="display:flex;gap:6px">
            <input type="text" class="t-input" id="vs-appid-a" placeholder="Ej: 1091500" value="${esc(valA)}" style="width:130px" />
            <select class="t-select" id="vs-pick-a" style="flex:1">
              <option value="">Elegir de ofertas / watchlist...</option>
              ${candidates.map(c => `<option value="${esc(c.appid)}" ${String(c.appid) === String(valA) ? "selected" : ""}>${esc(c.titulo)} (${esc(c.appid)})</option>`).join("")}
            </select>
          </div>
        </div>

        <button type="button" class="btn-primary-accent" id="btn-run-versus">⚔️ Comparar</button>

        <div class="filter-field">
          <label>Juego B (AppID o Selección)</label>
          <div style="display:flex;gap:6px">
            <input type="text" class="t-input" id="vs-appid-b" placeholder="Ej: 1245620" value="${esc(valB)}" style="width:130px" />
            <select class="t-select" id="vs-pick-b" style="flex:1">
              <option value="">Elegir de ofertas / watchlist...</option>
              ${candidates.map(c => `<option value="${esc(c.appid)}" ${String(c.appid) === String(valB) ? "selected" : ""}>${esc(c.titulo)} (${esc(c.appid)})</option>`).join("")}
            </select>
          </div>
        </div>
      </div>

      <div id="versus-results-area"></div>
    `;

    document.getElementById("vs-pick-a")?.addEventListener("change", (e) => {
      if (e.target.value) document.getElementById("vs-appid-a").value = e.target.value;
    });
    document.getElementById("vs-pick-b")?.addEventListener("change", (e) => {
      if (e.target.value) document.getElementById("vs-appid-b").value = e.target.value;
    });

    document.getElementById("btn-run-versus")?.addEventListener("click", _executeVersus);

    if (valA && valB) {
      await _executeVersus();
    } else if (versusState.lastResult) {
      _renderVersusResult(versusState.lastResult);
    } else {
      document.getElementById("versus-results-area").innerHTML = `
        <div class="glass-card empty-state">Seleccioná dos juegos (o usá el botón ⚔️ en cualquier tarjeta de Ofertas) para compararlos.</div>
      `;
    }
  }

  async function _executeVersus() {
    const aId = document.getElementById("vs-appid-a")?.value.trim();
    const bId = document.getElementById("vs-appid-b")?.value.trim();
    const area = document.getElementById("versus-results-area");
    if (!aId || !bId) {
      ui().showToast("⚠️ Indicá los dos AppIDs para comparar");
      return;
    }
    area.innerHTML = `<div class="skeleton-list"><div class="skeleton-card"></div><div class="skeleton-card"></div></div>`;
    const res = await window.pywebview.api.compare_games_versus(aId, bId);
    if (!res?.ok) {
      area.innerHTML = `<div class="glass-card empty-state">⚠️ ${ui().escapeHtml(res?.error || "Error al comparar")}</div>`;
      return;
    }
    versusState.lastResult = res;
    _renderVersusResult(res);
  }

  function _renderVersusResult(res) {
    const area = document.getElementById("versus-results-area");
    if (!area) return;
    const esc = ui().escapeHtml;
    const a = res.game_a;
    const b = res.game_b;

    const bannerTxt = res.winner === "A"
      ? `🏆 Ganador: ${a.titulo} (${res.score_a} vs ${res.score_b})`
      : (res.winner === "B"
        ? `🏆 Ganador: ${b.titulo} (${res.score_b} vs ${res.score_a})`
        : `🤝 Empate técnico (${res.score_a} vs ${res.score_b})`);

    area.innerHTML = `
      <div class="regional-banner better" style="text-align:center;margin-bottom:14px">${esc(bannerTxt)}</div>

      <div class="versus-grid">
        <div class="glass-card versus-card ${res.winner === "A" ? "winner" : ""}">
          <img class="versus-cover" src="${esc(a.header_image)}" alt="${esc(a.titulo)}" />
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
            <strong>${res.winner === "A" ? "🏆 " : ""}${esc(a.titulo)}</strong>
            <button type="button" class="btn-ghost" id="btn-vs-ficha-a">Ver Ficha</button>
          </div>
        </div>
        <div class="glass-card versus-card ${res.winner === "B" ? "winner" : ""}">
          <img class="versus-cover" src="${esc(b.header_image)}" alt="${esc(b.titulo)}" />
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
            <strong>${res.winner === "B" ? "🏆 " : ""}${esc(b.titulo)}</strong>
            <button type="button" class="btn-ghost" id="btn-vs-ficha-b">Ver Ficha</button>
          </div>
        </div>
      </div>

      <div class="glass-card" style="overflow:hidden">
        <table class="versus-table">
          <thead>
            <tr>
              <th>Métrica</th>
              <th>${esc(a.titulo)}</th>
              <th>${esc(b.titulo)}</th>
            </tr>
          </thead>
          <tbody>
            ${(res.rows || []).map(r => `
              <tr>
                <td>${esc(r.metric)}</td>
                <td class="${r.winner === "A" ? "versus-win-cell" : ""}">${r.winner === "A" ? "🏆 " : ""}${esc(r.val_a)}</td>
                <td class="${r.winner === "B" ? "versus-win-cell" : ""}">${r.winner === "B" ? "🏆 " : ""}${esc(r.val_b)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;

    document.getElementById("btn-vs-ficha-a")?.addEventListener("click", () => openFicha(a.appid));
    document.getElementById("btn-vs-ficha-b")?.addEventListener("click", () => openFicha(b.appid));
  }

  window.FichaView = {
    openFicha,
    openLightbox,
    mountVersus,
    selectForVersus,
  };
})();
