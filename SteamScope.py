import os
import time
import re
import html
import random
import threading
import concurrent.futures
import math
import webbrowser
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps, ImageFont
import tkinter as tk
import customtkinter as ctk

from core.config import (
    APP_VERSION,
    APP_NAME,
    SKIN_PALETTES,
    MODALIDADES,
    GENEROS,
    CATEGORIAS_STEAM,
    RANGOS_DESCUENTO,
    RANGOS_PRECIO,
    FILTROS_CALIDAD,
    ITEMS_POR_PAGINA,
    obtener_ruta_appdata,
    obtener_ruta_recurso,
    SoundManager,
    ConfigManager,
)
from core.database import DatabaseManager
from core.filters import (
    normalizar_texto,
    obtener_subcategorias_para,
    coincide_categoria_steam,
    filtrar_ofertas_en_memoria,
)
from core.api_client import (
    HTTP_SESSION,
    resolver_steam_id,
    SteamAPIClient,
)
from core.pricing import (
    notificar_windows,
    notificar_minimo_historico,
    es_minimo_historico_real,
    detectar_suscripcion,
    evaluar_termometro_compra,
    ordenar_ofertas,
    formatear_oferta_para_compartir,
    es_steam_deck_verificado,
)
from core.multi_store import obtener_promociones_epic
from core.cards_manager import analizar_inventario_cromos
from core.gamepad import GamepadManager
from core.notifications import notificar_oferta_enriquecida
from core.exporters import ExportService
from ui import (
    TrayManager,
    crear_tarjeta_juego,
    DialogoGraficoHistorico,
    DialogoDashboardVisual,
    texto_contraste_acento,
    texto_contraste_color,
    mostrar_alerta_skin,
    preguntar_si_no_skin,
    pedir_input_skin,
    DialogoAlertaInteractiva,
    DialogoPatchNotes,
    abrir_ventana_ofertas,
    DialogoCarrito,
    DialogoRuleta,
    DialogoActualizador,
    DialogoRedes,
    DialogoFichaJuego,
    DialogoComparadorVersus,
    DialogoConfiguracion,
    DialogoMinimizar,
    DialogoHistorialATL,
    DialogoCommandPalette,
    DialogoRadarRegalos,
    DialogoGestorCromos,
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ================= APLICACIÓN PRINCIPAL =================
class SteamScopeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"⚡ {APP_NAME} v{APP_VERSION} | by Patoma89")
        self.geometry("1220x890")
        self.minsize(1060, 740)

        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"Patoma89.SteamScope.{APP_VERSION}")
        except Exception:
            pass
        self._aplicar_icono_ventana(self)
        self.after(220, lambda: self._aplicar_icono_ventana(self))

        self.db = DatabaseManager(); self.config = ConfigManager(); self.sfx = SoundManager(self.config)
        self.api_client = SteamAPIClient()
        self.exporter = ExportService(self)
        self.cache_dir = os.path.join(obtener_ruta_appdata(), "cache")
        self.ui_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        
        self.deals_data = []; self.deals_filtradas = []; self.juegos_propios = set()
        self._ruleta_deals_pool = []; self._recargando_ruleta = False; self._reparando_titulos_wl = False
        self.biblioteca_data = self.db.get_library_cached()
        if self.biblioteca_data:
            self.juegos_propios = {str(j["appid"]) for j in self.biblioteca_data}
        self.amigo_juegos_ids = set(); self._lib_token = 0
        self.lib_pagina_actual = 1; self.lib_total_paginas = 1; self.lib_items_por_pagina = 30
        self.item_comparar_a = None
        self.carrito = self.config.datos.get("carrito_guardado", {})
        self.pagina_actual = 1; self.total_paginas = 1; self.mem_image_cache = {}
        moneda_cfg = str(self.config.datos.get("moneda", "USD"))
        if "Cripto" in moneda_cfg or "🪙" in moneda_cfg:
            self.moneda_actual = "ARS (Cripto)"
        elif "ARS" in moneda_cfg or "Tarjeta" in moneda_cfg or "💳" in moneda_cfg:
            self.moneda_actual = "ARS (Tarjeta)"
        else:
            self.moneda_actual = "USD"
        self.kpi_filter = "all"
        self.filtros_visibles = True
        self._skeleton_active = False
        self._render_token = 0; self._watch_token = 0; self.palette = SKIN_PALETTES["Oscuro"]
        
        self.placeholder_normal = self._generar_placeholder(136, 64, radius=8)
        self.placeholder_compact = self._generar_placeholder(100, 46, radius=6)
        self.placeholder_grid = self._generar_placeholder(180, 260, radius=10)

        self.current_toast = None; self.current_menu = None
        self._crear_interfaz()

        # Soporte Nativo Gamepad XInput (Steam Deck / Mando Xbox)
        self._gamepad = GamepadManager(callbacks={
            "on_dpad_left": lambda: self.after(0, self._on_gamepad_dpad_left),
            "on_dpad_right": lambda: self.after(0, self._on_gamepad_dpad_right),
            "on_bumper_left": lambda: self.after(0, self._on_gamepad_cycle_tab_left),
            "on_bumper_right": lambda: self.after(0, self._on_gamepad_cycle_tab_right),
            "on_start": lambda: self.after(0, self._abrir_command_palette),
            "on_button_x": lambda: self.after(0, self._lanzar_ruleta_sorpresa),
            "on_button_y": lambda: self.after(0, self._abrir_radar_regalos),
            "on_connection_change": lambda conn: self.after(0, lambda: self._on_gamepad_connection(conn)),
        })
        self._gamepad.start()

        self.tray = TrayManager(self, self._lanzar_modal_ofertas); self.tray.iniciar_tray()

        self.protocol("WM_DELETE_WINDOW", self.tray.salir_completo)
        self._era_maximizada = False
        self.bind("<Configure>", self._al_configurar_ventana, add="+")
        self.bind("<Unmap>", self._al_minimizar)

        self._vincular_atajos_teclado()

        threading.Thread(target=self._daemon_monitoreo_watchlist, daemon=True).start()
        threading.Thread(target=self._actualizar_juegos_propios, daemon=True).start()

        tema_guardado = self.config.datos.get("tema", "Oscuro")
        if tema_guardado not in SKIN_PALETTES: tema_guardado = "Oscuro"
        self._cambiar_tema(tema_guardado)
        if self.biblioteca_data:
            self._renderizar_biblioteca(reset_page=True)

    def _actualizar_juegos_propios(self):
        api_key = self.config.datos.get("steam_api_key", "").strip()
        steam_id = self.config.datos.get("steam_id", "").strip()
        if not steam_id:
            return
        try:
            # Si aún no hay caché local de biblioteca, aprovechamos para sincronizarla completa
            if not self.biblioteca_data:
                _, juegos = self.api_client.obtener_biblioteca_detalle(steam_id, api_key)
                if juegos:
                    self.db.save_library_batch(juegos)
                    self.biblioteca_data = self.db.get_library_cached()
                    self.juegos_propios = {str(j["appid"]) for j in self.biblioteca_data}
                    self.after(0, lambda: self._renderizar_biblioteca(reset_page=True))
                return
            # Si ya tenemos caché local, mantenemos el set rápido en memoria
            self.juegos_propios = {str(j["appid"]) for j in self.biblioteca_data}
        except Exception:
            pass

    def _al_configurar_ventana(self, event):
        if event.widget == self:
            try:
                st = self.state()
                if st == "zoomed":
                    self._era_maximizada = True
                elif st == "normal":
                    self._era_maximizada = False
            except Exception:
                pass

    def _al_minimizar(self, event):
        if event.widget == self and self.state() == "iconic":
            opcion = self.config.datos.get("minimizar_a", "Preguntar")
            if opcion == "Barra": self._minimizar_normal()
            elif opcion == "Bandeja": self.tray.ocultar_a_tray()
            else: DialogoMinimizar(self, self._minimizar_normal, self.tray.ocultar_a_tray)

    def _minimizar_normal(self):
        self.unbind("<Unmap>"); self.iconify(); self.after(300, lambda: self.bind("<Unmap>", self._al_minimizar))

    def _refrescar_pestana_activa(self):
        tab_actual = self.tabview.get()
        if tab_actual == "🔥 Ofertas y Búsqueda":
            self._ejecutar_busqueda_inteligente()
        elif tab_actual == "⭐ Mi Watchlist":
            self._iniciar_comprobacion_rebajas()
        elif tab_actual == "🎮 Mi Biblioteca & Co-op":
            self._iniciar_analisis_biblioteca()

    def _vincular_atajos_teclado(self):
        # Búsqueda instantánea
        self.bind("<Control-f>", lambda e: self._atajo_buscar())
        self.bind("<Control-F>", lambda e: self._atajo_buscar())

        # Escape para limpiar filtro en vivo o desenfocar
        self.bind("<Escape>", lambda e: self._atajo_escape())

        # Recarga / Refresco de pestaña activa
        self.bind("<F5>", lambda e: self._refrescar_pestana_activa())
        self.bind("<Control-r>", lambda e: self._refrescar_pestana_activa())
        self.bind("<Control-R>", lambda e: self._refrescar_pestana_activa())

        # Navegación rápida de pestañas
        self.bind("<Control-Key-1>", lambda e: self.tabview.set("🔥 Ofertas y Búsqueda"))
        self.bind("<Control-Key-2>", lambda e: self.tabview.set("⭐ Mi Watchlist"))
        self.bind("<Control-Key-3>", lambda e: self.tabview.set("🎮 Mi Biblioteca & Co-op"))

        # Acceso directo a Changuito
        self.bind("<Control-b>", lambda e: self._abrir_modal_carrito())
        self.bind("<Control-B>", lambda e: self._abrir_modal_carrito())

        # Buscador Rápido Global (Command Palette)
        self.bind("<Control-k>", lambda e: self._abrir_command_palette())
        self.bind("<Control-K>", lambda e: self._abrir_command_palette())

        # Acceso directo a Dashboard, Eventos e Historial ATL
        self.bind("<Control-d>", lambda e: self._abrir_dashboard_visual())
        self.bind("<Control-D>", lambda e: self._abrir_dashboard_visual())
        self.bind("<Control-e>", lambda e: self._lanzar_modal_ofertas())
        self.bind("<Control-E>", lambda e: self._lanzar_modal_ofertas())
        self.bind("<Control-h>", lambda e: self._abrir_historial_atl())
        self.bind("<Control-H>", lambda e: self._abrir_historial_atl())
        self.bind("<Control-g>", lambda e: self._abrir_radar_regalos())
        self.bind("<Control-G>", lambda e: self._abrir_radar_regalos())
        self.bind("<Control-m>", lambda e: self._abrir_gestor_cromos())
        self.bind("<Control-M>", lambda e: self._abrir_gestor_cromos())

        # Paginación con flechas
        self.bind("<Left>", lambda e: self._pagina_anterior() if self.pagina_actual > 1 else None)
        self.bind("<Right>", lambda e: self._pagina_siguiente() if self.pagina_actual < self.total_paginas else None)

    def _atajo_buscar(self):
        self.tabview.set("🔥 Ofertas y Búsqueda")
        if hasattr(self, "entry_search_smart"):
            self.entry_search_smart.focus_set()
            self.entry_search_smart.select_range(0, "end")
        return "break"

    def _atajo_escape(self):
        if hasattr(self, "entry_local_filter") and self.entry_local_filter.get():
            self.entry_local_filter.delete(0, "end")
            self._actualizar_orden_y_paginar()
        elif hasattr(self, "entry_search_smart") and self.focus_get() == self.entry_search_smart:
            self.focus_set()
        return "break"

    def _abrir_command_palette(self):
        self.sfx.play("click")
        DialogoCommandPalette(self)

    def _lanzar_modal_ofertas(self): self.sfx.play("click"); abrir_ventana_ofertas(self, self.config)
    def _abrir_dashboard_visual(self): self.sfx.play("click"); DialogoDashboardVisual(self)
    def _abrir_historial_atl(self):
        self.sfx.play("click")
        d = DialogoHistorialATL(self)
        self.wait_window(d)
        self._actualizar_badge_atl()

    def _actualizar_badge_atl(self):
        if not hasattr(self, "btn_header_atl") or not self.winfo_exists():
            return
        try:
            cnt = self.db.contar_alertas_atl()
            if cnt > 0:
                self.btn_header_atl.configure(text=f"🏆 Récords ({cnt})", fg_color="#e65100", text_color="#ffffff", border_width=0)
            else:
                self.btn_header_atl.configure(text="🏆 Récords", fg_color=self.palette["card_bg"], text_color=self.palette["accent"], border_width=1, border_color=self.palette["border"], hover_color=self.palette["card_hover"])
        except Exception:
            pass

    def _lanzar_patch_notes(self): self.sfx.play("click"); DialogoPatchNotes(self)
    def _abrir_configuracion(self): self.sfx.play("click"); DialogoConfiguracion(self, self.config, self.db, self._actualizar_orden_y_paginar)
    def _abrir_modal_redes(self): self.sfx.play("click"); DialogoRedes(self)
    def _abrir_actualizador(self): self.sfx.play("click"); DialogoActualizador(self)
    def _abrir_modal_carrito(self): self.sfx.play("click"); DialogoCarrito(self)

    def _seleccionar_para_comparar(self, item):
        self.sfx.play("click")
        if self.item_comparar_a is None or str(self.item_comparar_a.get("appid")) == str(item.get("appid")):
            self.item_comparar_a = item
            self._show_toast(f"⚔️ '{item.get('titulo','')[:24]}' fijado. Tocá '⚔️' en otro juego para comparar.", self.palette["accent"])
        else:
            item_a = self.item_comparar_a
            self.item_comparar_a = None
            DialogoComparadorVersus(self, item_a, item)
    def _mostrar_drawer_carrito(self, event=None):
        if not self.carrito:
            return
        if hasattr(self, "_drawer_win") and self._drawer_win and self._drawer_win.winfo_exists():
            return

        pal = self.palette
        drawer = ctk.CTkToplevel(self)
        drawer.overrideredirect(True)
        drawer.wm_attributes("-topmost", True)
        self._drawer_win = drawer

        x = self.cart_bar.winfo_rootx() + 15
        y = self.cart_bar.winfo_rooty() - 10

        frame = ctk.CTkFrame(drawer, fg_color=pal["card_bg"], corner_radius=10, border_width=2, border_color=pal["accent"])
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="🛒 En tu changuito:", font=("Segoe UI", 12, "bold"), text_color=pal["accent"]).pack(anchor="w", padx=12, pady=(8, 4))

        dolar = self.config.datos.get("dolar_referencia", 1000.0)
        imp = self.config.datos.get("impuestos_pct", 60)
        mult = 1 + (imp / 100.0)

        items = list(self.carrito.values())
        for itm in items[:6]:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)
            t = itm.get("titulo", "Juego")[:30]
            p_usd = itm.get("precio_oferta_usd", 0.0)
            p_ars = round(p_usd * dolar * mult)
            ctk.CTkLabel(row, text=f"• {t}", font=("Segoe UI", 11), text_color=pal["text"]).pack(side="left")
            ctk.CTkLabel(row, text=f" ${p_usd:.2f} (${p_ars:,.0f})", font=("Consolas", 10, "bold"), text_color=pal["subtext"]).pack(side="right", padx=(8, 0))

        if len(items) > 6:
            ctk.CTkLabel(frame, text=f"... y {len(items) - 6} más", font=("Segoe UI", 10, "italic"), text_color=pal["subtext"]).pack(anchor="w", padx=14, pady=(2, 0))

        tot_ahorro = sum(max(0.0, itm.get("precio_normal_usd", itm.get("precio_oferta_usd", 0)) - itm.get("precio_oferta_usd", 0)) for itm in items)
        if tot_ahorro > 0:
            ahorro_ars = round(tot_ahorro * dolar * mult)
            ctk.CTkLabel(frame, text=f"🎉 Ahorro acumulado: ${tot_ahorro:.2f} USD (~${ahorro_ars:,.0f} ARS)", font=("Segoe UI", 11, "bold"), text_color="#00e676").pack(anchor="w", padx=12, pady=(4, 2))

        ctk.CTkLabel(frame, text="💡 Clic en 'Ver Detalle' para el simulador completo", font=("Segoe UI", 9), text_color=pal["subtext"]).pack(anchor="w", padx=12, pady=(4, 8))

        drawer.update_idletasks()
        h = drawer.winfo_height()
        drawer.geometry(f"+{x}+{y - h}")

    def _ocultar_drawer_carrito(self, event=None):
        if hasattr(self, "_drawer_win") and self._drawer_win and self._drawer_win.winfo_exists():
            self._drawer_win.destroy()
            self._drawer_win = None

    def _guardar_filtro_favorito(self):
        self.sfx.play("cart_add")
        preset = {
            "descuento": self.combo_descuento.get(),
            "precio_max": self.entry_precio_max.get().strip(),
            "precio_rango": self.combo_precio_rango.get(),
            "limite": self.combo_limit.get(),
            "modalidad": self.combo_mode.get(),
            "cat_padre": self.combo_cat_padre.get() if hasattr(self, "combo_cat_padre") else "Todas las Categorías",
            "subcat": self.combo_subcat.get() if hasattr(self, "combo_subcat") else "Todas las subcategorías",
            "calidad": self.combo_calidad.get()
        }
        self.config.guardar_basico("filtro_favorito", preset)
        self._show_toast("⭐ Preset guardado.", self.palette["accent"])

    def _aplicar_filtro_favorito(self):
        self.sfx.play("click")
        fav = self.config.datos.get("filtro_favorito", {})
        if not fav:
            self._show_toast("⚠️ No hay preset favorito guardado.", "#ffab00")
            return
        if fav.get("descuento") in RANGOS_DESCUENTO: self.combo_descuento.set(fav["descuento"])
        self.entry_precio_max.delete(0, "end")
        if fav.get("precio_max"): self.entry_precio_max.insert(0, fav["precio_max"])
        if fav.get("precio_rango") in RANGOS_PRECIO: self.combo_precio_rango.set(fav["precio_rango"])
        if fav.get("limite") in ["50", "100", "200", "300", "500"]: self.combo_limit.set(fav["limite"])
        if fav.get("modalidad") in MODALIDADES: self.combo_mode.set(fav["modalidad"])
        if hasattr(self, "combo_cat_padre") and fav.get("cat_padre") in CATEGORIAS_STEAM:
            self.combo_cat_padre.set(fav["cat_padre"])
            subcats = obtener_subcategorias_para(fav["cat_padre"])
            self.combo_subcat.configure(values=subcats)
            if fav.get("subcat") in subcats:
                self.combo_subcat.set(fav["subcat"])
            else:
                self.combo_subcat.set(subcats[0] if subcats else "Todas las subcategorías")
        elif fav.get("genero") in GENEROS and hasattr(self, "combo_cat_padre"):
            self.combo_cat_padre.set("Todas las Categorías")
        if fav.get("calidad") in FILTROS_CALIDAD: self.combo_calidad.set(fav["calidad"])
        self._show_toast("📂 Preset favorito cargado.", "#00e676")
        self._actualizar_orden_y_paginar()

    def _al_cambiar_cat_padre(self, val):
        subcats = obtener_subcategorias_para(val)
        self.combo_subcat.configure(values=subcats)
        self.combo_subcat.set(subcats[0] if subcats else "Todas las subcategorías")
        self._actualizar_orden_y_paginar()

    def _restablecer_todos_los_filtros(self):
        self.sfx.play("click")
        self.combo_descuento.set("Cualquier Descuento")
        self.combo_precio_rango.set("Cualquier Precio")
        self.entry_precio_max.delete(0, "end")
        self.combo_limit.set("100")
        self.combo_mode.set("Cualquiera")
        if hasattr(self, "combo_cat_padre"):
            self.combo_cat_padre.set("Todas las Categorías")
            self.combo_subcat.configure(values=["Todas las subcategorías"])
            self.combo_subcat.set("Todas las subcategorías")
        self.combo_calidad.set("Cualquier Calidad")
        if hasattr(self, "entry_local_filter"):
            self.entry_local_filter.delete(0, "end")
        if hasattr(self, "entry_search_smart"):
            self.entry_search_smart.delete(0, "end")
        self.kpi_filter = "all"
        self._actualizar_orden_y_paginar()
        self._show_toast("🧹 Filtros restablecidos.", self.palette["accent"])

    def _on_local_filter_keyrelease(self, event=None):
        if hasattr(self, "_filter_debounce_timer") and self._filter_debounce_timer:
            try:
                self.after_cancel(self._filter_debounce_timer)
            except Exception:
                pass
        self._filter_debounce_timer = self.after(160, self._actualizar_orden_y_paginar)

    def _on_smart_search_keyrelease(self, event=None):
        pass

    def _on_precio_max_keyrelease(self, event=None):
        if hasattr(self, "_precio_debounce_timer") and self._precio_debounce_timer:
            try:
                self.after_cancel(self._precio_debounce_timer)
            except Exception:
                pass
        self._precio_debounce_timer = self.after(250, self._actualizar_orden_y_paginar)

    def _registrar_busqueda_reciente(self, query):
        rec = self.config.datos.get("busquedas_recientes", [])
        if query in rec: rec.remove(query)
        rec.insert(0, query)
        rec = rec[:5]
        self.config.guardar_basico("busquedas_recientes", rec)
        self.combo_recientes.configure(values=["🕒 Recientes"] + rec)
        self.combo_recientes.set("🕒 Recientes")

    def _seleccionar_busqueda_reciente(self, valor):
        if valor == "🕒 Recientes" or not valor: return
        self.entry_search_smart.delete(0, "end")
        self.entry_search_smart.insert(0, valor)
        self.combo_recientes.set("🕒 Recientes")
        self._ejecutar_busqueda_inteligente()

    def _toggle_carrito_item(self, item):
        appid = str(item["appid"])
        if appid in self.carrito:
            del self.carrito[appid]; self.sfx.play("cart_remove"); self._show_toast("🛒 Quitado del changuito.", "#ff9800")
        else:
            self.carrito[appid] = item; self.sfx.play("cart_add"); self._show_toast(f"🛒 '{item.get('titulo','')[:24]}' sumado al changuito.", self.palette["accent"])
        self.config.guardar_basico("carrito_guardado", self.carrito)
        self._actualizar_barra_carrito(); self._renderizar_pagina_actual()

    def _vaciar_carrito(self):
        self.carrito.clear(); self.config.guardar_basico("carrito_guardado", self.carrito)
        self.sfx.play("cart_remove"); self._actualizar_barra_carrito(); self._renderizar_pagina_actual()
        self._show_toast("🗑 Changuito vaciado.", "#ef5350")

    def _actualizar_barra_carrito(self):
        if not hasattr(self, "cart_bar"): return
        if not self.carrito: self.cart_bar.pack_forget(); return
        cant = len(self.carrito); tot_usd = sum(i.get("precio_oferta_usd", 0) for i in self.carrito.values())
        tot_reg_usd = sum(i.get("precio_normal_usd", i.get("precio_oferta_usd", 0)) for i in self.carrito.values())
        dolar = self.config.datos.get("dolar_referencia", 1000.0); imp = self.config.datos.get("impuestos_pct", 60)
        tot_ars = round(tot_usd * dolar * (1 + imp / 100.0))
        tot_wallet = round(tot_usd * dolar)
        ahorro_usd = max(0.0, tot_reg_usd - tot_usd)
        ahorro_ars = round(ahorro_usd * dolar * (1 + imp / 100.0))
        ahorro_str = f"  •  🎉 Ahorrás: ${ahorro_usd:.2f} USD (~${ahorro_ars:,.0f} ARS)" if ahorro_usd > 0 else ""
        self.lbl_cart_info.configure(text=f"🛒 Changuito: {cant} juego(s) | Total: ${tot_usd:.2f} USD  ➔  💳 Tarjeta: ${tot_ars:,.0f} ARS  |  🪙 Wallet: ${tot_wallet:,.0f} ARS{ahorro_str}", text_color=self.palette["text"])

        # Medidor de Presupuesto Reactivo
        presupuesto_usd = float(self.config.datos.get("presupuesto_carrito_usd", 0.0) or 0.0)
        if presupuesto_usd > 0:
            diff = presupuesto_usd - tot_usd
            ratio = (tot_usd / presupuesto_usd) * 100.0 if presupuesto_usd > 0 else 0
            if tot_usd <= presupuesto_usd:
                if ratio >= 85.0:
                    budget_col = "#ffab00"  # Ámbar
                    budget_txt = f"⚠️ Límite: ${tot_usd:.2f}/${presupuesto_usd:.2f} USD ({ratio:.0f}% • Quedan ${diff:.2f})"
                else:
                    budget_col = "#00e676"  # Verde
                    budget_txt = f"🎯 Presupuesto: ${tot_usd:.2f}/${presupuesto_usd:.2f} USD ({ratio:.0f}% • Quedan ${diff:.2f})"
            else:
                budget_col = "#ff003c"  # Rojo
                budget_txt = f"🚨 Excedido: ${tot_usd:.2f}/${presupuesto_usd:.2f} USD (+${abs(diff):.2f})"
            self.lbl_cart_budget.configure(text=f"|  {budget_txt}", text_color=budget_col)
            self.btn_cart_budget.configure(text=f"🎯 ${presupuesto_usd:.0f} USD", fg_color="#263238")
        else:
            self.lbl_cart_budget.configure(text="", text_color=self.palette["subtext"])
            self.btn_cart_budget.configure(text="🎯 Presupuesto", fg_color="#37474f")

        self.cart_bar.configure(fg_color=self.palette["card_bg"], border_color=self.palette["accent"])
        self.cart_bar.pack(fill="x", padx=20, pady=(2, 4), before=self.footer)

    def _fijar_presupuesto_carrito(self):
        pres_act = float(self.config.datos.get("presupuesto_carrito_usd", 0.0) or 0.0)
        val = pedir_input_skin(
            self,
            "🎯 Presupuesto Máximo de Compras",
            "Fijá tu límite de gasto en USD (ej: 25.00). Ingresá 0 para desactivar:",
            valor_inicial=f"{pres_act:.2f}" if pres_act > 0 else "25.00",
            modo="float",
            min_val=0.0,
            max_val=9999.0
        )
        if val is not None:
            self.config.guardar_basico("presupuesto_carrito_usd", float(val))
            self._actualizar_barra_carrito()
            self.sfx.play("click")
            if float(val) > 0:
                self._show_toast(f"🎯 Presupuesto fijado en ${float(val):.2f} USD")
            else:
                self._show_toast("🎯 Presupuesto desactivado")

    def _copiar_oferta_al_portapapeles(self, item):
        dolar = self.config.datos.get("dolar_referencia", 1000.0)
        imp = self.config.datos.get("impuestos_pct", 60)
        txt = formatear_oferta_para_compartir(item, dolar, imp)
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.update()
        self.sfx.play("click")
        self._show_toast("💬 ¡Ficha copiada para compartir en WhatsApp o Discord!", "#00e676")

    def _exportar_presupuesto_png(self):
        self.exporter.exportar_presupuesto_png()

    def _copiar_resumen_whatsapp(self):
        self.exporter.copiar_resumen_whatsapp()

    def _enviar_oferta_discord(self, item):
        self.exporter.enviar_oferta_discord(item)

    def _abrir_radar_regalos(self):
        self.sfx.play("click")
        DialogoRadarRegalos(self)

    def _abrir_gestor_cromos(self):
        self.sfx.play("click")
        DialogoGestorCromos(self)

    def _on_gamepad_connection(self, conectado: bool):
        if not self.winfo_exists():
            return
        if conectado:
            if hasattr(self, "lbl_gamepad"):
                self.lbl_gamepad.configure(text="🎮 Mando Activo", text_color="#00e676")
            self._show_toast("🎮 Mando XInput detectado y activo.", "#00e676")
        else:
            if hasattr(self, "lbl_gamepad"):
                self.lbl_gamepad.configure(text="", text_color=self.palette.get("subtext", "gray"))

    def _on_gamepad_dpad_left(self):
        if not self.winfo_exists():
            return
        tab = self.tabview.get()
        if "Ofertas" in tab:
            self._pagina_anterior()
        elif "Biblioteca" in tab:
            self._lib_pagina_anterior()

    def _on_gamepad_dpad_right(self):
        if not self.winfo_exists():
            return
        tab = self.tabview.get()
        if "Ofertas" in tab:
            self._pagina_siguiente()
        elif "Biblioteca" in tab:
            self._lib_pagina_siguiente()

    def _on_gamepad_cycle_tab_left(self):
        if not self.winfo_exists():
            return
        tabs = ["🔥 Ofertas y Búsqueda", "⭐ Mi Watchlist", "🎮 Mi Biblioteca & Co-op"]
        actual = self.tabview.get()
        idx = (tabs.index(actual) - 1) % len(tabs) if actual in tabs else 0
        self.tabview.set(tabs[idx])

    def _on_gamepad_cycle_tab_right(self):
        if not self.winfo_exists():
            return
        tabs = ["🔥 Ofertas y Búsqueda", "⭐ Mi Watchlist", "🎮 Mi Biblioteca & Co-op"]
        actual = self.tabview.get()
        idx = (tabs.index(actual) + 1) % len(tabs) if actual in tabs else 0
        self.tabview.set(tabs[idx])

    def _lanzar_ruleta_sorpresa(self):
        self.sfx.play("click")
        # Si la ruleta ya está abierta, no abrimos otra ventana: giramos directamente en el lugar (Spin-In-Place)
        if hasattr(self, "_ruleta_activa") and self._ruleta_activa and self._ruleta_activa.winfo_exists():
            self._ruleta_activa.modo = "deals"
            self._ruleta_activa.deiconify()
            self._ruleta_activa.lift()
            self._ruleta_activa.focus_force()
            self._ruleta_activa.girar_de_nuevo()
            return

        aid_actual = None
        item_elegido = self._obtener_siguiente_item_ruleta(modo="deals", appid_actual=aid_actual)
        if item_elegido:
            self.sfx.play("roulette_tick")
            DialogoRuleta(self, item_elegido, modo="deals")
            return

        self._show_toast("🎲 Buscando oferta sorpresa...", self.palette["accent"])
        threading.Thread(target=self._hilo_ruleta_global, daemon=True).start()

    def _obtener_siguiente_item_ruleta(self, modo="deals", appid_actual=None):
        """Selecciona un juego para la ruleta garantizando que nunca se repita el juego actual."""
        aid_actual_str = str(appid_actual) if appid_actual is not None else ""
        if modo == "backlog":
            if not self.biblioteca_data:
                return None
            cands = [j for j in self.biblioteca_data if str(j.get("appid")) != aid_actual_str]
            sin_jugar = [j for j in cands if j.get("horas", 0) < 0.5]
            pool = sin_jugar if sin_jugar else cands
            return random.choice(pool) if pool else (self.biblioteca_data[0] if self.biblioteca_data else None)

        # Modo Ofertas (Deals)
        fuente = self.deals_filtradas or self.deals_data or getattr(self, "_ruleta_deals_pool", [])
        cands = [
            d for d in fuente
            if str(d.get("appid")) != aid_actual_str
            and str(d.get("appid")) not in self.carrito
            and not d.get("es_dlc", False)
        ]
        if not cands and getattr(self, "_ruleta_deals_pool", []):
            cands = [d for d in self._ruleta_deals_pool if str(d.get("appid")) != aid_actual_str]

        # Si el pool de candidatos está bajo, nutrimos de forma proactiva en segundo plano
        if len(cands) < 8:
            self._recargar_pool_ruleta_async()

        return random.choice(cands) if cands else None

    def _recargar_pool_ruleta_async(self):
        """Descarga en segundo plano un lote de ofertas variadas de Steam para mantener nutrida la ruleta."""
        if getattr(self, "_recargando_ruleta", False):
            return
        self._recargando_ruleta = True
        blacklist = set(self.db.get_blacklist())

        def _worker():
            try:
                pagina_azar = random.randint(0, 25)
                r = HTTP_SESSION.get(
                    "https://www.cheapshark.com/api/1.0/deals",
                    params={"storeID": "1", "onSale": "1", "pageSize": "40", "pageNumber": str(pagina_azar)},
                    timeout=4
                )
                if r.status_code == 200 and r.json():
                    pool_existente = {str(d.get("appid")) for d in getattr(self, "_ruleta_deals_pool", [])}
                    nuevos_items = []
                    appids_para_precio = []
                    for d in r.json():
                        aid = str(d.get("steamAppID") or "")
                        if aid and aid not in pool_existente and aid not in blacklist and aid not in self.juegos_propios:
                            appids_para_precio.append(aid)
                            nuevos_items.append(d)

                    if appids_para_precio:
                        precios_ar = self._obtener_precios_argentina_lote(appids_para_precio)
                        lote_final = []
                        for d in nuevos_items:
                            aid = str(d.get("steamAppID"))
                            if aid in precios_ar:
                                norm = precios_ar[aid]["normal"]
                                sale = precios_ar[aid]["oferta"]
                                desc = precios_ar[aid]["descuento"]
                            else:
                                norm = float(d.get("normalPrice", 0))
                                sale = float(d.get("salePrice", 0))
                                desc = round(((norm - sale) / norm) * 100) if norm > sale else 0
                            meta = self.db.get_game_meta(aid)
                            mod_txt = meta[0] if meta else "Oferta Destacada"
                            gen_display = meta[1] if meta else "Steam"
                            es_minimo = self.db.update_historical_min(aid, sale) if sale > 0 else False
                            lote_final.append({
                                "appid": aid, "thumb_url": d.get("thumb"), "titulo": d.get("title", "Juego Sorpresa"),
                                "precio_oferta_usd": sale, "precio_normal_usd": norm, "descuento": desc,
                                "rating": d.get("steamRatingPercent", "N/A"), "modalidad": mod_txt, "genero": gen_display,
                                "es_atl": es_minimo, "es_bug": False, "es_dlc": False,
                                "tiene_cromos": self._tiene_cromos_juego(aid),
                                "es_deck": self._es_steam_deck_verificado(aid),
                                "link": f"https://store.steampowered.com/app/{aid}"
                            })
                        if not hasattr(self, "_ruleta_deals_pool"):
                            self._ruleta_deals_pool = []
                        self._ruleta_deals_pool.extend(lote_final)
            except Exception:
                pass
            finally:
                self._recargando_ruleta = False

        threading.Thread(target=_worker, daemon=True).start()

    def _hilo_ruleta_global(self):
        """Descarga sincrónicamente un primer paquete de ofertas si la app aún no tiene deals cacheadas."""
        blacklist = set(self.db.get_blacklist())
        try:
            r = HTTP_SESSION.get(
                "https://www.cheapshark.com/api/1.0/deals",
                params={"storeID": "1", "onSale": "1", "pageSize": "40", "pageNumber": str(random.randint(0, 15))},
                timeout=4.5
            )
            if r.status_code == 200 and r.json():
                cands_raw = [
                    d for d in r.json()
                    if d.get("steamAppID")
                    and str(d.get("steamAppID")) not in self.carrito
                    and str(d.get("steamAppID")) not in blacklist
                    and str(d.get("steamAppID")) not in self.juegos_propios
                ] or r.json()

                ids_lote = [str(d.get("steamAppID")) for d in cands_raw if d.get("steamAppID")]
                precios_ar = self._obtener_precios_argentina_lote(ids_lote) if ids_lote else {}

                items_procesados = []
                for d in cands_raw:
                    aid = str(d.get("steamAppID") or "")
                    if not aid:
                        continue
                    if aid in precios_ar:
                        norm = precios_ar[aid]["normal"]
                        sale = precios_ar[aid]["oferta"]
                        desc = precios_ar[aid]["descuento"]
                    else:
                        norm = float(d.get("normalPrice", 0))
                        sale = float(d.get("salePrice", 0))
                        desc = round(((norm - sale) / norm) * 100) if norm > sale else 0
                    meta = self.db.get_game_meta(aid)
                    mod_txt = meta[0] if meta else "Oferta Destacada"
                    gen_display = meta[1] if meta else "Steam"
                    es_minimo = self.db.update_historical_min(aid, sale) if sale > 0 else False
                    items_procesados.append({
                        "appid": aid, "thumb_url": d.get("thumb"), "titulo": d.get("title", "Juego Sorpresa"),
                        "precio_oferta_usd": sale, "precio_normal_usd": norm, "descuento": desc,
                        "rating": d.get("steamRatingPercent", "N/A"), "modalidad": mod_txt, "genero": gen_display,
                        "es_atl": es_minimo, "es_bug": False, "es_dlc": False,
                        "tiene_cromos": self._tiene_cromos_juego(aid),
                        "es_deck": self._es_steam_deck_verificado(aid),
                        "link": f"https://store.steampowered.com/app/{aid}"
                    })

                if not hasattr(self, "_ruleta_deals_pool"):
                    self._ruleta_deals_pool = []
                self._ruleta_deals_pool.extend(items_procesados)
        except Exception:
            pass

        aid_actual = getattr(self._ruleta_activa, "item_final", {}).get("appid") if hasattr(self, "_ruleta_activa") and self._ruleta_activa and self._ruleta_activa.winfo_exists() else None
        item_elegido = self._obtener_siguiente_item_ruleta(modo="deals", appid_actual=aid_actual)

        if item_elegido:
            self.sfx.play("roulette_tick")
            def _mostrar_ruleta_red():
                if hasattr(self, "_ruleta_activa") and self._ruleta_activa and self._ruleta_activa.winfo_exists():
                    self._ruleta_activa.modo = "deals"
                    self._ruleta_activa.deiconify()
                    self._ruleta_activa.lift()
                    self._ruleta_activa.focus_force()
                    self._ruleta_activa.girar_de_nuevo(nuevo_item=item_elegido)
                else:
                    DialogoRuleta(self, item_elegido, modo="deals")
            self.after(0, _mostrar_ruleta_red)
        else:
            self.after(0, lambda: mostrar_alerta_skin(self, "Ruleta", "No se pudo conectar con el servidor de ofertas.", tipo="warning"))

    def _exportar_placa_redes(self, item):
        self.exporter.exportar_placa_redes(item)

    def _redondear_imagen_pil(self, pil_img, w, h, radius=10, badge_pct=0, es_atl=False):
        img = ImageOps.fit(pil_img.convert("RGBA"), (w, h), Image.Resampling.LANCZOS)
        if h > w:
            draw_ov = ImageDraw.Draw(img)
            try: f_badge = ImageFont.truetype("arialbd.ttf", 13)
            except: f_badge = ImageFont.load_default()
            if badge_pct > 0:
                draw_ov.rounded_rectangle([(w - 64, 8), (w - 8, 32)], radius=6, fill=(0, 230, 118, 240) if badge_pct >= 50 else (3, 169, 244, 240))
                draw_ov.text((w - 56, 13), f"-{badge_pct}%", fill=(0, 0, 0, 255), font=f_badge)
            if es_atl:
                draw_ov.rounded_rectangle([(8, 8), (68, 30)], radius=6, fill=(255, 0, 60, 235))
                draw_ov.text((14, 12), "MIN HIST", fill=(255, 255, 255, 255), font=f_badge)
        mask = Image.new("L", (w, h), 0); ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (w, h)], radius=radius, fill=255)
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0)); out.paste(img, (0, 0), mask)
        return out

    def _aplicar_icono_ventana(self, win):
        try:
            ico_path = obtener_ruta_recurso("icono.ico")
            if os.path.exists(ico_path):
                win.iconbitmap(ico_path)
                win.wm_iconbitmap(default=ico_path)
        except Exception:
            pass

    def _generar_placeholder(self, w, h, radius=8):
        img = Image.new("RGBA", (w, h), color=(22, 26, 34, 255))
        ImageDraw.Draw(img).rounded_rectangle([(0, 0), (w-1, h-1)], radius=radius, fill=(22, 26, 34, 255), outline=(45, 55, 72, 255), width=1)
        ImageDraw.Draw(img).text((w//2 - 20, h//2 - 5), "STEAM", fill=(100, 116, 139, 255))
        out = self._redondear_imagen_pil(img, w, h, radius=radius)
        return ctk.CTkImage(light_image=out, dark_image=out, size=(w, h))

    def _show_toast(self, mensaje, color="#00e676"):
        if self.current_toast and self.current_toast.winfo_exists(): self.current_toast.destroy()
        toast = ctk.CTkFrame(self, fg_color=self.palette["card_bg"], corner_radius=20, border_width=1, border_color=color)
        toast.place(relx=0.5, rely=0.88, anchor="s"); self.current_toast = toast
        ctk.CTkLabel(toast, text=mensaje, font=("Arial", 12, "bold"), text_color=self.palette["text"]).pack(padx=25, pady=8)
        self.after(3000, lambda: toast.destroy() if toast.winfo_exists() else None)

    def _crear_interfaz(self):
        self.topbar = ctk.CTkFrame(self, fg_color="transparent"); self.topbar.pack(fill="x", padx=20, pady=(12, 6))
        try:
            ico_path = obtener_ruta_recurso("icono.ico")
            if os.path.exists(ico_path):
                with Image.open(ico_path) as raw_ico:
                    raw_ico.load()
                    pil_ico = raw_ico.convert("RGBA").resize((28, 28), Image.Resampling.LANCZOS)
                self._brand_ctk_icon = ctk.CTkImage(light_image=pil_ico, dark_image=pil_ico, size=(28, 28))
                self.lbl_brand = ctk.CTkLabel(self.topbar, text=f"  SteamScope v{APP_VERSION}", image=self._brand_ctk_icon, compound="left", font=("Segoe UI", 18, "bold"))
            else:
                self.lbl_brand = ctk.CTkLabel(self.topbar, text=f"⚡ SteamScope v{APP_VERSION}", font=("Segoe UI", 18, "bold"))
        except Exception:
            self.lbl_brand = ctk.CTkLabel(self.topbar, text=f"⚡ SteamScope v{APP_VERSION}", font=("Segoe UI", 18, "bold"))
        self.lbl_brand.pack(side="left")
        self.btn_modal_calendar = ctk.CTkButton(self.topbar, text="📅 Eventos y Calc", fg_color="#00695c", hover_color="#00796b", font=("Segoe UI", 12, "bold"), width=130, command=self._lanzar_modal_ofertas); self.btn_modal_calendar.pack(side="left", padx=(10, 3))
        self.btn_radar_epic = ctk.CTkButton(self.topbar, text="🎁 Regalos", fg_color="#107c10", hover_color="#0e6b0e", font=("Segoe UI", 12, "bold"), width=95, command=self._abrir_radar_regalos); self.btn_radar_epic.pack(side="left", padx=3)
        self.btn_cromos = ctk.CTkButton(self.topbar, text="🃏 Cromos", fg_color="#673ab7", hover_color="#512da8", font=("Segoe UI", 12, "bold"), width=90, command=self._abrir_gestor_cromos); self.btn_cromos.pack(side="left", padx=3)
        self.btn_dashboard = ctk.CTkButton(self.topbar, text="📊 Dashboard", fg_color="#7c4dff", hover_color="#651fff", font=("Segoe UI", 12, "bold"), width=105, command=self._abrir_dashboard_visual); self.btn_dashboard.pack(side="left", padx=3)
        self.btn_config = ctk.CTkButton(self.topbar, text="⚙️ Ajustes", fg_color="#3949ab", hover_color="#283593", font=("Segoe UI", 12, "bold"), width=92, command=self._abrir_configuracion); self.btn_config.pack(side="left", padx=3)
        self.btn_header_atl = ctk.CTkButton(self.topbar, text="⭐ Récords", fg_color="#37474f", hover_color="#e65100", font=("Segoe UI", 12, "bold"), width=92, command=self._abrir_historial_atl); self.btn_header_atl.pack(side="left", padx=3)
        self.btn_cmd_palette = ctk.CTkButton(self.topbar, text="⚡ Acciones (Ctrl+K)", fg_color="#263238", hover_color="#455a64", font=("Segoe UI", 12, "bold"), width=140, command=self._abrir_command_palette); self.btn_cmd_palette.pack(side="left", padx=3)
        self.lbl_gamepad = ctk.CTkLabel(self.topbar, text="", font=("Segoe UI", 11, "bold"))
        self.lbl_gamepad.pack(side="left", padx=6)
        self.seg_vista = ctk.CTkSegmentedButton(self.topbar, values=["Compacta", "Normal", "Grilla"], font=("Segoe UI", 12, "bold"), command=self._cambiar_vista)
        self.seg_vista.set(self.config.datos.get("vista_resultados", "Normal")); self.seg_vista.pack(side="right", padx=(10, 0))
        self.lbl_vista = ctk.CTkLabel(self.topbar, text="Vista:", font=("Segoe UI", 12, "bold")); self.lbl_vista.pack(side="right", padx=4)
        self.combo_theme = ctk.CTkOptionMenu(self.topbar, values=list(SKIN_PALETTES.keys()), font=("Segoe UI", 12, "bold"), command=self._cambiar_tema, width=148); self.combo_theme.pack(side="right", padx=(6, 0))
        self.lbl_skin_dot = ctk.CTkLabel(self.topbar, text="●", font=("Segoe UI", 16, "bold")); self.lbl_skin_dot.pack(side="right", padx=(10, 0))
        self.lbl_tema = ctk.CTkLabel(self.topbar, text="Skin:", font=("Segoe UI", 12, "bold")); self.lbl_tema.pack(side="right", padx=2)
        self.combo_moneda = ctk.CTkOptionMenu(self.topbar, values=["USD", "ARS (Tarjeta)", "ARS (Cripto)"], font=("Segoe UI", 12, "bold"), command=self._cambiar_moneda, width=142)
        self.combo_moneda.set(self.moneda_actual); self.combo_moneda.pack(side="right", padx=(8, 12))
        self.lbl_moneda = ctk.CTkLabel(self.topbar, text="Pago:", font=("Segoe UI", 12, "bold")); self.lbl_moneda.pack(side="right", padx=3)
        self.tabview = ctk.CTkTabview(self); self.tabview.pack(fill="both", expand=True, padx=20, pady=4)
        self.tab_deals = self.tabview.add("🔥 Ofertas y Búsqueda")
        self.tab_watch = self.tabview.add("⭐ Mi Watchlist")
        self.tab_lib = self.tabview.add("🎮 Mi Biblioteca & Co-op")
        self._armar_pestana_ofertas(); self._armar_pestana_watchlist(); self._armar_pestana_biblioteca()
        self._actualizar_badge_atl()
        self.cart_bar = ctk.CTkFrame(self, height=42, corner_radius=10, border_width=1)
        self.lbl_cart_info = ctk.CTkLabel(self.cart_bar, text="", font=("Consolas", 12, "bold"))
        self.lbl_cart_info.pack(side="left", padx=16, pady=6)
        self.lbl_cart_info.bind("<Enter>", self._mostrar_drawer_carrito)
        self.lbl_cart_info.bind("<Leave>", self._ocultar_drawer_carrito)
        self.lbl_cart_budget = ctk.CTkLabel(self.cart_bar, text="", font=("Consolas", 11, "bold"))
        self.lbl_cart_budget.pack(side="left", padx=(4, 8), pady=6)
        ctk.CTkButton(self.cart_bar, text="🗑 Vaciar", width=80, height=26, fg_color="#b71c1c", hover_color="#d32f2f", text_color="white", command=self._vaciar_carrito).pack(side="right", padx=(4, 12), pady=6)
        ctk.CTkButton(self.cart_bar, text="🔎 Ver Detalle", width=110, height=26, fg_color="#00695c", hover_color="#00897b", text_color="white", command=self._abrir_modal_carrito).pack(side="right", padx=4, pady=6)
        self.btn_cart_budget = ctk.CTkButton(self.cart_bar, text="🎯 Presupuesto", width=115, height=26, fg_color="#37474f", hover_color="#455a64", text_color="white", command=self._fijar_presupuesto_carrito)
        self.btn_cart_budget.pack(side="right", padx=4, pady=6)
        
        self.footer = ctk.CTkFrame(self, height=50, fg_color="transparent"); self.footer.pack(fill="x", padx=20, pady=8)
        self.btn_version_notes = ctk.CTkButton(self.footer, text=f"v{APP_VERSION} 📜", width=65, height=26, command=self._lanzar_patch_notes); self.btn_version_notes.pack(side="left", padx=(10, 6))
        self.btn_redes = ctk.CTkButton(self.footer, text="📱 Mis Redes", width=80, height=26, command=self._abrir_modal_redes); self.btn_redes.pack(side="left", padx=(0, 6))
        self.btn_update = ctk.CTkButton(self.footer, text="🔄 Actualizar", width=95, height=26, command=self._abrir_actualizador); self.btn_update.pack(side="left", padx=(0, 8))
        self.lbl_status = ctk.CTkLabel(self.footer, text="Listo para buscar.", text_color=self.palette["subtext"]); self.lbl_status.pack(side="left", padx=5)
        
        self.combo_exportar = ctk.CTkOptionMenu(self.footer, values=["📤 Exportar...", "📊 Excel (.xlsx)", "📄 PDF Ejecutivo", "📋 Copiar WhatsApp/Telegram"], width=175, command=self._manejar_exportacion)
        self.combo_exportar.pack(side="right", padx=(6, 15), pady=8)

        # PAGINACION NUEVA
        self.pag_frame = ctk.CTkFrame(self.footer, fg_color="transparent"); self.pag_frame.pack(side="right", padx=15)
        self.btn_prev = ctk.CTkButton(self.pag_frame, text="◀ Ant", width=60, command=self._pagina_anterior, state="disabled"); self.btn_prev.pack(side="left", padx=5)
        
        self.btn_pag = ctk.CTkButton(self.pag_frame, text="Pág 1 / 1", fg_color="transparent", border_width=1, width=70, command=self._saltar_a_pagina)
        self.btn_pag.pack(side="left", padx=8)

        self.btn_next = ctk.CTkButton(self.pag_frame, text="Sig ▶", width=60, command=self._pagina_siguiente, state="disabled"); self.btn_next.pack(side="left", padx=5)

    def _saltar_a_pagina(self):
        if self.total_paginas <= 1: return
        val = pedir_input_skin(
            self,
            "🔢 Ir a página",
            f"Ingresá el número de página (1 - {self.total_paginas}):",
            valor_inicial=str(self.pagina_actual),
            modo="int",
            min_val=1,
            max_val=self.total_paginas,
        )
        if val:
            self.sfx.play("page")
            self.pagina_actual = val
            self._renderizar_pagina_actual()

    def _pagina_anterior(self):
        if self.pagina_actual > 1: 
            self.sfx.play("page")
            self.pagina_actual -= 1
            self._renderizar_pagina_actual()

    def _pagina_siguiente(self):
        if self.pagina_actual < self.total_paginas: 
            self.sfx.play("page")
            self.pagina_actual += 1
            self._renderizar_pagina_actual()

    def _manejar_exportacion(self, opcion):
        self.combo_exportar.set("📤 Exportar...")
        if "Excel" in opcion: self._exportar_excel()
        elif "PDF" in opcion: self._exportar_pdf()
        elif "WhatsApp" in opcion: self._copiar_resumen_whatsapp()

    def _cambiar_tema(self, tema_nombre):
        if tema_nombre not in SKIN_PALETTES: tema_nombre = "Oscuro"
        self.config.guardar_basico("tema", tema_nombre); self.combo_theme.set(tema_nombre); self.sfx.play("click")
        pal = SKIN_PALETTES[tema_nombre]; self.palette = pal; ctk.set_appearance_mode(pal["mode"]); self.configure(fg_color=pal["win_bg"])
        fg_txt_btn = texto_contraste_acento(pal)
        fg_txt_accent_2 = texto_contraste_color(pal["accent_2"])

        self.lbl_brand.configure(text_color=pal["accent"])
        self.btn_modal_calendar.configure(fg_color=pal["accent_2"], hover_color=pal["accent"], text_color=fg_txt_accent_2)
        if hasattr(self, "btn_dashboard"):
            self.btn_dashboard.configure(fg_color=pal["card_bg"], text_color=pal["accent"], border_width=1, border_color=pal["accent"], hover_color=pal["card_hover"])
        if hasattr(self, "btn_radar_epic"):
            self.btn_radar_epic.configure(fg_color="#107c10", hover_color="#0e6b0e", text_color="white")
        if hasattr(self, "btn_cromos"):
            self.btn_cromos.configure(fg_color="#673ab7", hover_color="#512da8", text_color="white")
        self.btn_config.configure(fg_color=pal["accent"], hover_color=pal["accent_2"], text_color=fg_txt_btn)
        self.seg_vista.configure(fg_color=pal["card_bg"], selected_color=pal["accent"], selected_hover_color=pal["accent_2"], unselected_color=pal["card_bg"], unselected_hover_color=pal["card_hover"], text_color=pal["text"])
        self.combo_moneda.configure(fg_color=pal["card_bg"], button_color=pal["accent"], button_hover_color=pal["accent_2"], dropdown_fg_color=pal["card_bg"], dropdown_hover_color=pal["card_hover"], dropdown_text_color=pal["text"], text_color=pal["text"])
        self.combo_theme.configure(fg_color=pal["card_bg"], button_color=pal["accent"], button_hover_color=pal["accent_2"], dropdown_fg_color=pal["card_bg"], dropdown_hover_color=pal["card_hover"], dropdown_text_color=pal["text"], text_color=pal["text"])
        if hasattr(self, "lbl_skin_dot"):
            self.lbl_skin_dot.configure(text_color=pal["accent"])
        for lbl in (self.lbl_vista, self.lbl_tema, self.lbl_moneda): lbl.configure(text_color=pal["text"])
        self.tabview.configure(fg_color=pal["panel_bg"], segmented_button_fg_color=pal["card_bg"], segmented_button_selected_color=pal["accent"], segmented_button_selected_hover_color=pal["accent_2"], segmented_button_unselected_color=pal["card_bg"], segmented_button_unselected_hover_color=pal["card_hover"], text_color=pal["text"])
        self.filtros_box.configure(fg_color=pal["card_bg"], border_width=1, border_color=pal["border"])
        for cb in (self.combo_descuento, self.combo_precio_rango, self.combo_limit, self.combo_mode, self.combo_cat_padre, self.combo_subcat, self.combo_calidad):
            cb.configure(fg_color=pal["panel_bg"], border_color=pal["border"], button_color=pal["accent"], button_hover_color=pal["accent_2"], dropdown_fg_color=pal["card_bg"], dropdown_hover_color=pal["card_hover"], dropdown_text_color=pal["text"], text_color=pal["text"])
        for ent in (self.entry_precio_max, self.entry_search_smart, self.entry_local_filter, self.entry_watch_search, self.entry_amigo_id, self.entry_lib_search):
            ent.configure(fg_color=pal["card_bg"], border_color=pal["border"], text_color=pal["text"], placeholder_text_color=pal["subtext"])
        for opt in (self.combo_recientes, self.combo_sort, self.combo_watch_filter, self.combo_lib_sort):
            opt.configure(fg_color=pal["card_bg"], button_color=pal["accent_2"], button_hover_color=pal["accent"], dropdown_fg_color=pal["card_bg"], dropdown_hover_color=pal["card_hover"], dropdown_text_color=pal["text"], text_color=pal["text"])

        # Actualizar etiquetas de filtros para evitar texto negro en modo oscuro
        filter_labels = [
            getattr(self, "lbl_filtro_desc", None),
            getattr(self, "lbl_filtro_precio", None),
            getattr(self, "lbl_filtro_modo", None),
            getattr(self, "lbl_filtro_limite", None),
            getattr(self, "lbl_filtro_cat", None),
            getattr(self, "lbl_filtro_subcat", None),
            getattr(self, "lbl_filtro_calidad", None),
            getattr(self, "lbl_sort", None),
            getattr(self, "lbl_watch_tag", None),
            getattr(self, "lbl_lib_sort", None)
        ]
        for lbl in filter_labels:
            if lbl and hasattr(lbl, "configure"):
                lbl.configure(text_color=pal["text"])

        if hasattr(self, "btn_toggle_filtros"):
            self.btn_toggle_filtros.configure(fg_color=pal["card_bg"], text_color=pal["text"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"])
        if hasattr(self, "kpi_bar"):
            self._actualizar_kpi_dashboard()
        self.btn_search_smart.configure(fg_color=pal["accent"], hover_color=pal["accent_2"], text_color=fg_txt_btn)
        self.btn_version_notes.configure(fg_color=pal["card_bg"], hover_color=pal["card_hover"], text_color=pal["accent"], border_width=1, border_color=pal["border"])
        self.btn_redes.configure(fg_color=pal["card_bg"], hover_color=pal["card_hover"], text_color="#ff5252", border_width=1, border_color=pal["border"])
        self.btn_update.configure(fg_color=pal["card_bg"], hover_color=pal["card_hover"], text_color="#00e676", border_width=1, border_color=pal["border"])
        self.combo_exportar.configure(fg_color=pal["deal_badge"], button_color=pal["accent_2"], button_hover_color=pal["accent"], dropdown_fg_color=pal["card_bg"], dropdown_hover_color=pal["card_hover"], dropdown_text_color=pal["text"], text_color=pal["deal_text"])
        self.lbl_status.configure(text_color=pal["accent"])
        self.btn_sync_steam.configure(fg_color=pal["accent"], hover_color=pal["accent_2"], text_color=fg_txt_btn)
        self.btn_check_drops.configure(fg_color=pal["accent_2"], hover_color=pal["accent"], text_color=fg_txt_accent_2)
        self.btn_reload_watch.configure(fg_color=pal["card_bg"], hover_color=pal["card_hover"], text_color=pal["text"], border_width=1, border_color=pal["border"])

        # Botones de barra superior y herramientas con paleta dinámica
        if hasattr(self, "btn_cmd_palette"):
            self.btn_cmd_palette.configure(fg_color=pal["card_bg"], text_color=pal["text"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"])
        if hasattr(self, "btn_export_watch_csv"):
            self.btn_export_watch_csv.configure(fg_color=pal["card_bg"], text_color=pal["accent"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"])
        if hasattr(self, "btn_export_lib_csv"):
            self.btn_export_lib_csv.configure(fg_color=pal["card_bg"], text_color=pal["accent"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"])
        if hasattr(self, "btn_historial_atl"):
            self.btn_historial_atl.configure(fg_color=pal["accent_2"], hover_color=pal["accent"], text_color=fg_txt_accent_2)
        if hasattr(self, "btn_cart_budget"):
            self.btn_cart_budget.configure(fg_color=pal["card_bg"], text_color=pal["text"], border_width=1, border_color=pal["border"], hover_color=pal["card_hover"])
        self._actualizar_badge_atl()

        if hasattr(self, "btn_scan_lib"):
            self.btn_scan_lib.configure(fg_color=pal["accent"], hover_color=pal["accent_2"], text_color=fg_txt_btn)
            self.btn_valuar_lib.configure(fg_color=pal["deal_badge"], hover_color="#00c853", text_color=pal["deal_text"])
            self.btn_sortear_backlog.configure(fg_color=pal["accent_2"], hover_color=pal["accent"], text_color=fg_txt_accent_2)
            self.btn_cruzar_amigo.configure(fg_color=pal["card_bg"], hover_color=pal["card_hover"], text_color=pal["accent"], border_width=1, border_color=pal["accent"])
            self.seg_lib_filter.configure(fg_color=pal["card_bg"], selected_color=pal["accent"], selected_hover_color=pal["accent_2"], unselected_color=pal["card_bg"], unselected_hover_color=pal["card_hover"], text_color=pal["text"])
            self.btn_lib_prev.configure(fg_color=pal["card_bg"], text_color=pal["text"], border_width=1, border_color=pal["border"])
            self.btn_lib_next.configure(fg_color=pal["card_bg"], text_color=pal["text"], border_width=1, border_color=pal["border"])
            self.lbl_lib_pag.configure(text_color=pal["text"])
        self._actualizar_barra_carrito()
        if self.tabview.get() == "🔥 Ofertas y Búsqueda": self._renderizar_pagina_actual()
        elif self.tabview.get() == "⭐ Mi Watchlist": self._renderizar_watchlist()
        elif self.tabview.get() == "🎮 Mi Biblioteca & Co-op": self._renderizar_biblioteca()
        if hasattr(self, "scan_progress"):
            self.scan_progress.configure(progress_color=pal["accent"])

    def _cambiar_moneda(self, moneda):
        self.sfx.play("click"); self.moneda_actual = moneda; self.config.guardar_basico("moneda", moneda)
        self._actualizar_barra_carrito()
        if hasattr(self, "kpi_bar"):
            self._actualizar_kpi_dashboard()
        if self.tabview.get() == "🔥 Ofertas y Búsqueda": self._renderizar_pagina_actual()
        else: self._renderizar_watchlist()

    def _cambiar_vista(self, vista):
        self.sfx.play("click"); self.config.guardar_basico("vista_resultados", vista)
        if self.tabview.get() == "🔥 Ofertas y Búsqueda": self._renderizar_pagina_actual()
        elif self.tabview.get() == "⭐ Mi Watchlist": self._renderizar_watchlist()

    def _formatear_precio(self, precio_usd):
        if self.moneda_actual in ("ARS (Cripto)", "ARS 🪙", "Cripto"):
            dolar_base = self.config.datos.get("dolar_referencia", 1000.0)
            dolar_c = self.config.datos.get("dolar_cripto_ref", round(dolar_base * 1.15))
            return f"${round(precio_usd * dolar_c):,.0f} ARS"
        if self.moneda_actual in ("ARS (Tarjeta)", "ARS", "ARS 💳", "Tarjeta"):
            return f"${round(precio_usd * self.config.datos.get('dolar_referencia', 1000.0) * (1 + self.config.datos.get('impuestos_pct', 60) / 100)):,.0f} ARS"
        return f"${precio_usd:.2f} USD"

    def _copiar_al_portapapeles(self, texto, titulo):
        self.sfx.play("click"); self.clipboard_clear(); self.clipboard_append(texto)
        self._show_toast(f"📋 Enlace de '{titulo}' copiado.", self.palette["accent"])

    def _asignar_etiqueta(self, appid, titulo_actual):
        tag = pedir_input_skin(
            self,
            "🏷️ Asignar Etiqueta",
            f"Asigná una etiqueta personalizada para '{titulo_actual}':\n(Dejá vacío para quitar la etiqueta)",
            modo="str",
        )
        if tag is not None: self.db.set_watchlist_tag(appid, tag); self._renderizar_watchlist()

    def _asignar_precio_objetivo(self, appid, titulo_actual, target_actual=0.0):
        val = pedir_input_skin(
            self,
            "🎯 Precio Objetivo (USD)",
            f"Recibir alerta cuando '{titulo_actual}' baje a o menos de (USD):\n(Poné 0 para desactivar)",
            valor_inicial=str(float(target_actual or 0.0)),
            modo="float",
            min_val=0.0,
            max_val=999.0,
        )
        if val is not None:
            self.sfx.play("coin")
            self.db.set_watchlist_target_price(appid, val)
            if val > 0:
                self._show_toast(f"🎯 Meta de ${val:.2f} USD fijada para '{titulo_actual[:22]}'.", "#00e676")
            else:
                self._show_toast(f"🎯 Precio objetivo quitado de '{titulo_actual[:22]}'.", "#ffab00")
            self._renderizar_watchlist()

    def _mostrar_menu_contextual(self, event, item, es_watchlist):
        if self.current_menu and self.current_menu.winfo_exists(): self.current_menu.destroy()
        appid = item["appid"]; titulo = item["titulo"]; pal = self.palette
        menu_win = ctk.CTkToplevel(self); menu_win.overrideredirect(True); menu_win.wm_attributes("-topmost", True)
        menu_win.geometry(f"+{event.x_root}+{event.y_root}")
        frame = ctk.CTkFrame(menu_win, fg_color=pal["card_bg"], corner_radius=8, border_width=1, border_color=pal["border"]); frame.pack(fill="both", expand=True)
        def create_btn(text, cmd, color=None):
            btn = ctk.CTkButton(frame, text=text, fg_color="transparent", text_color=color or pal["text"], hover_color=pal["card_hover"], anchor="w", font=("Segoe UI", 12), height=30)
            btn.pack(fill="x", padx=4, pady=2); btn.bind("<ButtonPress-1>", lambda e: (cmd(), menu_win.destroy() if menu_win.winfo_exists() else None))
        create_btn("🖥️ Ver Ficha y Termómetro", lambda: DialogoFichaJuego(self, appid, titulo, item), color=pal["accent"])
        create_btn("🌐 Abrir en Steam Web (Evita 21% IVA en ARG)", lambda: webbrowser.open(f"https://store.steampowered.com/app/{appid}"), color="#00e676")
        create_btn("🚀 Abrir en Aplicación Steam Desktop", lambda: webbrowser.open(f"steam://store/{appid}"))
        lbl_vs = "⚔️ Comparar con '" + self.item_comparar_a["titulo"][:18] + "'" if (self.item_comparar_a and str(self.item_comparar_a.get("appid")) != str(appid)) else "⚔️ Comparar Cara a Cara (Versus)"
        create_btn(lbl_vs, lambda: self._seleccionar_para_comparar(item), color="#00e676")
        create_btn("🛒 Sumar / Quitar del Changuito", lambda: self._toggle_carrito_item(item))
        create_btn("📸 Exportar Placa para Redes (PNG)", lambda: self._exportar_placa_redes(item), color="#ce93d8")
        create_btn("📢 Publicar en Discord", lambda: self._enviar_oferta_discord(item), color="#5865F2")
        create_btn("🔗 Copiar Enlace de Steam", lambda: self._copiar_al_portapapeles(item.get("link", f"https://store.steampowered.com/app/{appid}"), titulo))
        create_btn("📋 Copiar Ficha de Oferta (WhatsApp / Discord)", lambda: self._copiar_oferta_al_portapapeles(item), color="#00e676")
        create_btn("▶ Buscar Gameplay en YouTube", lambda: webbrowser.open(f"https://www.youtube.com/results?search_query={titulo}+gameplay"))
        create_btn("⏳ Ver duración (HowLongToBeat)", lambda: webbrowser.open(f"https://howlongtobeat.com/?q={titulo.replace(' ', '+')}"))
        create_btn("🌍 Comparar Precios (SteamDB)", lambda: webbrowser.open(f"https://steamdb.info/app/{appid}/"))
        create_btn("📈 Ver Gráfico Histórico", lambda: DialogoGraficoHistorico(self, titulo, self.db.get_price_log(appid), appid=appid, item_ref=item))
        ctk.CTkFrame(frame, height=1, fg_color=pal["border"]).pack(fill="x", padx=8, pady=2)
        if es_watchlist:
            create_btn("🎯 Definir Precio Objetivo (USD)", lambda: self._asignar_precio_objetivo(appid, titulo, item.get("target_price", 0.0)), color="#00e676")
            create_btn("🏷 Asignar Etiqueta", lambda: self._asignar_etiqueta(appid, titulo))
        create_btn("🚫 Añadir a Ignorados (Blacklist)", lambda: self._ignorar_juego(appid, titulo), color="#ff5252")
        self.current_menu = menu_win; menu_win.focus_force()
        menu_win.bind("<FocusOut>", lambda e: menu_win.destroy() if menu_win.winfo_exists() else None)

    def _ignorar_juego(self, appid, titulo):
        self.db.add_blacklist(appid, titulo); self._actualizar_orden_y_paginar()
        self._show_toast(f"🚫 '{titulo}' añadido a ignorados.", "#ff9800")

    def _toggle_panel_filtros(self):
        self.sfx.play("click")
        self.filtros_visibles = not self.filtros_visibles
        if self.filtros_visibles:
            self.filtros_box.pack(fill="x", padx=10, pady=8, before=self.subbar)
            self.btn_toggle_filtros.configure(text="🔼 Filtros")
        else:
            self.filtros_box.pack_forget()
            self.btn_toggle_filtros.configure(text="🔽 Filtros")

    def _set_kpi_filter(self, modo):
        self.sfx.play("click")
        if self.kpi_filter == modo and modo != "all":
            self.kpi_filter = "all"
        else:
            self.kpi_filter = modo
        self.pagina_actual = 1
        self._actualizar_orden_y_paginar()

    def _actualizar_kpi_dashboard(self):
        if not hasattr(self, "kpi_bar"):
            return
        pal = self.palette
        base_items = getattr(self, "_base_deals_sin_kpi", self.deals_data)
        if not base_items:
            self.kpi_bar.pack_forget()
            return
        self.kpi_bar.pack(fill="x", padx=12, pady=(0, 4), after=self.subbar)
        total_cnt = len(base_items)
        atl_cnt = sum(1 for d in base_items if d.get("es_atl"))
        free_cnt = sum(1 for d in base_items if d.get("descuento") == 100 or (d.get("precio_oferta_usd", 1) == 0.0 and d.get("descuento", 0) > 0))
        sub_cnt = sum(1 for d in base_items if detectar_suscripcion(d.get("titulo", "")))
        cards_cnt = sum(1 for d in base_items if d.get("tiene_cromos"))
        coop_cnt = sum(1 for d in base_items if "cooperativo" in (d.get("modalidad") or "").lower() or "multi" in (d.get("modalidad") or "").lower())
        precios_val = [d["precio_oferta_usd"] for d in base_items if d.get("precio_oferta_usd", 0) > 0]
        prom_usd = (sum(precios_val) / len(precios_val)) if precios_val else 0.0
        prom_fmt = self._formatear_precio(prom_usd)

        fg_kpi_all = texto_contraste_acento(pal) if self.kpi_filter == "all" else pal["text"]
        self.btn_kpi_all.configure(
            text=f"📦 Todos ({total_cnt})",
            fg_color=pal["accent"] if self.kpi_filter == "all" else pal["card_bg"],
            text_color=fg_kpi_all,
            border_color=pal["accent"] if self.kpi_filter == "all" else pal["border"]
        )
        self.btn_kpi_atl.configure(
            text=f"⭐ Récords ATL ({atl_cnt})",
            fg_color="#ffd700" if self.kpi_filter == "atl" else pal["card_bg"],
            text_color="black" if self.kpi_filter == "atl" else "#ffd700",
            border_color="#ffd700" if self.kpi_filter == "atl" else pal["border"]
        )
        if hasattr(self, "btn_kpi_free"):
            self.btn_kpi_free.configure(
                text=f"🎁 100% Gratis ({free_cnt})",
                fg_color="#00c853" if self.kpi_filter == "free" else pal["card_bg"],
                text_color="white" if self.kpi_filter == "free" else "#00e676",
                border_color="#00e676" if self.kpi_filter == "free" else pal["border"]
            )
        self.btn_kpi_sub.configure(
            text=f"🟢 En Suscripción ({sub_cnt})",
            fg_color="#107c10" if self.kpi_filter == "sub" else pal["card_bg"],
            text_color="white" if self.kpi_filter == "sub" else "#4af626",
            border_color="#4af626" if self.kpi_filter == "sub" else pal["border"]
        )
        if hasattr(self, "btn_kpi_cards"):
            self.btn_kpi_cards.configure(
                text=f"🃏 Con Cromos ({cards_cnt})",
                fg_color="#0288d1" if self.kpi_filter == "cards" else pal["card_bg"],
                text_color="white" if self.kpi_filter == "cards" else "#38bdf8",
                border_color="#38bdf8" if self.kpi_filter == "cards" else pal["border"]
            )
        if hasattr(self, "btn_kpi_coop"):
            self.btn_kpi_coop.configure(
                text=f"🤝 Co-op / Multi ({coop_cnt})",
                fg_color="#8e24aa" if self.kpi_filter == "coop" else pal["card_bg"],
                text_color="white" if self.kpi_filter == "coop" else "#ce93d8",
                border_color="#ce93d8" if self.kpi_filter == "coop" else pal["border"]
            )
        self.lbl_kpi_avg.configure(
            text=f"💰 Promedio: {prom_fmt}",
            text_color=pal["subtext"]
        )

    def _mostrar_skeleton_loading(self, mensaje="Escaneando ofertas en Steam..."):
        self._skeleton_active = True
        for w in self.scroll_ofertas.winfo_children():
            w.destroy()
        pal = self.palette
        self.scroll_ofertas.grid_columnconfigure(0, weight=1)
        self._skeleton_bars = []
        for idx in range(5):
            sk_card = ctk.CTkFrame(self.scroll_ofertas, corner_radius=10, fg_color=pal["card_bg"], border_width=1, border_color=pal["border"], height=76)
            sk_card.grid(row=idx, column=0, padx=8, pady=5, sticky="ew")
            sk_card.pack_propagate(False)
            ph_box = ctk.CTkFrame(sk_card, width=136, height=58, corner_radius=8, fg_color=pal["panel_bg"])
            ph_box.pack(side="left", padx=12, pady=9)
            txt_col = ctk.CTkFrame(sk_card, fg_color="transparent")
            txt_col.pack(side="left", fill="both", expand=True, pady=12)
            b1 = ctk.CTkFrame(txt_col, width=260 if idx % 2 == 0 else 210, height=16, corner_radius=6, fg_color=pal["panel_bg"])
            b1.pack(anchor="w", pady=(2, 8))
            b2 = ctk.CTkFrame(txt_col, width=340 if idx % 2 == 0 else 290, height=12, corner_radius=6, fg_color=pal["price_bg"])
            b2.pack(anchor="w")
            p_box = ctk.CTkFrame(sk_card, width=130, height=40, corner_radius=8, fg_color=pal["panel_bg"])
            p_box.pack(side="right", padx=14, pady=14)
            self._skeleton_bars.extend([ph_box, b1, p_box])

        def _animar_pulso(paso=0):
            if not getattr(self, "_skeleton_active", False) or not self.winfo_exists():
                return
            col_a = pal["panel_bg"]
            col_b = pal["card_hover"]
            c_actual = col_b if paso % 2 == 0 else col_a
            for w_bar in getattr(self, "_skeleton_bars", []):
                try:
                    if w_bar.winfo_exists():
                        w_bar.configure(fg_color=c_actual)
                except Exception:
                    pass
            self.after(420, lambda: _animar_pulso(paso + 1))

        _animar_pulso(0)

    def _armar_pestana_ofertas(self):
        self.filtros_box = ctk.CTkFrame(self.tab_deals, corner_radius=10); self.filtros_box.pack(fill="x", padx=10, pady=8)
        
        # Fila 0: Descuento, Precio, Modalidad, Límite e Iconos
        self.lbl_filtro_desc = ctk.CTkLabel(self.filtros_box, text="Descuento:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_desc.grid(row=0, column=0, padx=(12, 5), pady=8, sticky="w")
        self.combo_descuento = ctk.CTkComboBox(self.filtros_box, values=list(RANGOS_DESCUENTO.keys()), state="readonly", width=225, text_color=self.palette["text"], dropdown_text_color=self.palette["text"], command=lambda v: self._actualizar_orden_y_paginar())
        self.combo_descuento.set("Cualquier Descuento")
        self.combo_descuento.grid(row=0, column=1, padx=4, pady=8)
        
        self.lbl_filtro_precio = ctk.CTkLabel(self.filtros_box, text="Precio:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_precio.grid(row=0, column=2, padx=(10, 5), pady=8, sticky="w")
        precio_frame = ctk.CTkFrame(self.filtros_box, fg_color="transparent"); precio_frame.grid(row=0, column=3, padx=4, pady=8, sticky="w")
        self.entry_precio_max = ctk.CTkEntry(precio_frame, width=50, placeholder_text="USD", text_color=self.palette["text"]); self.entry_precio_max.pack(side="left")
        self.entry_precio_max.bind("<KeyRelease>", self._on_precio_max_keyrelease)
        self.combo_precio_rango = ctk.CTkComboBox(precio_frame, values=list(RANGOS_PRECIO.keys()), state="readonly", width=175, text_color=self.palette["text"], dropdown_text_color=self.palette["text"], command=lambda v: self._actualizar_orden_y_paginar())
        self.combo_precio_rango.set("Cualquier Precio")
        self.combo_precio_rango.pack(side="left", padx=(4, 0))
        
        self.lbl_filtro_modo = ctk.CTkLabel(self.filtros_box, text="Modalidad:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_modo.grid(row=0, column=4, padx=(10, 5), pady=8, sticky="w")
        self.combo_mode = ctk.CTkComboBox(self.filtros_box, values=list(MODALIDADES.keys()), state="readonly", width=175, text_color=self.palette["text"], dropdown_text_color=self.palette["text"], command=lambda v: self._actualizar_orden_y_paginar())
        self.combo_mode.set("Cualquiera")
        self.combo_mode.grid(row=0, column=5, padx=4, pady=8)

        self.lbl_filtro_limite = ctk.CTkLabel(self.filtros_box, text="Límite:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_limite.grid(row=0, column=6, padx=(10, 5), pady=8, sticky="w")
        self.combo_limit = ctk.CTkComboBox(self.filtros_box, values=["50", "100", "200", "300", "500"], state="readonly", width=80, text_color=self.palette["text"], dropdown_text_color=self.palette["text"])
        self.combo_limit.set("100")
        self.combo_limit.grid(row=0, column=7, padx=4, pady=8)

        self.filtros_box.grid_columnconfigure(8, weight=1)
        icon_box = ctk.CTkFrame(self.filtros_box, fg_color="transparent")
        icon_box.grid(row=0, column=8, rowspan=2, padx=(15, 20), pady=8, sticky="e")
        ctk.CTkButton(icon_box, text="⭐", width=46, height=40, corner_radius=9, font=("Segoe UI", 16), fg_color="#00695c", hover_color="#00897b", text_color="white", command=self._guardar_filtro_favorito).pack(side="left", padx=3)
        ctk.CTkButton(icon_box, text="📂", width=46, height=40, corner_radius=9, font=("Segoe UI", 16), fg_color="#37474f", hover_color="#455a64", text_color="white", command=self._aplicar_filtro_favorito).pack(side="left", padx=3)
        ctk.CTkButton(icon_box, text="🎲", width=46, height=40, corner_radius=9, font=("Segoe UI", 16), fg_color="#8e24aa", hover_color="#ab47bc", text_color="white", command=self._lanzar_ruleta_sorpresa).pack(side="left", padx=3)
        ctk.CTkButton(icon_box, text="✕", width=46, height=40, corner_radius=9, font=("Segoe UI", 16, "bold"), fg_color="#b71c1c", hover_color="#d32f2f", text_color="white", command=self._restablecer_todos_los_filtros).pack(side="left", padx=3)

        # Fila 1: Categoría Steam, Subcategoría y Calidad de Reseñas
        self.lbl_filtro_cat = ctk.CTkLabel(self.filtros_box, text="Categoría Steam:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_cat.grid(row=1, column=0, padx=(12, 5), pady=8, sticky="w")
        self.combo_cat_padre = ctk.CTkComboBox(self.filtros_box, values=list(CATEGORIAS_STEAM.keys()), state="readonly", width=230, text_color=self.palette["text"], dropdown_text_color=self.palette["text"], dropdown_fg_color=self.palette["card_bg"], fg_color=self.palette["panel_bg"], command=self._al_cambiar_cat_padre)
        self.combo_cat_padre.set("Todas las Categorías")
        self.combo_cat_padre.grid(row=1, column=1, padx=4, pady=8)
        self.combo_genre = self.combo_cat_padre  # Alias para mantener compatibilidad

        self.lbl_filtro_subcat = ctk.CTkLabel(self.filtros_box, text="Subcategoría / Tag:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_subcat.grid(row=1, column=2, padx=(10, 5), pady=8, sticky="w")
        self.combo_subcat = ctk.CTkComboBox(self.filtros_box, values=["Todas las subcategorías"], state="readonly", width=250, text_color=self.palette["text"], dropdown_text_color=self.palette["text"], dropdown_fg_color=self.palette["card_bg"], fg_color=self.palette["panel_bg"], command=lambda v: self._actualizar_orden_y_paginar())
        self.combo_subcat.set("Todas las subcategorías")
        self.combo_subcat.grid(row=1, column=3, padx=4, pady=8)

        self.lbl_filtro_calidad = ctk.CTkLabel(self.filtros_box, text="Calidad:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_filtro_calidad.grid(row=1, column=4, padx=(10, 5), pady=8, sticky="w")
        self.combo_calidad = ctk.CTkComboBox(self.filtros_box, values=list(FILTROS_CALIDAD.keys()), state="readonly", width=190, text_color=self.palette["text"], dropdown_text_color=self.palette["text"], command=lambda v: self._actualizar_orden_y_paginar())
        self.combo_calidad.set("Cualquier Calidad")
        self.combo_calidad.grid(row=1, column=5, padx=4, pady=8)

        self.subbar = ctk.CTkFrame(self.tab_deals, fg_color="transparent"); self.subbar.pack(fill="x", padx=10, pady=(0, 6))
        self.entry_search_smart = ctk.CTkEntry(self.subbar, placeholder_text="Buscar título (o dejar vacío para escanear catálogo)...", font=("Segoe UI", 12), width=300, text_color=self.palette["text"])
        self.entry_search_smart.pack(side="left", padx=(0, 6))
        self.entry_search_smart.bind("<Return>", lambda e: self._ejecutar_busqueda_inteligente())

        self.btn_search_smart = ctk.CTkButton(self.subbar, text="⚡ Buscar / Escanear", width=142, font=("Segoe UI", 12, "bold"), command=self._ejecutar_busqueda_inteligente)
        self.btn_search_smart.pack(side="left", padx=4)

        rec_init = ["🕒 Recientes"] + self.config.datos.get("busquedas_recientes", [])
        self.combo_recientes = ctk.CTkOptionMenu(self.subbar, values=rec_init, width=118, fg_color="#37474f", font=("Segoe UI", 11), text_color="white", dropdown_text_color=self.palette["text"], command=self._seleccionar_busqueda_reciente)
        self.combo_recientes.set("🕒 Recientes")
        self.combo_recientes.pack(side="left", padx=4)

        self.btn_toggle_filtros = ctk.CTkButton(self.subbar, text="🔼 Filtros", width=76, font=("Segoe UI", 11, "bold"), fg_color="#262936", text_color=self.palette["text"], command=self._toggle_panel_filtros)
        self.btn_toggle_filtros.pack(side="left", padx=4)

        self.entry_local_filter = ctk.CTkEntry(self.subbar, placeholder_text="🔍 Filtrar en vivo...", font=("Segoe UI", 11), width=155, text_color=self.palette["text"])
        self.entry_local_filter.pack(side="left", padx=4)
        self.entry_local_filter.bind("<KeyRelease>", self._on_local_filter_keyrelease)

        self.combo_sort = ctk.CTkOptionMenu(self.subbar, values=["Mayor Descuento", "Menor Descuento", "Precio: Menor a Mayor", "Precio: Mayor a Menor", "Mejor Puntuación", "Alfabético"], font=("Segoe UI", 11, "bold"), text_color=self.palette["text"], dropdown_text_color=self.palette["text"], command=lambda v: self._actualizar_orden_y_paginar(), width=165)
        self.combo_sort.set("Mayor Descuento"); self.combo_sort.pack(side="right")
        self.lbl_sort = ctk.CTkLabel(self.subbar, text="Ordenar:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_sort.pack(side="right", padx=(8, 4))

        self.scan_progress = ctk.CTkProgressBar(self.tab_deals, height=4, corner_radius=2, mode="indeterminate")
        self.scan_progress.configure(progress_color=self.palette["accent"])
        self.scan_progress.pack(fill="x", padx=14, pady=(0, 4))
        self.scan_progress.pack_forget()

        self.kpi_bar = ctk.CTkFrame(self.tab_deals, fg_color="transparent")
        self.btn_kpi_all = ctk.CTkButton(self.kpi_bar, text="📦 Todos (0)", height=24, width=108, corner_radius=12, border_width=1, font=("Segoe UI", 11, "bold"), command=lambda: self._set_kpi_filter("all"))
        self.btn_kpi_all.pack(side="left", padx=(2, 4))
        self.btn_kpi_atl = ctk.CTkButton(self.kpi_bar, text="⭐ Récords ATL (0)", height=24, width=135, corner_radius=12, border_width=1, font=("Segoe UI", 11, "bold"), command=lambda: self._set_kpi_filter("atl"))
        self.btn_kpi_atl.pack(side="left", padx=4)
        self.btn_kpi_free = ctk.CTkButton(self.kpi_bar, text="🎁 100% Gratis (0)", height=24, width=132, corner_radius=12, border_width=1, font=("Segoe UI", 11, "bold"), command=lambda: self._set_kpi_filter("free"))
        self.btn_kpi_free.pack(side="left", padx=4)
        self.btn_kpi_sub = ctk.CTkButton(self.kpi_bar, text="🟢 En Suscripción (0)", height=24, width=142, corner_radius=12, border_width=1, font=("Segoe UI", 11, "bold"), command=lambda: self._set_kpi_filter("sub"))
        self.btn_kpi_sub.pack(side="left", padx=4)
        self.btn_kpi_cards = ctk.CTkButton(self.kpi_bar, text="🃏 Con Cromos (0)", height=24, width=132, corner_radius=12, border_width=1, font=("Segoe UI", 11, "bold"), command=lambda: self._set_kpi_filter("cards"))
        self.btn_kpi_cards.pack(side="left", padx=4)
        self.btn_kpi_coop = ctk.CTkButton(self.kpi_bar, text="🤝 Co-op / Multi (0)", height=24, width=138, corner_radius=12, border_width=1, font=("Segoe UI", 11, "bold"), command=lambda: self._set_kpi_filter("coop"))
        self.btn_kpi_coop.pack(side="left", padx=4)
        self.lbl_kpi_avg = ctk.CTkLabel(self.kpi_bar, text="", font=("Consolas", 11, "bold"))
        self.lbl_kpi_avg.pack(side="right", padx=8)

        self.scroll_ofertas = ctk.CTkScrollableFrame(self.tab_deals, corner_radius=10, fg_color="transparent")
        self.scroll_ofertas.pack(fill="both", expand=True, padx=10, pady=4)
        
    def _ejecutar_busqueda_inteligente(self):
        query = self.entry_search_smart.get().strip()
        if query:
            self._registrar_busqueda_reciente(query)
            self._iniciar_busqueda_directa(query)
        else:
            self._iniciar_escaneo_ofertas()

    def _iniciar_busqueda_directa(self, query):
        self.sfx.play("click")
        self.kpi_filter = "all"
        self._bloquear_botones()
        self._actualizar_estado(f"Buscando '{query}' en Steam...", "orange")
        self._mostrar_skeleton_loading()
        threading.Thread(target=self._hilo_buscar_titulo, args=(query,), daemon=True).start()

    def _hilo_buscar_titulo(self, query):
        procesados = []
        blacklist = set(self.db.get_blacklist())
        query_limpia = query.strip()
        q_norm = normalizar_texto(query_limpia)
        palabras_query = [p for p in q_norm.split() if len(p) >= 2]

        try:
            items_raw = []
            appids_vistos = set()

            # 1. API oficial storesearch de Steam (ultra-rápida ~200ms, rankeada oficialmente por Steam)
            try:
                s_resp = HTTP_SESSION.get(
                    "https://store.steampowered.com/api/storesearch",
                    params={"term": query_limpia, "l": "spanish", "cc": "ar"},
                    timeout=5
                )
                if s_resp.status_code == 200:
                    for it in s_resp.json().get("items", []):
                        aid = str(it.get("id", ""))
                        if aid and aid not in appids_vistos:
                            appids_vistos.add(aid)
                            items_raw.append(it)
            except Exception as e:
                print(f"Error en storesearch: {e}")

            # 2. Si storesearch devolvió pocos resultados (< 4), complementar con HTML search filtrando por relevancia
            if len(items_raw) < 4:
                try:
                    r_html = HTTP_SESSION.get(
                        "https://store.steampowered.com/search/results/",
                        params={"term": query_limpia, "cc": "ar", "l": "spanish", "count": 25},
                        timeout=5
                    )
                    if r_html.status_code == 200:
                        bloques = re.findall(
                            r'data-ds-appid="(\d+)"[^>]*>.*?<span class="title">([^<]+)</span>',
                            r_html.text,
                            flags=re.DOTALL
                        )
                        for aid, raw_name in bloques:
                            if aid in appids_vistos:
                                continue
                            nombre_limpio = html.unescape(raw_name).strip()
                            nombre_norm = normalizar_texto(nombre_limpio)

                            # Filtro estricto de relevancia: ignorar recomendaciones aleatorias al final de la página
                            if len(palabras_query) == 1:
                                es_relevante = palabras_query[0] in nombre_norm
                            else:
                                coincidentes = sum(1 for p in palabras_query if p in nombre_norm)
                                es_relevante = (coincidentes >= len(palabras_query) // 2 + 1) or (palabras_query[0] in nombre_norm)

                            if es_relevante:
                                appids_vistos.add(aid)
                                items_raw.append({
                                    "id": aid,
                                    "name": nombre_limpio,
                                    "tiny_image": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_sm_120.jpg"
                                })
                except Exception as e:
                    print(f"Error en html search: {e}")

            appids = [str(it.get("id")) for it in items_raw if it.get("id")]
            mapa_precios_ar = self._obtener_precios_argentina_lote(appids)

            pares_hist = {}
            for aid in appids:
                if aid in mapa_precios_ar and mapa_precios_ar[aid]["oferta"] > 0:
                    pares_hist[aid] = (
                        mapa_precios_ar[aid]["oferta"],
                        mapa_precios_ar[aid]["descuento"],
                        mapa_precios_ar[aid]["normal"]
                    )
            resultados_atl = self.db.update_historical_min_batch(pares_hist)

            for it in items_raw:
                appid = str(it.get("id"))
                if appid in blacklist:
                    continue

                if appid in mapa_precios_ar:
                    norm = mapa_precios_ar[appid]["normal"]
                    sale = mapa_precios_ar[appid]["oferta"]
                    desc = mapa_precios_ar[appid]["descuento"]
                else:
                    p_info = it.get("price")
                    norm = (p_info.get("initial", 0) / 100.0) if p_info else 0.0
                    sale = (p_info.get("final", 0) / 100.0) if p_info else 0.0
                    desc = round(((norm - sale) / norm) * 100) if norm > sale else 0

                nombre = it.get("name", query)
                meta = self.db.get_game_meta(appid)
                if meta:
                    mod_txt, gen_display = meta[0], meta[1]
                else:
                    es_dlc = any(kw in nombre.lower() for kw in ["soundtrack", "dlc", "season pass", "pack", "expansion", "expansión", "paquete", "upgrade"])
                    mod_txt = "Expansión / DLC" if es_dlc else "Single-Player"
                    gen_display = "Contenido Adicional" if es_dlc else "Steam"

                es_minimo = resultados_atl.get(appid, False)
                procesados.append({
                    "appid": appid,
                    "thumb_url": it.get("tiny_image") or f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg",
                    "titulo": nombre,
                    "precio_oferta_usd": sale,
                    "precio_normal_usd": norm or sale,
                    "descuento": desc,
                    "rating": "N/A",
                    "modalidad": mod_txt,
                    "genero": gen_display,
                    "es_atl": es_minimo,
                    "es_bug": (norm >= 29.99 and sale <= 3.00) or desc >= 93,
                    "es_dlc": "dlc" in mod_txt.lower() or "expansión" in mod_txt.lower(),
                    "tiene_cromos": self._tiene_cromos_juego(appid),
                    "es_deck": self._es_steam_deck_verificado(appid),
                    "link": f"https://store.steampowered.com/app/{appid}"
                })
        except Exception as e:
            print(f"Error en búsqueda: {e}")

        self.deals_data = procesados
        self.pagina_actual = 1
        self.after(0, self._actualizar_orden_y_paginar)
        self.after(0, self._desbloquear_botones)

    def _armar_pestana_watchlist(self):
        self.watch_top = ctk.CTkFrame(self.tab_watch, fg_color="transparent"); self.watch_top.pack(fill="x", padx=10, pady=8)
        self.btn_reload_watch = ctk.CTkButton(self.watch_top, text="🔄 Actualizar", command=self._renderizar_watchlist, width=105, font=("Segoe UI", 12, "bold")); self.btn_reload_watch.pack(side="left", padx=4)
        self.btn_sync_steam = ctk.CTkButton(self.watch_top, text="📥 Wishlist", command=self._iniciar_sincronizacion_steam, width=115, font=("Segoe UI", 12, "bold")); self.btn_sync_steam.pack(side="left", padx=4)
        self.btn_check_drops = ctk.CTkButton(self.watch_top, text="🔔 Rebajas", command=self._iniciar_comprobacion_rebajas, width=105, font=("Segoe UI", 12, "bold")); self.btn_check_drops.pack(side="left", padx=4)
        self.btn_historial_atl = ctk.CTkButton(self.watch_top, text="⭐ Récords", command=self._abrir_historial_atl, width=105, font=("Segoe UI", 12, "bold"), fg_color="#b8860b", hover_color="#d4af37", text_color="white"); self.btn_historial_atl.pack(side="left", padx=4)
        self.btn_export_watch_csv = ctk.CTkButton(self.watch_top, text="📥 CSV", command=self.exporter.exportar_watchlist_csv, width=70, font=("Segoe UI", 12, "bold"), fg_color="#37474f", hover_color="#455a64"); self.btn_export_watch_csv.pack(side="left", padx=4)
        self.entry_watch_search = ctk.CTkEntry(self.watch_top, placeholder_text="🔍 Filtrar guardado...", width=165, font=("Segoe UI", 12)); self.entry_watch_search.pack(side="left", padx=6); self.entry_watch_search.bind("<KeyRelease>", lambda e: self._renderizar_watchlist())
        self.combo_watch_filter = ctk.CTkOptionMenu(self.watch_top, values=["Todas las etiquetas"], command=lambda v: self._renderizar_watchlist(), width=155, font=("Segoe UI", 12)); self.combo_watch_filter.pack(side="right", padx=5)
        self.lbl_watch_tag = ctk.CTkLabel(self.watch_top, text="Etiqueta:", font=("Segoe UI", 12, "bold"), text_color=self.palette["text"])
        self.lbl_watch_tag.pack(side="right", padx=4)
        self.lbl_watch_summary = ctk.CTkLabel(self.tab_watch, text="📊 Resumen Watchlist: 0 juegos | Total: $0.00 USD ($0 ARS)", font=("Segoe UI", 12, "bold"), text_color=self.palette["accent"])
        self.lbl_watch_summary.pack(anchor="w", padx=16, pady=(0, 4))
        self.scroll_watchlist = ctk.CTkScrollableFrame(self.tab_watch, corner_radius=10, fg_color="transparent"); self.scroll_watchlist.pack(fill="both", expand=True, padx=10, pady=5)

    def _armar_pestana_biblioteca(self):
        self.lib_top = ctk.CTkFrame(self.tab_lib, fg_color="transparent")
        self.lib_top.pack(fill="x", padx=10, pady=(8, 4))

        self.btn_scan_lib = ctk.CTkButton(
            self.lib_top, text="🔄 Sincronizar Steam", width=145,
            font=("Segoe UI", 12, "bold"), fg_color="#1f6feb", hover_color="#388bfd",
            command=self._iniciar_analisis_biblioteca
        )
        self.btn_scan_lib.pack(side="left", padx=(2, 4))

        self.btn_valuar_lib = ctk.CTkButton(
            self.lib_top, text="💰 Valuar Cuenta", width=130,
            font=("Segoe UI", 12, "bold"), fg_color="#00c853", hover_color="#00e676", text_color="white",
            command=self._iniciar_valuacion_biblioteca
        )
        self.btn_valuar_lib.pack(side="left", padx=4)

        self.btn_sortear_backlog = ctk.CTkButton(
            self.lib_top, text="🎲 ¿A qué juego hoy?", width=150,
            font=("Segoe UI", 12, "bold"), fg_color="#8e24aa", hover_color="#6a1b9a",
            command=self._sortear_juego_backlog
        )
        self.btn_sortear_backlog.pack(side="left", padx=4)

        self.seg_lib_filter = ctk.CTkSegmentedButton(
            self.lib_top,
            values=["Todos", "💤 0 hs", "⏳ < 2 hs", "🏆 +20 hs", "🤝 Co-op"],
            font=("Segoe UI", 11, "bold"),
            command=lambda v: self._renderizar_biblioteca(reset_page=True)
        )
        self.seg_lib_filter.set("Todos")
        self.seg_lib_filter.pack(side="left", padx=6)

        self.btn_cruzar_amigo = ctk.CTkButton(
            self.lib_top, text="🤝 Cruzar", width=95,
            font=("Segoe UI", 12, "bold"), fg_color="#00695c", hover_color="#00897b",
            command=self._iniciar_cruce_amigo
        )
        self.btn_cruzar_amigo.pack(side="right", padx=4)

        self.entry_amigo_id = ctk.CTkEntry(
            self.lib_top, placeholder_text="Steam ID o link amigo...", width=160, font=("Segoe UI", 11)
        )
        self.entry_amigo_id.pack(side="right", padx=4)

        # Subbarra de búsqueda instantánea, ordenamiento y paginación de biblioteca
        self.lib_subbar = ctk.CTkFrame(self.tab_lib, fg_color="transparent")
        self.lib_subbar.pack(fill="x", padx=10, pady=(0, 4))

        self.entry_lib_search = ctk.CTkEntry(
            self.lib_subbar, placeholder_text="🔍 Buscar en mi biblioteca...", width=230, font=("Segoe UI", 11)
        )
        self.entry_lib_search.pack(side="left", padx=(2, 6))
        self.entry_lib_search.bind("<KeyRelease>", lambda e: self._renderizar_biblioteca(reset_page=True))

        self.lbl_lib_sort = ctk.CTkLabel(self.lib_subbar, text="Ordenar:", font=("Segoe UI", 11, "bold"), text_color=self.palette["text"])
        self.lbl_lib_sort.pack(side="left", padx=(6, 4))
        self.combo_lib_sort = ctk.CTkOptionMenu(
            self.lib_subbar,
            values=["Más Jugados", "Alfabético", "Mayor Valor USD", "Sin Jugar Primero"],
            width=150, font=("Segoe UI", 11, "bold"),
            command=lambda v: self._renderizar_biblioteca(reset_page=True)
        )
        self.combo_lib_sort.set("Más Jugados")
        self.combo_lib_sort.pack(side="left", padx=4)

        self.btn_export_lib_csv = ctk.CTkButton(
            self.lib_subbar, text="📥 CSV", width=68,
            font=("Segoe UI", 11, "bold"), fg_color="#37474f", hover_color="#455a64",
            command=self.exporter.exportar_biblioteca_csv
        )
        self.btn_export_lib_csv.pack(side="left", padx=4)

        self.lib_pag_frame = ctk.CTkFrame(self.lib_subbar, fg_color="transparent")
        self.lib_pag_frame.pack(side="right", padx=4)
        self.btn_lib_prev = ctk.CTkButton(self.lib_pag_frame, text="◀", width=36, height=26, state="disabled", command=self._lib_pagina_anterior)
        self.btn_lib_prev.pack(side="left", padx=3)
        self.lbl_lib_pag = ctk.CTkLabel(self.lib_pag_frame, text="Pág 1 / 1", font=("Consolas", 11, "bold"), text_color=self.palette["text"])
        self.lbl_lib_pag.pack(side="left", padx=8)
        self.btn_lib_next = ctk.CTkButton(self.lib_pag_frame, text="▶", width=36, height=26, state="disabled", command=self._lib_pagina_siguiente)
        self.btn_lib_next.pack(side="left", padx=3)

        self.lbl_lib_stats = ctk.CTkLabel(
            self.tab_lib,
            text="💡 Tocá '🔄 Sincronizar Steam' para importar tu biblioteca en segundos (queda guardada en caché local instantánea).",
            font=("Segoe UI", 12, "bold"),
            text_color=self.palette["subtext"]
        )
        self.lbl_lib_stats.pack(anchor="w", padx=16, pady=(0, 4))

        self.scroll_lib = ctk.CTkScrollableFrame(self.tab_lib, corner_radius=10, fg_color="transparent")
        self.scroll_lib.pack(fill="both", expand=True, padx=10, pady=4)

    def _lib_pagina_anterior(self):
        if self.lib_pagina_actual > 1:
            self.sfx.play("page")
            self.lib_pagina_actual -= 1
            self._renderizar_biblioteca(reset_page=False)

    def _lib_pagina_siguiente(self):
        if self.lib_pagina_actual < self.lib_total_paginas:
            self.sfx.play("page")
            self.lib_pagina_actual += 1
            self._renderizar_biblioteca(reset_page=False)

    def _iniciar_analisis_biblioteca(self):
        self.sfx.play("click")
        steam_id = self.config.datos.get("steam_id", "").strip()
        api_key = self.config.datos.get("steam_api_key", "").strip()
        if not steam_id:
            mostrar_alerta_skin(self, "Atención", "Ingresá tu Steam ID en Ajustes (⚙️) para analizar tu biblioteca.", tipo="warning")
            self._abrir_configuracion()
            return
        self.btn_scan_lib.configure(state="disabled")
        self.lbl_lib_stats.configure(text="⏳ Sincronizando tu biblioteca desde Steam y guardando en caché local...", text_color="orange")
        threading.Thread(target=self._hilo_analizar_biblioteca, args=(steam_id, api_key), daemon=True).start()

    def _hilo_analizar_biblioteca(self, steam_id, api_key):
        _, juegos = self.api_client.obtener_biblioteca_detalle(steam_id, api_key)
        if juegos:
            self.db.save_library_batch(juegos)
            self.biblioteca_data = self.db.get_library_cached()
            self.juegos_propios = {str(j["appid"]) for j in self.biblioteca_data}

        def _fin_sync():
            self.btn_scan_lib.configure(state="normal")
            self._renderizar_biblioteca(reset_page=True)
            if not juegos:
                if not api_key:
                    self.lbl_lib_stats.configure(
                        text="🔑 Steam ahora exige tu Steam API Key para leer tus 667 juegos. Tocá '⚙️ Ajustes' -> '🔑 Web' para pegarla en 10 seg.",
                        text_color="#ff5252"
                    )
                    if preguntar_si_no_skin(
                        self,
                        "🔑 Se requiere Steam API Key",
                        "Valve desactivó la lectura anónima de bibliotecas completas sin sesión.\n\n"
                        "Para importar todos tus juegos al instante, necesitás pegar tu Steam API Key gratuita en Ajustes (⚙️).\n\n"
                        "¿Querés abrir la página oficial de Steam para copiar tu API Key y pegarla en Ajustes?",
                        texto_si="🔑 Abrir Steam y Ajustes",
                        texto_no="Ahora no"
                    ):
                        webbrowser.open("https://steamcommunity.com/dev/apikey")
                        self._abrir_configuracion()
                else:
                    self.lbl_lib_stats.configure(
                        text="⚠️ No se pudieron leer tus juegos. Verificá que tu Steam API Key sea válida y que 'Detalles de los juegos' esté en Público en tu perfil de Steam.",
                        text_color="#ff5252"
                    )
            elif not api_key and len(juegos) <= 10:
                self._show_toast(f"⚡ Se importaron {len(juegos)} juegos recientes. Agregá tu Steam API Key en ⚙️ Ajustes para traer los 667 juegos.", "#ffab00")
            else:
                self._show_toast(f"⚡ Biblioteca sincronizada y guardada ({len(juegos)} juegos).", "#00e676")

        self.after(0, _fin_sync)

    def _iniciar_valuacion_biblioteca(self):
        self.sfx.play("click")
        if not self.biblioteca_data:
            mostrar_alerta_skin(self, "Valuar Cuenta", "Primero sincronizá tu biblioteca tocando '🔄 Sincronizar Steam'.", tipo="info")
            return
        pendientes = [str(j["appid"]) for j in self.biblioteca_data if j.get("price_usd", -1.0) < 0]
        if not pendientes:
            self.sfx.play("coin")
            self._show_toast("💰 Todos los juegos de tu biblioteca ya están valuados.", "#00e676")
            self._renderizar_biblioteca(reset_page=False)
            return
        self.btn_valuar_lib.configure(state="disabled")
        self.lbl_lib_stats.configure(text=f"💰 Cotizando precios de tienda para {len(pendientes)} juegos en segundo plano...", text_color="#00e676")
        threading.Thread(target=self._hilo_valuar_biblioteca, args=(pendientes,), daemon=True).start()

    def _hilo_valuar_biblioteca(self, ids_pendientes):
        total = len(ids_pendientes)
        bsize = 40
        for i in range(0, total, bsize):
            chunk = ids_pendientes[i:i + bsize]
            precios_lote = self._obtener_precios_argentina_lote(chunk)
            mapa_guardar = {}
            for aid in chunk:
                if aid in precios_lote:
                    # Para valuación patrimonial guardamos el precio normal (o de oferta si no hubiera normal)
                    p_val = precios_lote[aid].get("normal") or precios_lote[aid].get("oferta") or 0.0
                    mapa_guardar[aid] = float(p_val)
                else:
                    mapa_guardar[aid] = 0.0
            self.db.update_library_prices_batch(mapa_guardar)
            procesados_cnt = min(i + bsize, total)
            self.after(0, lambda p=procesados_cnt, t=total: self.lbl_lib_stats.configure(
                text=f"💰 Valuando tu cuenta en Steam... ({p}/{t} juegos cotizados)", text_color="#00e676"
            ))

        self.biblioteca_data = self.db.get_library_cached()
        def _fin_val():
            self.sfx.play("coin")
            self.btn_valuar_lib.configure(state="normal")
            self._renderizar_biblioteca(reset_page=False)
            self._show_toast("💰 ¡Valuación de cuenta completada!", "#00e676")
        self.after(0, _fin_val)

    def _iniciar_cruce_amigo(self):
        self.sfx.play("click")
        amigo_input = self.entry_amigo_id.get().strip()
        if not amigo_input:
            mostrar_alerta_skin(self, "🤝 Co-op con Amigos", "Ingresá el Steam ID, nombre personalizado o URL del perfil de tu amigo en la caja de texto.", tipo="info")
            return
        api_key = self.config.datos.get("steam_api_key", "").strip()
        self.btn_cruzar_amigo.configure(state="disabled")
        self._actualizar_estado(f"Buscando biblioteca de '{amigo_input}' para cruzar juegos en común...", "orange")
        def _worker():
            _, juegos_amigo = self.api_client.obtener_biblioteca_detalle(amigo_input, api_key)
            self.amigo_juegos_ids = {j["appid"] for j in juegos_amigo}
            def _fin():
                self.btn_cruzar_amigo.configure(state="normal")
                if not self.amigo_juegos_ids:
                    mostrar_alerta_skin(self, "Perfil Privado o no encontrado", "No se pudo leer la biblioteca de tu amigo (asegurate de que su perfil de Steam sea Público).", tipo="warning")
                    return
                if not self.biblioteca_data:
                    self._iniciar_analisis_biblioteca()
                self.seg_lib_filter.set("🤝 Co-op con Amigo")
                self._renderizar_biblioteca(reset_page=True)
                self._show_toast(f"🤝 Biblioteca de amigo cargada ({len(self.amigo_juegos_ids)} juegos).", "#00e676")
            self.after(0, _fin)
        threading.Thread(target=_worker, daemon=True).start()

    def _sortear_juego_backlog(self):
        self.sfx.play("click")
        if not self.biblioteca_data:
            mostrar_alerta_skin(self, "Backlog", "Primero tocá '🔄 Sincronizar Steam' para cargar tus juegos.", tipo="info")
            return
        aid_actual = getattr(self._ruleta_activa, "item_final", {}).get("appid") if hasattr(self, "_ruleta_activa") and self._ruleta_activa and self._ruleta_activa.winfo_exists() else None
        elegido = self._obtener_siguiente_item_ruleta(modo="backlog", appid_actual=aid_actual)
        if not elegido:
            elegido = random.choice(self.biblioteca_data)
        self.sfx.play("roulette_tick")

        if hasattr(self, "_ruleta_activa") and self._ruleta_activa and self._ruleta_activa.winfo_exists():
            self._ruleta_activa.modo = "backlog"
            self._ruleta_activa.deiconify()
            self._ruleta_activa.lift()
            self._ruleta_activa.focus_force()
            self._ruleta_activa.girar_de_nuevo(nuevo_item=elegido)
        else:
            DialogoRuleta(self, elegido, modo="backlog")

    def _renderizar_biblioteca(self, reset_page=False):
        if reset_page:
            self.lib_pagina_actual = 1
        self._lib_token += 1
        tok = self._lib_token
        for w in self.scroll_lib.winfo_children():
            w.destroy()
        try:
            self.scroll_lib._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass
        pal = self.palette
        if not self.biblioteca_data:
            self.lbl_lib_stats.configure(
                text="💡 Configurá tu Steam ID y Steam API Key en Ajustes (⚙️) y tocá '🔄 Sincronizar Steam' para importar tu biblioteca.",
                text_color=pal["subtext"]
            )
            ctk.CTkLabel(
                self.scroll_lib,
                text="Todavía no cargaste tu biblioteca.\nConfigurá tu Steam ID y Steam API Key en Ajustes (⚙️) y tocá '🔄 Sincronizar Steam'.",
                font=("Segoe UI", 13), text_color=pal["subtext"]
            ).pack(pady=40)
            return

        met = self.db.obtener_metricas_backlog()
        total = met["total"] or len(self.biblioteca_data)
        sin_jugar_cnt = met["sin_jugar"]
        apenas_cnt = met["apenas_probados"]
        viciados_cnt = met["viciados"]
        pct_backlog = met["pct_sin_jugar"]
        horas_totales = met["horas_totales"]
        en_comun_cnt = sum(1 for j in self.biblioteca_data if j["appid"] in self.amigo_juegos_ids)

        valuados = [j for j in self.biblioteca_data if j.get("price_usd", -1.0) >= 0]
        val_total_usd = sum(j["price_usd"] for j in valuados if j["price_usd"] > 0)
        val_backlog_usd = sum(j["price_usd"] for j in valuados if j["price_usd"] > 0 and j["horas"] == 0)

        resumen = (
            f"🎮 Biblioteca: {total} juegos   |   "
            f"💤 0 hs: {sin_jugar_cnt} ({pct_backlog}%)   |   "
            f"⏳ < 2 hs: {apenas_cnt}   |   "
            f"🏆 +20 hs: {viciados_cnt}   |   "
            f"⏱️ Total: {horas_totales:,.1f} hs"
        )
        if valuados:
            dolar = self.config.datos.get("dolar_referencia", 1000.0)
            imp = self.config.datos.get("impuestos_pct", 60)
            val_ars = round(val_total_usd * dolar * (1 + imp / 100.0))
            ratio_hs = (val_total_usd / horas_totales) if horas_totales > 0 else 0.0
            resumen += f"   |   💰 Valor: ${val_total_usd:,.2f} USD (${val_ars:,.0f} ARS) • Sin tocar: ${val_backlog_usd:,.2f} USD • ${ratio_hs:.2f}/h"
        if self.amigo_juegos_ids:
            resumen += f"   |   🤝 En común: {en_comun_cnt}"
        api_key_cfg = self.config.datos.get("steam_api_key", "").strip()
        if not api_key_cfg and total <= 10:
            resumen += "   |   🔑 Agregá tu Steam API Key en ⚙️ Ajustes para cargar tus 667 juegos"
        self.lbl_lib_stats.configure(text=resumen, text_color=pal["accent"])

        modo_f = self.seg_lib_filter.get()
        if modo_f in ("💤 0 hs", "⏳ Sin Jugar (0 hs)"):
            lista = [j for j in self.biblioteca_data if j["horas"] < 0.1]
        elif modo_f == "⏳ < 2 hs":
            lista = [j for j in self.biblioteca_data if 0.1 <= j["horas"] < 2.0]
        elif modo_f in ("🏆 +20 hs", "🔥 Más Jugados"):
            lista = [j for j in self.biblioteca_data if j["horas"] >= 20.0]
        elif modo_f in ("🤝 Co-op", "🤝 Co-op con Amigo"):
            lista = [j for j in self.biblioteca_data if j["appid"] in self.amigo_juegos_ids]
        else:
            lista = list(self.biblioteca_data)

        busq_lib = self.entry_lib_search.get().strip().lower() if hasattr(self, "entry_lib_search") else ""
        if busq_lib:
            lista = [j for j in lista if busq_lib in (j.get("titulo") or "").lower()]

        orden_lib = self.combo_lib_sort.get() if hasattr(self, "combo_lib_sort") else "Más Jugados"
        if orden_lib == "Alfabético":
            lista.sort(key=lambda x: (x.get("titulo") or "").lower())
        elif orden_lib == "Mayor Valor USD":
            lista.sort(key=lambda x: (x.get("price_usd", -1.0), x.get("horas", 0)), reverse=True)
        elif orden_lib == "Sin Jugar Primero":
            lista.sort(key=lambda x: (x.get("horas", 0), (x.get("titulo") or "").lower()))
        else:
            lista.sort(key=lambda x: x.get("horas", 0), reverse=True)

        if not lista:
            self.lib_total_paginas = 1
            self.lbl_lib_pag.configure(text="Pág 0 / 0")
            self.btn_lib_prev.configure(state="disabled")
            self.btn_lib_next.configure(state="disabled")
            ctk.CTkLabel(self.scroll_lib, text="No hay juegos que coincidan con este filtro.", font=("Segoe UI", 13), text_color=pal["subtext"]).pack(pady=30)
            return

        self.lib_total_paginas = max(1, math.ceil(len(lista) / self.lib_items_por_pagina))
        if self.lib_pagina_actual > self.lib_total_paginas:
            self.lib_pagina_actual = 1

        ini = (self.lib_pagina_actual - 1) * self.lib_items_por_pagina
        mostrar = lista[ini:ini + self.lib_items_por_pagina]

        self.lbl_lib_pag.configure(text=f"Pág {self.lib_pagina_actual} / {self.lib_total_paginas} ({len(lista)})", text_color=pal["text"])
        self.btn_lib_prev.configure(state="normal" if self.lib_pagina_actual > 1 else "disabled", fg_color=pal["card_bg"], text_color=pal["text"])
        self.btn_lib_next.configure(state="normal" if self.lib_pagina_actual < self.lib_total_paginas else "disabled", fg_color=pal["card_bg"], text_color=pal["text"])

        self.scroll_lib.grid_columnconfigure(0, weight=1)

        def _dibujar_lib_lote(idx=0, bsize=10):
            if tok != self._lib_token:
                return
            fin = min(idx + bsize, len(mostrar))
            for i in range(idx, fin):
                jg = mostrar[i]
                aid = jg["appid"]
                row_card = ctk.CTkFrame(self.scroll_lib, corner_radius=10, fg_color=pal["card_bg"], border_width=1, border_color=pal["border"])
                row_card.grid(row=i, column=0, padx=8, pady=4, sticky="ew")

                lbl_im = ctk.CTkLabel(row_card, text="", image=self.placeholder_compact, width=100, height=46, cursor="hand2")
                lbl_im.pack(side="left", padx=10, pady=6)
                self.ui_executor.submit(self._cargar_imagen_async, aid, jg.get("thumb_url"), lbl_im, "Compacta", 100, 46, 0, False)

                info_f = ctk.CTkFrame(row_card, fg_color="transparent")
                info_f.pack(side="left", fill="both", expand=True, pady=6)
                tit_row_l = ctk.CTkFrame(info_f, fg_color="transparent")
                tit_row_l.pack(anchor="w", fill="x")
                ctk.CTkLabel(tit_row_l, text=jg["titulo"], font=("Segoe UI", 14, "bold"), text_color=pal["text"]).pack(side="left")

                p_lib = jg.get("price_usd", -1.0)
                if p_lib > 0:
                    ctk.CTkLabel(tit_row_l, text=f" 💵 ${p_lib:.2f} USD ", fg_color="#00695c", text_color="white", corner_radius=4, font=("Consolas", 10, "bold")).pack(side="left", padx=8)
                elif p_lib == 0.0:
                    ctk.CTkLabel(tit_row_l, text=" 🆓 Free / Delisted ", fg_color="#37474f", text_color="white", corner_radius=4, font=("Consolas", 9, "bold")).pack(side="left", padx=8)

                hrs = jg["horas"]
                estado_h = "⏳ Nunca abierto (0 hs - En tu Backlog)" if hrs == 0 else f"⏱️ {hrs:,.1f} horas registradas"
                if p_lib > 0 and hrs > 0:
                    estado_h += f"   •   💎 Rendimiento: ${(p_lib / hrs):.2f} USD/hora"
                col_h = "#ffab00" if hrs == 0 else pal["accent"]
                sub_lbl_txt = estado_h + ("   •   🤝 ¡Lo tenés en común con tu amigo!" if aid in self.amigo_juegos_ids else "")
                ctk.CTkLabel(info_f, text=sub_lbl_txt, font=("Consolas", 11, "bold"), text_color=col_h).pack(anchor="w", pady=(2, 0))

                btn_f = ctk.CTkFrame(row_card, fg_color="transparent")
                btn_f.pack(side="right", padx=10)
                ctk.CTkButton(btn_f, text="▶ Jugar", width=74, height=28, fg_color=pal["deal_badge"], hover_color="#00e676", text_color=pal["deal_text"], font=("Segoe UI", 11, "bold"), command=lambda a=aid: webbrowser.open(f"steam://run/{a}")).pack(side="right", padx=3)
                ctk.CTkButton(btn_f, text="🖥️ Ficha", width=66, height=28, fg_color=pal["panel_bg"], hover_color=pal["card_hover"], border_width=1, border_color=pal["border"], text_color=pal["accent"], font=("Segoe UI", 11, "bold"), command=lambda j=jg: DialogoFichaJuego(self, j["appid"], j["titulo"], {"appid": j["appid"], "titulo": j["titulo"], "precio_oferta_usd": max(0.0, float(j.get("price_usd", 0.0))), "precio_normal_usd": max(0.0, float(j.get("price_usd", 0.0))), "descuento": 0, "link": f"https://store.steampowered.com/app/{j['appid']}"})).pack(side="right", padx=3)
            if fin < len(mostrar):
                self.after(12, lambda: _dibujar_lib_lote(fin, bsize))

        _dibujar_lib_lote(0)

    def _tiene_cromos_juego(self, appid):
        meta = self.db.get_game_meta(appid)
        if meta and len(meta) >= 5 and meta[4]:
            g_low = meta[4].lower()
            return ("trading cards" in g_low) or ("cromos" in g_low) or ("cards" in g_low)
        return False

    def _es_steam_deck_verificado(self, appid):
        meta = self.db.get_game_meta(appid)
        if meta and len(meta) >= 5 and meta[4]:
            return es_steam_deck_verificado(meta[4])
        return False

    def _obtener_info_juego(self, appid, req_modo="", req_gen="", req_cat_padre="", req_subcat=""):
        if req_cat_padre in ("Todas las Categorías", "Todas", "Todas las categorías", ""):
            req_cat_padre = ""
        if req_subcat in ("Todas las subcategorías", "Todas", "Todas las Subcategorías", ""):
            req_subcat = ""

        meta = self.db.get_game_meta(appid)
        if meta:
            mod_txt, gen_txt, is_sp, is_mp, genres_list = meta
            if req_modo:
                if req_modo == "Single-player" and not is_sp: return False, "", ""
                if req_modo == "PvP" and ("pvp" not in (genres_list or "").lower() and "competitive" not in (genres_list or "").lower()): return False, "", ""
                if req_modo == "Online Co-op" and "online co-op" not in (genres_list or "").lower(): return False, "", ""
                if req_modo == "Local Co-op" and ("local co-op" not in (genres_list or "").lower() and "split screen" not in (genres_list or "").lower()): return False, "", ""
            if req_gen and (req_gen.lower() not in (genres_list or "").lower()): return False, "", ""
            if req_cat_padre and not coincide_categoria_steam(genres_list or gen_txt, req_cat_padre, req_subcat):
                return False, "", ""
            return True, mod_txt, gen_txt
        mod_txt, gen_txt, is_sp, is_mp = "General", "General", 1, 0
        try:
            spy_res = HTTP_SESSION.get(f"https://steamspy.com/api.php?request=appdetails&appid={appid}", timeout=3.5)
            if spy_res.status_code == 200:
                s_data = spy_res.json(); generos_spy = s_data.get("genre", "")
                tags_spy = list(s_data.get("tags", {}).keys()) if isinstance(s_data.get("tags"), dict) else []
                todos_los_tags = [g.strip() for g in generos_spy.split(",") if g.strip()] + tags_spy; todos_str = ", ".join(todos_los_tags)
                if any(m in todos_str.lower() for m in ["multiplayer", "multi-player", "co-op", "online pvp"]):
                    is_mp, mod_txt = 1, "Multiplayer"
                    if "pvp" in todos_str.lower() or "competitive" in todos_str.lower(): mod_txt = "Multijugador PvP"
                    elif "online co-op" in todos_str.lower(): mod_txt = "Cooperativo Online"
                    elif "local co-op" in todos_str.lower() or "split screen" in todos_str.lower(): mod_txt = "Cooperativo Local"
                else: is_sp, mod_txt = 1, "Single-Player"
                gen_txt = ", ".join(todos_los_tags[:2]) if todos_los_tags else "Acción"
                self.db.save_game_meta(appid, mod_txt, gen_txt, is_sp, is_mp, todos_str)
                if req_modo:
                    if req_modo == "Single-player" and not is_sp: return False, "", ""
                    if req_modo == "PvP" and "pvp" not in todos_str.lower() and "competitive" not in todos_str.lower(): return False, "", ""
                    if req_modo == "Online Co-op" and "online co-op" not in todos_str.lower(): return False, "", ""
                    if req_modo == "Local Co-op" and "local co-op" not in todos_str.lower() and "split screen" not in todos_str.lower(): return False, "", ""
                if req_gen and (req_gen.lower() not in todos_str.lower()): return False, "", ""
                if req_cat_padre and not coincide_categoria_steam(todos_str, req_cat_padre, req_subcat):
                    return False, "", ""
                return True, mod_txt, gen_txt
        except: pass
        if not req_gen and not req_modo and not req_cat_padre: return True, "General", "General"
        return False, "", ""

    def _obtener_precios_argentina_lote(self, lista_appids):
        return self.api_client.obtener_precios_argentina_lote(lista_appids)

    def _iniciar_escaneo_ofertas(self):
        self.sfx.play("click")
        self.kpi_filter = "all"
        self._bloquear_botones()
        self._actualizar_estado("Escaneando catálogo y verificando precios...", "orange")
        self._mostrar_skeleton_loading()
        threading.Thread(target=self._hilo_escaneo_ofertas, daemon=True).start()

    def _hilo_escaneo_ofertas(self):
        min_desc, max_desc = RANGOS_DESCUENTO.get(self.combo_descuento.get(), (1, 100))
        str_precio = self.entry_precio_max.get().strip().replace(",", ".")
        if str_precio:
            try: p_min, p_max = 0.0, float(str_precio)
            except: p_min, p_max = RANGOS_PRECIO.get(self.combo_precio_rango.get(), (0.0, 999.0))
        else: p_min, p_max = RANGOS_PRECIO.get(self.combo_precio_rango.get(), (0.0, 999.0))
        min_rating = FILTROS_CALIDAD.get(self.combo_calidad.get(), 0)
        objetivo_total = int(self.combo_limit.get())
        req_modo = MODALIDADES.get(self.combo_mode.get(), "")
        cat_p = self.combo_cat_padre.get() if hasattr(self, "combo_cat_padre") else ""
        sub_c = self.combo_subcat.get() if hasattr(self, "combo_subcat") else ""
        if cat_p in ("Todas las Categorías", "Todas", "Todas las categorías"):
            cat_p = ""
        if sub_c in ("Todas las subcategorías", "Todas", "Todas las Subcategorías"):
            sub_c = ""

        procesados = []; appids_vistos = set(); blacklist = set(self.db.get_blacklist())
        page_num = 0; hubo_atl = False

        while len(procesados) < objetivo_total and page_num < 25:
            params = {"storeID": "1", "onSale": "1", "pageSize": "60", "pageNumber": str(page_num), "sortBy": "Deal Rating"}
            try:
                r = HTTP_SESSION.get("https://www.cheapshark.com/api/1.0/deals", params=params, timeout=12)
                if r.status_code != 200: break
                raw_deals = r.json()
                if not raw_deals: break

                candidatos = []
                for d in raw_deals:
                    appid = str(d.get('steamAppID') or "")
                    if not appid or appid in appids_vistos or appid in blacklist or appid in self.juegos_propios:
                        continue
                    rating_val = float(d.get("steamRatingPercent", "0")) if str(d.get("steamRatingPercent", "0")).replace('.', '', 1).isdigit() else 0
                    if min_rating > 0 and rating_val < min_rating:
                        continue
                    candidatos.append(d)

                ids_lote = [str(c.get("steamAppID")) for c in candidatos]
                mapa_precios_ar = self._obtener_precios_argentina_lote(ids_lote)
                pares_lote_hist = {}
                items_pagina = []

                for d in candidatos:
                    if len(procesados) + len(items_pagina) >= objetivo_total: break
                    appid = str(d.get('steamAppID'))
                    
                    if appid in mapa_precios_ar:
                        normal_price = mapa_precios_ar[appid]["normal"]
                        sale_price = mapa_precios_ar[appid]["oferta"]
                        ahorro = mapa_precios_ar[appid]["descuento"]
                    else:
                        normal_price = float(d.get("normalPrice", 0))
                        sale_price = float(d.get("salePrice", 0))
                        ahorro = int(round(float(d.get("savings", 0))))

                    if ahorro < min_desc or ahorro > max_desc or sale_price < p_min or sale_price > p_max:
                        continue

                    coincide, mod_txt, gen_display = self._obtener_info_juego(appid, req_modo, "", cat_p, sub_c)
                    if not coincide: continue

                    appids_vistos.add(appid)
                    pares_lote_hist[appid] = (sale_price, ahorro, normal_price)
                    items_pagina.append({
                        "appid": appid, "thumb_url": d.get('thumb'), "titulo": d.get("title"),
                        "precio_oferta_usd": sale_price, "precio_normal_usd": normal_price,
                        "descuento": ahorro, "rating": d.get("steamRatingPercent", "0"),
                        "modalidad": mod_txt, "genero": gen_display,
                        "es_atl": False,
                        "es_bug": (normal_price >= 19.99 and sale_price <= 2.00) or ahorro >= 93,
                        "tiene_cromos": self._tiene_cromos_juego(appid),
                        "es_deck": self._es_steam_deck_verificado(appid),
                        "link": f"https://store.steampowered.com/app/{appid}"
                    })

                res_atl_lote = self.db.update_historical_min_batch(pares_lote_hist)
                for it_p in items_pagina:
                    es_minimo_historico = res_atl_lote.get(it_p["appid"], False)
                    it_p["es_atl"] = es_minimo_historico
                    if es_minimo_historico:
                        hubo_atl = True
                    procesados.append(it_p)

                self.after(0, lambda p=len(procesados): self._actualizar_estado(f"Escaneando catálogo... ({p}/{objetivo_total} ofertas verificadas)", "orange"))
                page_num += 1
            except: break

        self.deals_data = procesados; self.pagina_actual = 1
        if hubo_atl: self.sfx.play("atl")
        self.after(0, self._actualizar_orden_y_paginar); self.after(0, self._desbloquear_botones)

    def _iniciar_sincronizacion_steam(self):
        self.sfx.play("click"); steam_id = self.config.datos.get("steam_id", "").strip()
        if not steam_id: mostrar_alerta_skin(self, "Atención", "Ingresá tu Steam ID en Ajustes (⚙️).", tipo="warning"); self._abrir_configuracion(); return
        self.btn_sync_steam.configure(state="disabled"); self._actualizar_estado("Descargando Wishlist desde Steam...", "blue")
        threading.Thread(target=self._hilo_sincronizar_steam, args=(steam_id,), daemon=True).start()

    def _hilo_sincronizar_steam(self, steam_id_input):
        steam_id = resolver_steam_id(steam_id_input)
        if not steam_id:
            self.after(0, lambda: mostrar_alerta_skin(self, "Error", "Steam ID inválido.", tipo="error"))
            self.after(0, lambda: self.btn_sync_steam.configure(state="normal")); return
        
        try:
            appids_wishlist = []
            nombres_wishlist = {}

            # 1. Descarga directa de datos de la tienda de Steam con paginación (hasta 15 páginas)
            # Este endpoint entrega directamente los nombres oficiales: { aid: { "name": "...", ... } }
            for p in range(15):
                url_pag = (
                    f"https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/?p={p}"
                    if (steam_id.isdigit() and len(steam_id) == 17)
                    else f"https://store.steampowered.com/wishlist/id/{steam_id}/wishlistdata/?p={p}"
                )
                try:
                    r_p = HTTP_SESSION.get(url_pag, timeout=9)
                    if r_p.status_code == 200:
                        d_p = r_p.json()
                        if isinstance(d_p, dict) and d_p:
                            for aid, inf in d_p.items():
                                aid_str = str(aid)
                                if aid_str not in nombres_wishlist:
                                    appids_wishlist.append(aid_str)
                                    if isinstance(inf, dict) and inf.get("name"):
                                        nombres_wishlist[aid_str] = inf["name"].strip()
                            if len(d_p) < 35:
                                break
                        else:
                            break
                    else:
                        break
                except Exception:
                    break

            # 2. Complementar con la API oficial IWishlistService para incluir juegos no listados en la tienda
            try:
                url_api = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={steam_id}"
                r_api = HTTP_SESSION.get(url_api, timeout=10)
                if r_api.status_code == 200:
                    items_w = r_api.json().get("response", {}).get("items", [])
                    for it in items_w:
                        aid_str = str(it.get("appid", ""))
                        if aid_str and aid_str not in appids_wishlist:
                            appids_wishlist.append(aid_str)
            except Exception:
                pass

            if appids_wishlist:
                self.after(0, lambda tot=len(appids_wishlist): self._actualizar_estado(f"Obteniendo nombres y precios en lote ({tot} juegos)...", "orange"))
                
                # 3. Resolver nombres faltantes mediante pool multihilo de Steam/CheapShark
                ids_sin_nombre = [aid for aid in appids_wishlist if not nombres_wishlist.get(aid)]
                if ids_sin_nombre:
                    self.after(0, lambda tot=len(ids_sin_nombre): self._actualizar_estado(f"Resolviendo títulos oficiales ({tot} juegos)...", "orange"))
                    datos_resueltos = self.api_client.obtener_datos_basicos_lote(ids_sin_nombre)
                    for aid, inf in datos_resueltos.items():
                        if inf and inf.get("name"):
                            nombres_wishlist[aid] = inf["name"]

                precios_ar = self._obtener_precios_argentina_lote(appids_wishlist)
                tuplas_lote = []
                pares_hist = {}
                fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                for appid in appids_wishlist:
                    p_info = precios_ar.get(appid, {})
                    precio = p_info.get("oferta", 0.0)
                    if precio > 0:
                        pares_hist[appid] = precio
                    nombre_juego = nombres_wishlist.get(appid) or f"Juego Steam {appid}"
                    tuplas_lote.append((appid, nombre_juego, precio, f"https://store.steampowered.com/app/{appid}", fecha_hoy))

                if pares_hist:
                    self.db.update_historical_min_batch(pares_hist)
                self.db.add_watchlist_batch(tuplas_lote)
                self.after(0, lambda: self._actualizar_estado(f"⚡ Wishlist sincronizada en lote: {len(tuplas_lote)} juegos.", "#00e676"))
        except Exception as e:
            self.after(0, lambda err=str(e): mostrar_alerta_skin(self, "Error", f"No se pudo sincronizar:\n{err}", tipo="error"))
        self.after(0, self._renderizar_watchlist); self.after(0, lambda: self.btn_sync_steam.configure(state="normal"))

    def _actualizar_orden_y_paginar(self):
        blacklist = set(self.db.get_blacklist())
        es_busqueda_manual = bool(self.entry_search_smart.get().strip())
        if es_busqueda_manual:
            base = [d for d in self.deals_data if d["appid"] not in blacklist]
        else:
            base = [d for d in self.deals_data if d["appid"] not in blacklist and d["appid"] not in self.juegos_propios]
            ordenar_ofertas(base, self.combo_sort.get())

        filtro_loc = self.entry_local_filter.get().strip() if hasattr(self, "entry_local_filter") else ""

        # Extraer filtros activos
        combo_d = self.combo_descuento.get()
        if es_busqueda_manual and combo_d == "Cualquier Descuento":
            min_d, max_d = 0, 100
        else:
            min_d, max_d = RANGOS_DESCUENTO.get(combo_d, (1, 100))

        str_p = self.entry_precio_max.get().strip().replace(",", ".")
        if str_p:
            try: p_min, p_max = 0.0, float(str_p)
            except Exception: p_min, p_max = RANGOS_PRECIO.get(self.combo_precio_rango.get(), (0.0, 999.0))
        else:
            p_min, p_max = RANGOS_PRECIO.get(self.combo_precio_rango.get(), (0.0, 999.0))

        min_rat = FILTROS_CALIDAD.get(self.combo_calidad.get(), 0)
        req_m = MODALIDADES.get(self.combo_mode.get(), "")
        cat_p = self.combo_cat_padre.get() if hasattr(self, "combo_cat_padre") else ""
        sub_c = self.combo_subcat.get() if hasattr(self, "combo_subcat") else ""

        if cat_p in ("Todas las Categorías", "Todas", "Todas las categorías"):
            cat_p = ""
        if sub_c in ("Todas las subcategorías", "Todas", "Todas las Subcategorías"):
            sub_c = ""

        # Filtrado instantáneo en memoria a través de core.filters
        base = filtrar_ofertas_en_memoria(
            base,
            texto_busqueda=filtro_loc,
            categoria_padre=cat_p,
            subcategoria=sub_c,
            min_desc=min_d,
            max_desc=max_d,
            p_min=p_min,
            p_max=p_max,
            min_rating=min_rat,
            solo_atl=(self.kpi_filter == "atl"),
            solo_cromos=(self.kpi_filter == "cards"),
            modalidad=req_m
        )

        self._base_deals_sin_kpi = list(base)

        if self.kpi_filter == "atl":
            self.deals_filtradas = [d for d in base if d.get("es_atl")]
        elif self.kpi_filter == "free":
            self.deals_filtradas = [d for d in base if d.get("descuento") == 100 or (d.get("precio_oferta_usd", 1) == 0.0 and d.get("descuento", 0) > 0)]
        elif self.kpi_filter == "sub":
            self.deals_filtradas = [d for d in base if detectar_suscripcion(d.get("titulo", ""))]
        elif self.kpi_filter == "cards":
            self.deals_filtradas = [d for d in base if d.get("tiene_cromos")]
        elif self.kpi_filter == "coop":
            self.deals_filtradas = [d for d in base if "cooperativo" in (d.get("modalidad") or "").lower() or "multi" in (d.get("modalidad") or "").lower()]
        else:
            self.deals_filtradas = list(base)

        self._actualizar_kpi_dashboard()
        self.total_paginas = max(1, math.ceil(len(self.deals_filtradas) / ITEMS_POR_PAGINA))
        if self.pagina_actual > self.total_paginas: self.pagina_actual = 1
        self._renderizar_pagina_actual()

    def _renderizar_pagina_actual(self):
        self._skeleton_active = False
        self._render_token += 1
        token_actual = self._render_token
        for w in self.scroll_ofertas.winfo_children():
            w.destroy()
        try:
            self.scroll_ofertas._parent_canvas.yview_moveto(0.0)
        except:
            pass
        if not self.deals_filtradas:
            self._actualizar_estado("No se encontraron juegos con este filtro.", "yellow")
            self.combo_exportar.configure(state="disabled")
            self.btn_prev.configure(state="disabled")
            self.btn_next.configure(state="disabled")
            self.btn_pag.configure(text="Pág 0 / 0", text_color=self.palette["text"], border_color=self.palette["border"])
            return
        inicio = (self.pagina_actual - 1) * ITEMS_POR_PAGINA
        pagina_items = self.deals_filtradas[inicio:inicio+ITEMS_POR_PAGINA]
        vista = self.config.datos.get("vista_resultados", "Normal")
        cols = 4 if vista == "Grilla" else 1
        for col in range(cols if vista == "Grilla" else 4):
            self.scroll_ofertas.grid_columnconfigure(col, weight=1 if vista == "Grilla" or col == 0 else 0)
        def _dibujar_lote(idx=0, batch_size=6):
            if token_actual != self._render_token:
                return
            fin = min(idx + batch_size, len(pagina_items))
            for i in range(idx, fin):
                item = pagina_items[i]
                card = self._crear_tarjeta_juego(self.scroll_ofertas, item, es_watchlist=False, vista=vista)
                if vista == "Grilla":
                    card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="nsew")
                else:
                    card.grid(row=i, column=0, padx=8, pady=4, sticky="ew")
            if fin < len(pagina_items):
                self.after(12, lambda: _dibujar_lote(fin, batch_size))
        _dibujar_lote(0)
        self.btn_pag.configure(text=f"Pág {self.pagina_actual} / {self.total_paginas}", text_color=self.palette["text"], border_color=self.palette["border"])
        self.btn_prev.configure(state="normal" if self.pagina_actual > 1 else "disabled", fg_color=self.palette["card_bg"], text_color=self.palette["text"], border_width=1, border_color=self.palette["border"])
        self.btn_next.configure(state="normal" if self.pagina_actual < self.total_paginas else "disabled", fg_color=self.palette["card_bg"], text_color=self.palette["text"], border_width=1, border_color=self.palette["border"])
        self.combo_exportar.configure(state="normal")
        self._actualizar_estado(f"Mostrando {len(pagina_items)} de {len(self.deals_filtradas)} títulos.", self.palette["accent"])

    def _cargar_jugadores_async(self, appid, lbl_widget, item):
        if "jugadores_cache" in item:
            self.after(0, lambda: lbl_widget.configure(text=item["jugadores_cache"]) if lbl_widget.winfo_exists() else None); return
        try:
            r = HTTP_SESSION.get(f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}", timeout=3.5)
            if r.status_code == 200:
                count = r.json().get("response", {}).get("player_count", 0)
                txt = f"   •   👥 {count:,} activos" if count > 0 else "   •   👥 Sin datos"
                item["jugadores_cache"] = txt
                self.after(0, lambda: lbl_widget.configure(text=txt) if lbl_widget.winfo_exists() else None)
        except: pass

    def _cargar_imagen_async(self, appid, thumb_url, lbl, vista, width, height, badge_pct=0, es_atl=False):
        cache_key = f"{vista}_{appid}_{width}x{height}_{badge_pct}_{int(es_atl)}" if appid else f"{vista}_default"
        if cache_key in self.mem_image_cache:
            img_cached = self.mem_image_cache[cache_key]
            def _apply_cached():
                if lbl.winfo_exists():
                    lbl._ctk_img = img_cached
                    lbl.configure(image=img_cached)
            self.after(0, _apply_cached)
            return
        if len(self.mem_image_cache) > 250:
            for k in list(self.mem_image_cache.keys())[:60]:
                del self.mem_image_cache[k]
        ruta_archivo = os.path.join(self.cache_dir, f"{vista}_{appid}.jpg")
        rad = 10 if vista == "Grilla" else (8 if vista == "Normal" else 6)
        if appid and os.path.exists(ruta_archivo) and os.path.getsize(ruta_archivo) > 600:
            try:
                with Image.open(ruta_archivo) as raw_pil:
                    raw_pil.load()
                    pil_img = self._redondear_imagen_pil(raw_pil, width, height, radius=rad, badge_pct=badge_pct, es_atl=es_atl)
                img_ctk = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
                self.mem_image_cache[cache_key] = img_ctk
                def _apply_disk():
                    if lbl.winfo_exists():
                        lbl._ctk_img = img_ctk
                        lbl.configure(image=img_ctk)
                self.after(0, _apply_disk)
                return
            except Exception:
                try: os.remove(ruta_archivo)
                except Exception: pass

        if vista == "Grilla" and appid:
            urls = [
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg",
                f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
                thumb_url
            ]
        elif appid:
            urls = [
                thumb_url,
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_231x87.jpg",
                f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_sm_120.jpg"
            ]
        else:
            urls = [thumb_url]

        def _intentar_descarga(lista_urls):
            for url in lista_urls:
                if not url:
                    continue
                try:
                    r = HTTP_SESSION.get(url, timeout=4.0)
                    if r.status_code == 200 and len(r.content) > 600:
                        with Image.open(BytesIO(r.content)) as raw_pil:
                            raw_pil.load()
                            pil_img = self._redondear_imagen_pil(raw_pil, width, height, radius=rad, badge_pct=badge_pct, es_atl=es_atl)
                        if appid:
                            try:
                                with open(ruta_archivo, 'wb') as f:
                                    f.write(r.content)
                            except Exception:
                                pass
                        img_ctk = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
                        self.mem_image_cache[cache_key] = img_ctk
                        def _apply_net(img_ref=img_ctk):
                            if lbl.winfo_exists():
                                lbl._ctk_img = img_ref
                                lbl.configure(image=img_ref)
                        self.after(0, _apply_net)
                        return True
                except Exception:
                    continue
            return False

        if _intentar_descarga(urls):
            return

        # Fallback para juegos nuevos de Steam con rutas hash dinámicas
        if appid:
            header_dinamico = self.api_client.obtener_header_image(appid)
            if header_dinamico:
                _intentar_descarga([header_dinamico])

    def _crear_tarjeta_juego(self, parent, item, es_watchlist=False, vista="Normal"):
        return crear_tarjeta_juego(self, parent, item, es_watchlist=es_watchlist, vista=vista)

    def ejecutar_watchdog_silencioso(self):
        """Monitorea en segundo plano si algún juego de la Wishlist alcanzó su Mínimo Histórico (ATL)."""
        if not self.winfo_exists():
            return
        def _worker():
            try:
                items_wl = self.db.get_all_watchlist()
                if not items_wl:
                    return
                appids = [str(it[0]) for it in items_wl]
                precios_actuales = self.api_client.obtener_precios_argentina_lote(appids)
                mins_hist = self.db.get_historical_mins_batch(appids)

                for it in items_wl:
                    aid = str(it[0])
                    titulo = it[1]
                    if aid in precios_actuales:
                        p_info = precios_actuales[aid]
                        precio_oferta = p_info.get("oferta", 0.0)
                        descuento = p_info.get("descuento", 0)
                        min_reg = mins_hist.get(aid, 0.0)
                        if precio_oferta > 0 and es_minimo_historico_real(precio_oferta, min_reg):
                            notificar_minimo_historico(titulo, precio_oferta, descuento, aid)
                            self.db.registrar_alerta_atl(aid, titulo, precio_oferta, descuento)
                            if self.config.datos.get("alerta_sonido_atl", True):
                                self.sfx.play("atl")
                            self.after(0, self._actualizar_badge_atl)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _actualizar_resumen_watchlist(self, lista_precios_usd):
        cant = len(lista_precios_usd); total_usd = sum(lista_precios_usd)
        mult = 1 + (self.config.datos.get("impuestos_pct", 60) / 100)
        dolar_t = self.config.datos.get("dolar_referencia", 1000.0)
        dolar_c = self.config.datos.get("dolar_cripto_ref", 1100.0)
        total_ars_t = round(total_usd * dolar_t * mult)
        total_ars_c = round(total_usd * dolar_c)
        self.lbl_watch_summary.configure(
            text=f"📊 Resumen Watchlist: {cant} juego(s)   |   USD: ${total_usd:.2f}   |   💳 Tarjeta: ${total_ars_t:,.0f} ARS   |   🪙 Cripto: ${total_ars_c:,.0f} ARS",
            text_color=self.palette["accent"]
        )

    def _guardar_en_watchlist(self, item):
        self.sfx.play("cart_add"); self.db.add_watchlist(item["appid"], item["titulo"], item["precio_oferta_usd"], item["link"])
        self._show_toast(f"⭐ '{item['titulo']}' guardado.", self.palette["accent"]); self._renderizar_watchlist()

    def _quitar_de_watchlist(self, appid):
        self.sfx.play("cart_remove"); self.db.remove_watchlist(appid); self._renderizar_watchlist()

    def _reparar_titulos_watchlist_en_segundo_plano(self):
        """Detecta y repara en segundo plano juegos en la Watchlist que tengan códigos o placeholders."""
        if getattr(self, "_reparando_titulos_wl", False):
            return
        items = self.db.get_all_watchlist()
        a_reparar = []
        for row in items:
            aid, tit = str(row[0]), str(row[1])
            if tit.startswith("Juego Steam") or tit.startswith("AppID") or tit.strip().isdigit():
                a_reparar.append(aid)
        if not a_reparar:
            return
        self._reparando_titulos_wl = True

        def _hilo():
            try:
                datos = self.api_client.obtener_datos_basicos_lote(a_reparar)
                mapa_update = {}
                for aid, d in datos.items():
                    if d and d.get("name") and not d["name"].startswith("Juego Steam"):
                        mapa_update[aid] = d["name"]
                if mapa_update:
                    self.db.update_watchlist_titles_batch(mapa_update)
                    self.after(0, self._renderizar_watchlist)
                    self.after(0, lambda cnt=len(mapa_update): self._show_toast(f"✨ {cnt} nombres de Wishlist restaurados con éxito.", self.palette["accent"]))
            finally:
                self._reparando_titulos_wl = False

        threading.Thread(target=_hilo, daemon=True).start()

    def _renderizar_watchlist(self):
        self._watch_token += 1; token_w = self._watch_token
        self._reparar_titulos_watchlist_en_segundo_plano()
        for w in self.scroll_watchlist.winfo_children(): w.destroy()
        items = self.db.get_all_watchlist(); tags_existentes = {"Todas las etiquetas"}
        for _, _, _, _, _, tag, _ in items:
            if tag: tags_existentes.add(tag)
        filtro_actual = self.combo_watch_filter.get(); self.combo_watch_filter.configure(values=sorted(list(tags_existentes)))
        if filtro_actual not in tags_existentes: self.combo_watch_filter.set("Todas las etiquetas"); filtro_actual = "Todas las etiquetas"
        if not items:
            self._actualizar_resumen_watchlist([])
            ctk.CTkLabel(self.scroll_watchlist, text="Tu Watchlist está vacía.", text_color=self.palette["subtext"], font=("Segoe UI", 13)).pack(pady=20); return
        vista = self.config.datos.get("vista_resultados", "Normal")
        texto_busq = self.entry_watch_search.get().strip().lower() if hasattr(self, 'entry_watch_search') else ""
        items_filtrados = [i for i in items if (filtro_actual == "Todas las etiquetas" or i[5] == filtro_actual) and (not texto_busq or texto_busq in i[1].lower())]
        self._actualizar_resumen_watchlist([i[2] for i in items_filtrados])
        cols = 4 if vista == "Grilla" else 1
        for col in range(cols if vista == "Grilla" else 4): self.scroll_watchlist.grid_columnconfigure(col, weight=1 if vista == "Grilla" or col == 0 else 0)
        notas_mapa = self.db.get_all_game_notes()
        def _dibujar_lote_w(idx=0, batch_size=6):
            if token_w != self._watch_token: return
            fin = min(idx + batch_size, len(items_filtrados))
            for i in range(idx, fin):
                itm = items_filtrados[i]
                aid = str(itm[0])
                card_data = {
                    "appid": aid, "titulo": itm[1], "precio_normal_usd": itm[2], "precio_oferta_usd": itm[2],
                    "descuento": 0, "link": itm[4], "es_atl": False, "es_bug": False, "thumb_url": None,
                    "modalidad": "Guardado", "genero": itm[3], "rating": "N/A", "custom_tag": itm[5],
                    "target_price": float(itm[6] or 0.0),
                    "personal_note": notas_mapa.get(aid, "")
                }
                card = self._crear_tarjeta_juego(self.scroll_watchlist, card_data, es_watchlist=True, vista=vista)
                if vista == "Grilla": card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="nsew")
                else: card.grid(row=i, column=0, padx=8, pady=4, sticky="ew")
            if fin < len(items_filtrados): self.after(12, lambda: _dibujar_lote_w(fin, batch_size))
        _dibujar_lote_w(0)

    def _iniciar_comprobacion_rebajas(self):
        self.sfx.play("click"); self.btn_check_drops.configure(state="disabled")
        self._actualizar_estado("⚡ Comprobando rebajas en lote para tu Watchlist...", "orange")
        threading.Thread(target=self._hilo_comprobar_rebajas, daemon=True).start()

    def _hilo_comprobar_rebajas(self):
        items = self.db.get_all_watchlist()
        if not items:
            self.after(0, lambda: self.btn_check_drops.configure(state="normal"))
            self._actualizar_estado("Tu Watchlist está vacía.", "yellow"); return

        all_ids = [str(it[0]) for it in items]
        precios_lote = self._obtener_precios_argentina_lote(all_ids)
        pares_hist = {
            aid: (d["oferta"], d.get("descuento", 0), d.get("normal", d["oferta"]))
            for aid, d in precios_lote.items() if d.get("oferta", 0) > 0
        }
        res_atl = self.db.update_historical_min_batch(pares_hist) if pares_hist else {}

        nuevos_items = []; rebajas_encontradas = 0; mejor_rebaja_item = None
        for appid, titulo, precio_guardado, fecha, link, tag, target_p in items:
            appid_str = str(appid)
            p_info = precios_lote.get(appid_str)
            p_actual = p_info["oferta"] if p_info else precio_guardado
            p_norm = p_info["normal"] if p_info else precio_guardado
            desc = p_info["descuento"] if p_info else 0
            es_min = res_atl.get(appid_str, False)
            if es_min and p_actual > 0:
                self.db.registrar_alerta_atl(appid_str, titulo, p_actual, desc)
            target_val = float(target_p or 0.0)
            cumple_target = (target_val > 0 and 0 < p_actual <= target_val)
            bajo_precio = (0 < p_actual < precio_guardado) or desc > 0 or cumple_target
            if bajo_precio:
                rebajas_encontradas += 1
            item_dict = {
                "appid": appid_str, "titulo": titulo, "precio_normal_usd": p_norm or precio_guardado,
                "precio_oferta_usd": p_actual, "descuento": desc, "es_atl": es_min, "link": link,
                "bajo_precio": bajo_precio, "thumb_url": None, "modalidad": "Guardado", "genero": fecha,
                "rating": "N/A", "custom_tag": tag, "target_price": target_val
            }
            nuevos_items.append(item_dict)
            if bajo_precio and mejor_rebaja_item is None:
                mejor_rebaja_item = item_dict

        self.after(0, lambda: self._mostrar_watchlist_actualizada(nuevos_items, rebajas_encontradas, mejor_rebaja_item))

    def _mostrar_watchlist_actualizada(self, items, rebajas_encontradas, mejor_rebaja_item=None):
        self._watch_token += 1; token_w = self._watch_token
        for w in self.scroll_watchlist.winfo_children(): w.destroy()
        filtro_actual = self.combo_watch_filter.get(); vista = self.config.datos.get("vista_resultados", "Normal")
        texto_busq = self.entry_watch_search.get().strip().lower() if hasattr(self, 'entry_watch_search') else ""
        items_filtrados = [itm for itm in items if (filtro_actual == "Todas las etiquetas" or itm.get("custom_tag") == filtro_actual) and (not texto_busq or texto_busq in itm.get("titulo", "").lower())]
        self._actualizar_resumen_watchlist([itm["precio_oferta_usd"] for itm in items_filtrados])
        cols = 4 if vista == "Grilla" else 1
        for col in range(cols if vista == "Grilla" else 4): self.scroll_watchlist.grid_columnconfigure(col, weight=1 if vista == "Grilla" or col == 0 else 0)
        def _dibujar_lote_act(idx=0, batch_size=6):
            if token_w != self._watch_token: return
            fin = min(idx + batch_size, len(items_filtrados))
            for i in range(idx, fin):
                itm = items_filtrados[i]
                card = self._crear_tarjeta_juego(self.scroll_watchlist, itm, es_watchlist=True, vista=vista)
                if vista == "Grilla": card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="nsew")
                else: card.grid(row=i, column=0, padx=8, pady=4, sticky="ew")
            if fin < len(items_filtrados): self.after(12, lambda: _dibujar_lote_act(fin, batch_size))
        _dibujar_lote_act(0)
        self.btn_check_drops.configure(state="normal")
        if rebajas_encontradas > 0:
            self.sfx.play("atl"); self._actualizar_estado(f"⚡ ¡Se encontraron {rebajas_encontradas} juego(s) en oferta o en tu precio objetivo!", "#00e676")
            notificar_windows("¡Rebajas en Watchlist!", f"¡{rebajas_encontradas} juego(s) de tu Watchlist están en oferta!")
            if mejor_rebaja_item:
                p_usd = float(mejor_rebaja_item.get("precio_oferta_usd", 0.0))
                p_ars = self.calcular_precio_ars(p_usd, "ARS (Tarjeta)")
                aid = str(mejor_rebaja_item.get("appid", ""))
                notificar_oferta_enriquecida(
                    titulo=mejor_rebaja_item.get("titulo", "Juego en Oferta"),
                    precio_usd=p_usd,
                    descuento=int(mejor_rebaja_item.get("descuento", 0)),
                    precio_ars=p_ars,
                    banner_url=f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg" if aid else None,
                    appid=aid,
                    es_gratis=(p_usd == 0)
                )
                self.after(0, lambda it=mejor_rebaja_item, m=f"{mejor_rebaja_item['titulo']} está a ${mejor_rebaja_item['precio_oferta_usd']:.2f} USD": DialogoAlertaInteractiva(self, "¡Rebaja en tu Watchlist!", m, it))
        else: self._actualizar_estado("⚡ Precios verificados en lote: todo al día.", self.palette["accent"])

    def _daemon_monitoreo_watchlist(self):
        time.sleep(30)
        while True:
            try:
                items = self.db.get_all_watchlist(); umbral = self.config.datos.get("umbral_alerta_pct", 50)
                if items:
                    all_ids = [str(it[0]) for it in items]
                    precios_lote = self._obtener_precios_argentina_lote(all_ids)
                    pares_hist = {
                        aid: (d["oferta"], d.get("descuento", 0), d.get("normal", d["oferta"]))
                        for aid, d in precios_lote.items() if d.get("oferta", 0) > 0
                    }
                    res_atl = self.db.update_historical_min_batch(pares_hist) if pares_hist else {}
                    bajaron = []; item_destacado = None
                    for appid, titulo, p_guardado, fecha, link, tag, target_p in items:
                        appid_str = str(appid)
                        p_data = precios_lote.get(appid_str)
                        if not p_data:
                            continue
                        p_fin = p_data.get("oferta", 0.0)
                        desc_pct = p_data.get("descuento", 0)
                        target_val = float(target_p or 0.0)
                        if desc_pct >= umbral or (target_val > 0 and 0 < p_fin <= target_val):
                            bajaron.append(f"{titulo} (-{desc_pct}%)" if desc_pct > 0 else f"{titulo} (${p_fin:.2f})")
                            es_min = res_atl.get(appid_str, False)
                            if es_min and p_fin > 0:
                                self.db.registrar_alerta_atl(appid_str, titulo, p_fin, desc_pct)
                            if item_destacado is None:
                                item_destacado = {"appid": appid_str, "titulo": titulo, "precio_normal_usd": p_guardado, "precio_oferta_usd": p_fin, "descuento": desc_pct, "es_atl": es_min, "link": link}
                    if bajaron:
                        self.sfx.play("atl")
                        msg = f"Superaron tu alerta o precio objetivo: {', '.join(bajaron[:2])}"
                        notificar_windows("🚨 ¡SUPER OFERTAS EN WATCHLIST!", msg)
                        if item_destacado:
                            p_usd = float(item_destacado.get("precio_oferta_usd", 0.0))
                            p_ars = self.calcular_precio_ars(p_usd, "ARS (Tarjeta)")
                            aid = str(item_destacado.get("appid", ""))
                            notificar_oferta_enriquecida(
                                titulo=item_destacado.get("titulo", "Juego en Oferta"),
                                precio_usd=p_usd,
                                descuento=int(item_destacado.get("descuento", 0)),
                                precio_ars=p_ars,
                                banner_url=f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg" if aid else None,
                                appid=aid,
                                es_gratis=(p_usd == 0)
                            )
                            self.after(0, lambda it=item_destacado, m=msg: DialogoAlertaInteractiva(self, "🚨 ¡Super Oferta Detectada!", m, it))
            except: pass
            time.sleep(10800)

    def _bloquear_botones(self):
        self.btn_search_smart.configure(state="disabled")
        self.combo_exportar.configure(state="disabled")
        if hasattr(self, "scan_progress"):
            self.scan_progress.pack(fill="x", padx=14, pady=(0, 4), after=self.subbar)
            self.scan_progress.start()

    def _desbloquear_botones(self):
        self.btn_search_smart.configure(state="normal")
        self.combo_exportar.configure(state="normal")
        if hasattr(self, "scan_progress"):
            self.scan_progress.stop()
            self.scan_progress.pack_forget()
    def _actualizar_estado(self, txt, col): self.lbl_status.configure(text=txt, text_color=col)

    def _exportar_pdf(self):
        self.exporter.exportar_pdf()

    def _exportar_excel(self):
        self.exporter.exportar_excel()

if __name__ == "__main__":
    app = SteamScopeApp()
    app.mainloop()