"""
Componente de Tarjeta de Juego para SteamScope (SRP / UI Modular).
Encapsula la creación visual, eventos de hover, badges (Récord Histórico, Tags, DLC, etc.)
y acciones de compra/watchlist en vistas Normal, Compacta y Grilla.
"""

import webbrowser
import tkinter as tk
import customtkinter as ctk

from core.pricing import evaluar_termometro_compra, detectar_suscripcion, calcular_tiempo_restante
from ui.modals import DialogoFichaJuego, texto_contraste_acento, texto_contraste_color


def _bind_mousewheel(widget, scrollable_target):
    """Propaga el scroll del mousepad o rueda al contenedor padre sin tirones."""
    def _on_mousewheel(event):
        try:
            scrollable_target._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    try:
        widget.bind("<MouseWheel>", _on_mousewheel)
    except Exception:
        pass

    for child in widget.winfo_children():
        _bind_mousewheel(child, scrollable_target)


def _bind_card_events(widget, card_ref, item_ref, is_wl, app, card_bg, card_hover, border_base, accent_col):
    """Enlaza el menú contextual y los efectos de iluminación al pasar el mouse."""
    es_boton_o_hijo = isinstance(widget, (ctk.CTkButton, tk.Button))
    padre = widget.master
    while padre and not es_boton_o_hijo:
        if isinstance(padre, (ctk.CTkButton, tk.Button)):
            es_boton_o_hijo = True
            break
        if padre == card_ref:
            break
        padre = getattr(padre, "master", None)

    if not es_boton_o_hijo:
        widget.bind("<Button-3>", lambda e: app._mostrar_menu_contextual(e, item_ref, is_wl))
        widget.bind("<Enter>", lambda e: card_ref.configure(fg_color=card_hover, border_color=accent_col))
        widget.bind("<Leave>", lambda e: card_ref.configure(fg_color=card_bg, border_color=border_base))
        for child in widget.winfo_children():
            _bind_card_events(child, card_ref, item_ref, is_wl, app, card_bg, card_hover, border_base, accent_col)


def crear_tarjeta_juego(app, parent, item, es_watchlist=False, vista="Normal"):
    """
    Construye y retorna el widget de tarjeta para un juego, optimizado para la vista seleccionada.
    """
    pal = app.palette
    desc = item.get("descuento", 0)
    es_atl = item.get("es_atl", False)
    appid_str = str(item.get("appid"))
    en_carrito = (appid_str in app.carrito)
    watchlist_ids = app.db.get_watchlist_ids_set()
    en_watchlist = (appid_str in watchlist_ids)
    card_bg = pal["card_bg"]
    card_hover = pal["card_hover"]
    border_base = pal["accent"] if en_carrito else pal["border"]
    
    # Resaltado dorado para Récord Histórico (ATL), o según calidad del descuento
    if es_atl:
        accent_col = "#ffd700"  # Dorado brillante para ATL
    elif desc == 100:
        accent_col = pal["accent"]
    elif desc >= 50:
        accent_col = "#ffab00"
    elif desc > 0:
        accent_col = "#38bdf8"
    else:
        accent_col = pal["border"]

    p_usd = item.get("precio_oferta_usd", 0.0)
    target_p = float(item.get("target_price") or 0.0)
    es_proximamente = (p_usd == 0 and desc < 100)

    if es_proximamente:
        p_off = "Próximamente"
        veredicto = "⏳ PRÓXIMAMENTE"
        col_term = "#8b929a"
        accent_col = pal["border"]
    else:
        p_off = app._formatear_precio(p_usd)
        veredicto, col_term, _ = evaluar_termometro_compra(desc, es_atl, p_usd)

    p_norm = app._formatear_precio(item.get("precio_normal_usd", 0.0))
    sub_badge = detectar_suscripcion(item.get("titulo", ""))

    # ================= 1. VISTA EN GRILLA =================
    if vista == "Grilla":
        card = ctk.CTkFrame(parent, corner_radius=12, fg_color=card_bg, border_width=2 if en_carrito else 1, border_color=border_base)
        lbl_img = ctk.CTkLabel(card, text="", image=app.placeholder_grid, cursor="hand2")
        lbl_img.pack(padx=10, pady=(10, 6))
        app.ui_executor.submit(app._cargar_imagen_async, item.get("appid"), item.get("thumb_url"), lbl_img, "Grilla", 180, 260, desc, es_atl)
        lbl_img.bind("<Button-1>", lambda e, i=item: DialogoFichaJuego(app, i["appid"], i["titulo"], i))
        
        t = item["titulo"]
        t = (t[:20] + "…") if len(t) > 22 else t
        lbl_tit = ctk.CTkLabel(card, text=t, font=("Segoe UI", 13, "bold"), text_color=pal["text"], cursor="hand2")
        lbl_tit.pack(padx=10, pady=(0, 2))
        lbl_tit.bind("<Button-1>", lambda e, i=item: DialogoFichaJuego(app, i["appid"], i["titulo"], i))

        time_end = item.get("time_end")
        aviso_tiempo = calcular_tiempo_restante(time_end) if time_end else None
        es_gratis = (desc == 100 or (p_usd == 0.0 and desc > 0))

        if es_gratis:
            ctk.CTkLabel(card, text=" 🎁 ¡100% GRATIS! ", fg_color="#00c853", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        elif es_atl:
            ctk.CTkLabel(card, text=" ⭐ RÉCORD HISTÓRICO ", fg_color="#ffd700", text_color="#000000", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        elif item.get("es_dlc"):
            ctk.CTkLabel(card, text=" 🧩 DLC / EXPANSIÓN ", fg_color="#8e24aa", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        elif sub_badge:
            ctk.CTkLabel(card, text=f" 🟢 {sub_badge[0]} ", fg_color=sub_badge[1], text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        elif item.get("es_deck"):
            ctk.CTkLabel(card, text=" 🟢 DECK READY ", fg_color="#107c10", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        elif target_p > 0:
            meta_cumplida = (0 < p_usd <= target_p)
            ctk.CTkLabel(card, text=f" 🎯 Meta: ${target_p:.2f} {'✓' if meta_cumplida else ''} ", fg_color="#00c853" if meta_cumplida else "#0277bd", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        elif aviso_tiempo and ("h" in aviso_tiempo or "pronto" in aviso_tiempo.lower() or aviso_tiempo in ("Termina en 1d", "Termina en 2d")):
            ctk.CTkLabel(card, text=f" ⏳ {aviso_tiempo} ", fg_color="#e65100", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(pady=(0, 3))
        else:
            ctk.CTkLabel(card, text=veredicto, font=("Consolas", 10, "bold"), text_color=col_term).pack(pady=(0, 3))

        bot_row = ctk.CTkFrame(card, fg_color=pal["price_bg"], corner_radius=8)
        bot_row.pack(fill="x", padx=10, pady=(2, 10))
        ctk.CTkLabel(bot_row, text=p_off, font=("Consolas", 13, "bold" if not es_proximamente else "normal"), text_color=accent_col if desc > 0 and not es_proximamente else pal["text"]).pack(side="left", padx=6, pady=6)

        if not es_watchlist:
            btn_star_txt = "⭐✓" if en_watchlist else "⭐"
            col_star = "#6a1b9a" if en_watchlist else "#262936"
            ctk.CTkButton(bot_row, text=btn_star_txt, width=28, height=24, corner_radius=6, fg_color=col_star, hover_color="#6a1b9a", text_color="white", command=lambda i=item: app._guardar_en_watchlist(i)).pack(side="right", padx=(2, 4), pady=4)
        else:
            ctk.CTkButton(bot_row, text="🗑", width=26, height=24, corner_radius=6, fg_color="#b71c1c", hover_color="#d32f2f", text_color="white", command=lambda a=item["appid"]: app._quitar_de_watchlist(a)).pack(side="right", padx=(2, 4), pady=4)

        if not es_proximamente:
            ctk.CTkButton(bot_row, text="🛒✓" if en_carrito else "🛒+", width=34, height=24, corner_radius=6, fg_color="#00c853" if en_carrito else "#00695c", text_color="white", font=("Segoe UI", 10, "bold"), command=lambda i=item: app._toggle_carrito_item(i)).pack(side="right", padx=2, pady=4)
        ctk.CTkButton(bot_row, text="📋", width=26, height=24, corner_radius=6, fg_color=pal["panel_bg"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"], text_color=pal["text"], font=("Segoe UI", 9), command=lambda i=item: app._copiar_oferta_al_portapapeles(i)).pack(side="right", padx=2, pady=4)

        card.bind("<Enter>", lambda e: card.configure(fg_color=card_hover, border_color=accent_col))
        card.bind("<Leave>", lambda e: card.configure(fg_color=card_bg, border_color=border_base))
        lbl_img.bind("<Button-3>", lambda e, i=item: app._mostrar_menu_contextual(e, i, es_watchlist))
        _bind_mousewheel(card, parent)
        _bind_card_events(card, card, item, es_watchlist, app, card_bg, card_hover, border_base, accent_col)
        return card

    # ================= 2. VISTAS NORMAL Y COMPACTA =================
    es_compacta = (vista == "Compacta")
    img_w, img_h = (100, 46) if es_compacta else (136, 64)
    ph_img = app.placeholder_compact if es_compacta else app.placeholder_normal

    card = ctk.CTkFrame(parent, corner_radius=10, fg_color=card_bg, border_width=2 if en_carrito else 1, border_color=border_base)
    lbl_img = ctk.CTkLabel(card, text="", image=ph_img, width=img_w, height=img_h, cursor="hand2")
    lbl_img.pack(side="left", padx=(10, 12), pady=6 if es_compacta else 8)
    app.ui_executor.submit(app._cargar_imagen_async, item.get("appid"), item.get("thumb_url"), lbl_img, vista, img_w, img_h, 0, False)
    lbl_img.bind("<Button-1>", lambda e, i=item: DialogoFichaJuego(app, i["appid"], i["titulo"], i))

    info_col = ctk.CTkFrame(card, fg_color="transparent")
    info_col.pack(side="left", fill="both", expand=True, pady=4 if es_compacta else 6)

    tit_row = ctk.CTkFrame(info_col, fg_color="transparent")
    tit_row.pack(anchor="w", fill="x")

    titulo_mostrar = item.get("titulo", "Juego")
    if len(titulo_mostrar) > 45:
        titulo_mostrar = titulo_mostrar[:42] + "..."

    lbl_tit = ctk.CTkLabel(tit_row, text=titulo_mostrar, font=("Segoe UI", 13 if es_compacta else 15, "bold"), text_color=pal["text"], cursor="hand2")
    lbl_tit.pack(side="left")
    lbl_tit.bind("<Button-1>", lambda e, i=item: DialogoFichaJuego(app, i["appid"], i["titulo"], i))

    es_gratis = (desc == 100 or (p_usd == 0.0 and desc > 0))
    time_end = item.get("time_end")
    aviso_tiempo = calcular_tiempo_restante(time_end) if time_end else None

    if es_gratis:
        ctk.CTkLabel(tit_row, text=" 🎁 ¡100% GRATIS! ", fg_color="#00c853", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    elif es_atl:
        ctk.CTkLabel(tit_row, text=" ⭐ RÉCORD HISTÓRICO ", fg_color="#ffd700", text_color="#000000", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("es_dlc"):
        ctk.CTkLabel(tit_row, text=" 🧩 DLC / EXPANSIÓN ", fg_color="#8e24aa", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("es_bug"):
        ctk.CTkLabel(tit_row, text=" 🚨 PRECIO BUG ", fg_color="#ff003c", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if sub_badge:
        ctk.CTkLabel(tit_row, text=f" 🟢 {sub_badge[0]} ", fg_color=sub_badge[1], text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("tiene_cromos"):
        ctk.CTkLabel(tit_row, text=" 🃏 CROMOS ", fg_color="#0288d1", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("es_deck"):
        ctk.CTkLabel(tit_row, text=" 🟢 DECK READY ", fg_color="#107c10", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if aviso_tiempo and ("h" in aviso_tiempo or "pronto" in aviso_tiempo.lower() or aviso_tiempo in ("Termina en 1d", "Termina en 2d")):
        ctk.CTkLabel(tit_row, text=f" ⏳ {aviso_tiempo} ", fg_color="#e65100", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("bajo_precio"):
        ctk.CTkLabel(tit_row, text=" 📉 BAJÓ ", fg_color="#ffab00", text_color="#121418", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if target_p > 0:
        meta_cumplida = (0 < p_usd <= target_p)
        ctk.CTkLabel(tit_row, text=f" 🎯 Meta: ${target_p:.2f} USD {'✓' if meta_cumplida else ''} ", fg_color="#00c853" if meta_cumplida else "#0277bd", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("custom_tag"):
        ctk.CTkLabel(tit_row, text=f" 🏷️ {item['custom_tag']} ", fg_color="#7c4dff", text_color="white", corner_radius=4, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 2))
    if item.get("personal_note"):
        nota_corta = item["personal_note"][:22] + ("..." if len(item["personal_note"]) > 22 else "")
        ctk.CTkLabel(tit_row, text=f" 📝 {nota_corta} ", fg_color="#37474f", text_color="#eceff1", corner_radius=4, font=("Segoe UI", 9, "italic")).pack(side="left", padx=(6, 2))

    meta_row = ctk.CTkFrame(info_col, fg_color="transparent")
    meta_row.pack(anchor="w", pady=(3, 0))
    mod_str = item.get('modalidad', 'General')
    gen_str = item.get('genero', 'Acción')
    rat_str = item.get('rating', 'N/A')
    ctk.CTkLabel(meta_row, text=f"🎮 {mod_str}   •   🏷️ {gen_str}   •   ⭐ {rat_str}%", font=("Segoe UI", 11), text_color=pal["subtext"]).pack(side="left")
    lbl_players = ctk.CTkLabel(meta_row, text="   •   👥 ...", font=("Segoe UI", 11, "bold"), text_color=pal["accent"])
    lbl_players.pack(side="left")
    if mod_str != "Gratis":
        app.ui_executor.submit(app._cargar_jugadores_async, item.get("appid"), lbl_players, item)
    ctk.CTkLabel(meta_row, text=f"    |    {veredicto}", font=("Consolas", 11, "bold"), text_color=col_term).pack(side="left")

    right_box = ctk.CTkFrame(card, fg_color="transparent")
    right_box.pack(side="right", padx=10, pady=6)

    price_widget = ctk.CTkFrame(right_box, fg_color=pal["price_bg"], corner_radius=8, width=155, height=42)
    price_widget.pack_propagate(False)
    price_widget.pack(side="top", anchor="e", pady=(0, 4))

    if desc > 0 and not es_proximamente:
        ctk.CTkLabel(price_widget, text=f"-{desc}%", fg_color=pal["deal_badge"], text_color=pal["deal_text"], corner_radius=6, width=48, height=34, font=("Consolas", 13, "bold")).pack(side="left", padx=(5, 6), pady=4)
        stacked_p = ctk.CTkFrame(price_widget, fg_color="transparent")
        stacked_p.pack(side="left", padx=(0, 6), pady=2)
        ctk.CTkLabel(stacked_p, text=p_norm, font=("Consolas", 9, "overstrike"), text_color=pal["subtext"], anchor="e").pack(anchor="e")
        ctk.CTkLabel(stacked_p, text=p_off, font=("Consolas", 13, "bold"), text_color=accent_col, anchor="e").pack(anchor="e")
    else:
        ctk.CTkLabel(price_widget, text=p_off, font=("Consolas", 13, "bold" if not es_proximamente else "normal"), text_color=pal["text"] if not es_proximamente else pal["subtext"], padx=10, pady=8).pack()

    act_box = ctk.CTkFrame(right_box, fg_color="transparent")
    act_box.pack(side="top", anchor="e")

    fg_btn = texto_contraste_acento(pal)
    txt_accent_2 = texto_contraste_color(pal["accent_2"])
    ctk.CTkButton(act_box, text="🚀 App", width=50, height=28, corner_radius=6, font=("Segoe UI", 11, "bold"), fg_color=pal["accent_2"], hover_color=pal["accent"], text_color=txt_accent_2, command=lambda aid=item["appid"]: webbrowser.open(f"steam://store/{aid}")).pack(side="right", padx=2)
    ctk.CTkButton(act_box, text="🌐 Web", width=52, height=28, corner_radius=6, font=("Segoe UI", 11, "bold"), fg_color=pal["card_bg"], hover_color=pal["card_hover"], border_width=1, border_color=pal["accent"], text_color=pal["accent"], command=lambda aid=item["appid"]: webbrowser.open(f"https://store.steampowered.com/app/{aid}")).pack(side="right", padx=2)
    ctk.CTkButton(act_box, text="🖥️ Ficha", width=56, height=28, corner_radius=6, font=("Segoe UI", 11, "bold"), fg_color=pal["panel_bg"], hover_color=pal["card_hover"], border_width=1, border_color=pal["border"], text_color=pal["accent"], command=lambda i=item: DialogoFichaJuego(app, i["appid"], i["titulo"], i)).pack(side="right", padx=2)
    
    es_fijado_vs = bool(app.item_comparar_a and str(app.item_comparar_a.get("appid")) == appid_str)
    ctk.CTkButton(act_box, text="⚔️✓" if es_fijado_vs else "⚔️", width=32, height=28, corner_radius=6, font=("Segoe UI", 11, "bold"), fg_color=pal["accent"] if es_fijado_vs else pal["panel_bg"], text_color=fg_btn if es_fijado_vs else pal["text"], border_width=1, border_color=pal["accent"] if es_fijado_vs else pal["border"], hover_color=pal["card_hover"], command=lambda i=item: app._seleccionar_para_comparar(i)).pack(side="right", padx=2)
    ctk.CTkButton(act_box, text="📋", width=30, height=28, corner_radius=6, font=("Segoe UI", 11), fg_color=pal["panel_bg"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"], text_color=pal["text"], command=lambda i=item: app._copiar_oferta_al_portapapeles(i)).pack(side="right", padx=2)

    if not es_proximamente:
        ctk.CTkButton(act_box, text="🛒✓" if en_carrito else "🛒+", width=38, height=28, corner_radius=6, fg_color=pal["deal_badge"] if en_carrito else pal["panel_bg"], text_color=pal["deal_text"] if en_carrito else pal["accent"], border_width=0 if en_carrito else 1, border_color=pal["accent"], hover_color=pal["card_hover"], font=("Segoe UI", 11, "bold"), command=lambda i=item: app._toggle_carrito_item(i)).pack(side="right", padx=2)

    if not es_watchlist:
        btn_star_txt = "⭐✓" if en_watchlist else "⭐"
        col_star = pal["accent"] if en_watchlist else pal["panel_bg"]
        ctk.CTkButton(act_box, text=btn_star_txt, width=32, height=28, corner_radius=6, fg_color=col_star, text_color=fg_btn if en_watchlist else pal["text"], border_width=0 if en_watchlist else 1, border_color=pal["border"], hover_color=pal["accent_2"], command=lambda i=item: app._guardar_en_watchlist(i)).pack(side="right", padx=2)
    else:
        ctk.CTkButton(act_box, text="🎯", width=30, height=28, corner_radius=6, fg_color=pal["panel_bg"], border_width=1, border_color=pal["accent"], text_color=pal["accent"], hover_color=pal["card_hover"], command=lambda i=item: app._asignar_precio_objetivo(i["appid"], i["titulo"], i.get("target_price", 0.0))).pack(side="right", padx=2)
        ctk.CTkButton(act_box, text="🗑", width=30, height=28, corner_radius=6, fg_color="#b71c1c", hover_color="#d32f2f", text_color="white", command=lambda a=item["appid"]: app._quitar_de_watchlist(a)).pack(side="right", padx=2)

    card.bind("<Enter>", lambda e: card.configure(fg_color=card_hover, border_color=accent_col))
    card.bind("<Leave>", lambda e: card.configure(fg_color=card_bg, border_color=border_base))
    card.bind("<Button-3>", lambda e, i=item: app._mostrar_menu_contextual(e, i, es_watchlist))
    _bind_mousewheel(card, parent)
    _bind_card_events(card, card, item, es_watchlist, app, card_bg, card_hover, border_base, accent_col)
    return card
