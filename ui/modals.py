import os
import re
import html
import time
import shutil
import random
import tempfile
import threading
import subprocess
import webbrowser
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps
from tkinter import ttk, filedialog
import customtkinter as ctk

from core.config import (
    APP_VERSION,
    APP_NAME,
    UPDATE_JSON_URL,
    GITHUB_API_RELEASES,
    FALLBACK_RELEASES_WEB,
    PATCH_NOTES,
    STEAM_CALENDAR,
    obtener_ruta_appdata,
    limpiar_cache_imagenes,
)
from core.filters import normalizar_texto
from core.api_client import HTTP_SESSION, consultar_dolar_api
from core.pricing import (
    limpiar_html,
    extraer_espacio_disco,
    calcular_tiempo_restante,
    _parse_version_tuple,
    detectar_suscripcion,
    evaluar_termometro_compra,
)
from core.multi_store import obtener_promociones_epic
from core.cards_manager import analizar_inventario_cromos
from ui.charts import DialogoGraficoHistorico


def color_luminance(hex_col):
    """Calcula la luminancia relativa estricta según la norma WCAG 2.1."""
    if not hex_col or not isinstance(hex_col, str):
        return 0.5
    h = hex_col.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        try:
            r = int(h[0:2], 16) / 255.0
            g = int(h[2:4], 16) / 255.0
            b = int(h[4:6], 16) / 255.0

            def _gamma(c):
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

            return 0.2126 * _gamma(r) + 0.7152 * _gamma(g) + 0.0722 * _gamma(b)
        except Exception:
            return 0.5
    return 0.5


def texto_contraste_color(hex_col):
    """Retorna 'black' si el fondo es claro/brillante (luminancia > 0.45), o 'white' si es oscuro."""
    return "black" if color_luminance(hex_col) > 0.45 else "white"


def texto_contraste_acento(pal):
    """Garantiza legibilidad matemática sobre el color accent de la paleta."""
    return texto_contraste_color(pal.get("accent", "#1f538d"))


class DialogoMensajeSkin(ctk.CTkToplevel):
    """Reemplazo 100% skin-aware para messagebox (info, warning, error, askyesno)."""
    def __init__(self, parent, titulo, mensaje, tipo="info", texto_ok="Aceptar", texto_cancel="Cancelar"):
        super().__init__(parent)
        pal = getattr(parent, "palette", None) or getattr(getattr(parent, "parent_app", None), "palette", {})
        self.resultado = False
        self.title(titulo)
        self.geometry("450x235")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal.get("win_bg", "#191a21"))

        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 225
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 118
            self.geometry(f"+{max(40, x)}+{max(40, y)}")
        except Exception:
            pass

        colores_tipo = {
            "info": pal.get("accent", "#00f0ff"),
            "warning": "#ffab00",
            "error": "#ff5252",
            "question": pal.get("accent", "#00f0ff"),
        }
        iconos_tipo = {
            "info": "💡",
            "warning": "⚠️",
            "error": "❌",
            "question": "❓",
        }
        borde_col = colores_tipo.get(tipo, pal.get("accent", "#00f0ff"))
        icono = iconos_tipo.get(tipo, "💡")

        card = ctk.CTkFrame(self, fg_color=pal.get("card_bg", "#282a36"), corner_radius=12, border_width=2, border_color=borde_col)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(hdr, text=f"{icono}  {titulo}", font=("Segoe UI", 14, "bold"), text_color=borde_col, anchor="w").pack(side="left")

        ctk.CTkLabel(
            card, text=mensaje, font=("Segoe UI", 12), text_color=pal.get("text", "#f8fafc"),
            justify="left", anchor="w", wraplength=390
        ).pack(fill="both", expand=True, padx=18, pady=(2, 8))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 14))

        fg_ok = "black" if borde_col in ("#00f0ff", "#39ff14", "#fcee0a", "#1a9fff", "#ff7518", "#ffab00", "#00e676") else "white"
        if tipo == "question":
            ctk.CTkButton(
                btn_row, text=texto_cancel, width=110, height=32,
                fg_color=pal.get("panel_bg", "#21222c"), hover_color=pal.get("card_hover", "#343746"),
                border_width=1, border_color=pal.get("border", "#6272a4"), text_color=pal.get("text", "#ffffff"),
                font=("Segoe UI", 12, "bold"), command=self._cancelar
            ).pack(side="right", padx=(6, 0))
            ctk.CTkButton(
                btn_row, text=texto_ok, width=120, height=32,
                fg_color=borde_col, hover_color=pal.get("accent_2", borde_col), text_color=fg_ok,
                font=("Segoe UI", 12, "bold"), command=self._confirmar
            ).pack(side="right")
        else:
            ctk.CTkButton(
                btn_row, text=texto_ok, width=120, height=32,
                fg_color=borde_col, hover_color=pal.get("accent_2", borde_col), text_color=fg_ok,
                font=("Segoe UI", 12, "bold"), command=self._confirmar
            ).pack(side="right")

        self.bind("<Return>", lambda e: self._confirmar())
        self.bind("<Escape>", lambda e: self._cancelar())

    def _confirmar(self):
        self.resultado = True
        self.destroy()

    def _cancelar(self):
        self.resultado = False
        self.destroy()


class DialogoInputSkin(ctk.CTkToplevel):
    """Reemplazo 100% skin-aware para simpledialog (askstring / askfloat / askinteger)."""
    def __init__(self, parent, titulo, prompt, valor_inicial="", modo="str", min_val=None, max_val=None):
        super().__init__(parent)
        pal = getattr(parent, "palette", None) or getattr(getattr(parent, "parent_app", None), "palette", {})
        self.valor = None
        self.modo = modo
        self.min_val = min_val
        self.max_val = max_val
        self.title(titulo)
        self.geometry("430x225")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal.get("win_bg", "#191a21"))

        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 215
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 112
            self.geometry(f"+{max(40, x)}+{max(40, y)}")
        except Exception:
            pass

        acento = pal.get("accent", "#00f0ff")
        card = ctk.CTkFrame(self, fg_color=pal.get("card_bg", "#282a36"), corner_radius=12, border_width=2, border_color=acento)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(card, text=titulo, font=("Segoe UI", 14, "bold"), text_color=acento, anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(card, text=prompt, font=("Segoe UI", 11), text_color=pal.get("text", "#ffffff"), justify="left", anchor="w", wraplength=380).pack(fill="x", padx=16, pady=(0, 8))

        self.entry = ctk.CTkEntry(
            card, width=360, height=32, font=("Consolas", 13, "bold"),
            fg_color=pal.get("price_bg", "#121418"), text_color=pal.get("text", "#ffffff"),
            border_color=acento, border_width=1
        )
        self.entry.pack(padx=16, pady=(0, 10))
        if valor_inicial is not None and str(valor_inicial) != "":
            self.entry.insert(0, str(valor_inicial))
            self.entry.select_range(0, "end")
        self.after(60, self.entry.focus_set)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        fg_ok = texto_contraste_acento(pal)
        ctk.CTkButton(
            btn_row, text="Cancelar", width=100, height=30,
            fg_color=pal.get("panel_bg", "#21222c"), hover_color=pal.get("card_hover", "#343746"),
            border_width=1, border_color=pal.get("border", "#6272a4"), text_color=pal.get("text", "#ffffff"),
            font=("Segoe UI", 11, "bold"), command=self._cancelar
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            btn_row, text="Confirmar", width=110, height=30,
            fg_color=acento, hover_color=pal.get("accent_2", acento), text_color=fg_ok,
            font=("Segoe UI", 11, "bold"), command=self._aceptar
        ).pack(side="right")

        self.bind("<Return>", lambda e: self._aceptar())
        self.bind("<Escape>", lambda e: self._cancelar())

    def _aceptar(self):
        raw = self.entry.get().strip()
        if self.modo == "int":
            try:
                v = int(raw)
                if self.min_val is not None and v < self.min_val:
                    return
                if self.max_val is not None and v > self.max_val:
                    return
                self.valor = v
            except ValueError:
                return
        elif self.modo == "float":
            try:
                v = float(raw.replace(",", "."))
                if self.min_val is not None and v < self.min_val:
                    return
                if self.max_val is not None and v > self.max_val:
                    return
                self.valor = v
            except ValueError:
                return
        else:
            self.valor = raw
        self.destroy()

    def _cancelar(self):
        self.valor = None
        self.destroy()


def mostrar_alerta_skin(parent, titulo, mensaje, tipo="info"):
    dlg = DialogoMensajeSkin(parent, titulo, mensaje, tipo=tipo)
    parent.wait_window(dlg)
    return dlg.resultado


def preguntar_si_no_skin(parent, titulo, mensaje, texto_ok="Sí", texto_cancel="No"):
    dlg = DialogoMensajeSkin(parent, titulo, mensaje, tipo="question", texto_ok=texto_ok, texto_cancel=texto_cancel)
    parent.wait_window(dlg)
    return dlg.resultado


def pedir_input_skin(parent, titulo, prompt, valor_inicial="", modo="str", min_val=None, max_val=None, valor_defecto=None):
    if valor_defecto is not None and not valor_inicial:
        valor_inicial = valor_defecto
    dlg = DialogoInputSkin(parent, titulo, prompt, valor_inicial=valor_inicial, modo=modo, min_val=min_val, max_val=max_val)
    parent.wait_window(dlg)
    try:
        if parent.winfo_exists():
            parent.grab_set()
    except Exception:
        pass
    return dlg.valor


class DialogoAlertaInteractiva(ctk.CTkToplevel):
    """Popup flotante en escritorio para alertas de rebaja interactivas (SRP)."""
    def __init__(self, parent, titulo_alerta, mensaje, item_juego=None):
        super().__init__(parent)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.parent_app = parent
        self.item_juego = item_juego
        pal = parent.palette

        w, h = 370, 110
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{sw - w - 22}+{sh - h - 58}")
        self.configure(fg_color=pal["win_bg"])

        card = ctk.CTkFrame(self, fg_color=pal["card_bg"], corner_radius=10, border_width=2, border_color=pal["accent"])
        card.pack(fill="both", expand=True, padx=2, pady=2)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(top, text=f"🔔 {titulo_alerta}", font=("Segoe UI", 12, "bold"), text_color=pal["accent"]).pack(side="left")
        ctk.CTkButton(top, text="✕", width=22, height=20, fg_color="transparent", hover_color="#b71c1c", text_color=pal["subtext"], command=self.destroy).pack(side="right")

        lbl_msg = ctk.CTkLabel(card, text=mensaje, font=("Segoe UI", 11), text_color=pal["text"], justify="left", anchor="w", wraplength=340, cursor="hand2")
        lbl_msg.pack(fill="x", padx=12, pady=(0, 2))

        lbl_cta = ctk.CTkLabel(card, text="👉 Hacé clic acá para abrir la Ficha Técnica", font=("Consolas", 10, "bold"), text_color="#00e676", cursor="hand2")
        lbl_cta.pack(anchor="w", padx=12, pady=(0, 6))

        for widget in (card, lbl_msg, lbl_cta):
            widget.bind("<Button-1>", self._al_hacer_clic)

        self.after(9000, lambda: self.destroy() if self.winfo_exists() else None)

    def _al_hacer_clic(self, event=None):
        self.parent_app.tray.mostrar_ventana()
        if self.item_juego:
            self.parent_app.after(200, lambda: DialogoFichaJuego(self.parent_app, self.item_juego["appid"], self.item_juego["titulo"], self.item_juego))
        if self.winfo_exists():
            self.destroy()


class DialogoPatchNotes(ctk.CTkToplevel):
    """Ventana modal de historial de versiones (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        pal = parent.palette
        self.title(f"Historial de Versiones | {APP_NAME}")
        self.geometry("620x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 310
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 260
        self.geometry(f"+{x}+{y}")

        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=20, pady=(15, 8))
        ctk.CTkLabel(top_frame, text="📜 Registro de Actualizaciones", font=("Arial", 16, "bold"), text_color=pal["text"]).pack(side="left")
        ctk.CTkLabel(top_frame, text=f"Actual: v{APP_VERSION}", font=("Arial", 11, "bold"), text_color=pal["accent"]).pack(side="right")

        scroll_notes = ctk.CTkScrollableFrame(self, corner_radius=10, fg_color=pal["panel_bg"])
        scroll_notes.pack(fill="both", expand=True, padx=20, pady=(5, 12))

        for item in PATCH_NOTES:
            box_ver = ctk.CTkFrame(scroll_notes, corner_radius=8, fg_color=pal["card_bg"], border_width=1, border_color=pal["border"])
            box_ver.pack(fill="x", pady=6, padx=4)
            header_row = ctk.CTkFrame(box_ver, fg_color="transparent")
            header_row.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(header_row, text=f"Versión {item['version']}", font=("Arial", 13, "bold"), text_color=pal["accent"]).pack(side="left")
            ctk.CTkLabel(header_row, text=item["fecha"], font=("Arial", 11), text_color=pal["subtext"]).pack(side="right")

            body_frame = ctk.CTkFrame(box_ver, fg_color="transparent")
            body_frame.pack(fill="x", padx=12, pady=(4, 10))
            for cambio in item["cambios"]:
                ctk.CTkLabel(body_frame, text=f"• {cambio}", font=("Arial", 11), text_color=pal["text"], justify="left", anchor="w", wraplength=520).pack(anchor="w", pady=2)

        ctk.CTkButton(self, text="Entendido", width=120, height=30, fg_color=pal["accent"], hover_color=pal["accent_2"], text_color=texto_contraste_acento(pal), command=self.destroy).pack(pady=(0, 15))


def abrir_ventana_ofertas(parent, config_manager):
    """Abre el calendario oficial de rebajas de Steam y calculadora multi-moneda."""
    pal = parent.palette
    modal = ctk.CTkToplevel(parent)
    modal.title(f"{APP_NAME} - Eventos Steam & Calculadora")
    modal.geometry("670x610")
    modal.resizable(False, False)
    modal.transient(parent)
    modal.grab_set()
    modal.configure(fg_color=pal["win_bg"])

    now = datetime.now(timezone.utc)

    frame_top = ctk.CTkFrame(modal, fg_color="transparent")
    frame_top.pack(fill="x", padx=15, pady=(15, 5))
    ctk.CTkLabel(frame_top, text="📅 Calendario Oficial de Rebajas Steam", font=("Arial", 14, "bold"), text_color=pal["text"]).pack(side="left")

    filtro_var = ctk.StringVar(value="Todas")
    cb_filtro = ctk.CTkOptionMenu(
        frame_top, variable=filtro_var, values=["Todas", "Solo Grandes Rebajas", "Solo Temáticos"], width=190,
        command=lambda v: refrescar_tabla(),
        fg_color=pal["card_bg"], button_color=pal["accent"], button_hover_color=pal["accent_2"], text_color=pal["text"]
    )
    cb_filtro.pack(side="right")

    style = ttk.Style()
    style.theme_use("default")
    style.configure("Treeview", background=pal["card_bg"], foreground=pal["text"], rowheight=25, fieldbackground=pal["card_bg"], borderwidth=0)
    style.map('Treeview', background=[('selected', pal["accent"])], foreground=[('selected', texto_contraste_acento(pal))])
    style.configure("Treeview.Heading", background=pal["panel_bg"], foreground=pal["accent"], relief="flat", font=("Segoe UI", 10, "bold"))
    style.map("Treeview.Heading", background=[('active', pal["card_hover"])])

    frame_tabla = ctk.CTkFrame(modal, fg_color=pal["card_bg"], border_width=1, border_color=pal["border"])
    frame_tabla.pack(fill="both", expand=True, padx=15, pady=5)

    cols = ("evento", "tipo", "fechas", "estado")
    tree = ttk.Treeview(frame_tabla, columns=cols, show="headings", height=6, selectmode="browse")
    tree.heading("evento", text="Evento")
    tree.column("evento", width=200, anchor="w")
    tree.heading("tipo", text="Tipo")
    tree.column("tipo", width=90, anchor="center")
    tree.heading("fechas", text="Ventana")
    tree.column("fechas", width=160, anchor="center")
    tree.heading("estado", text="Estado / Faltan")
    tree.column("estado", width=150, anchor="center")
    tree.pack(fill="both", expand=True, padx=2, pady=2)

    def refrescar_tabla():
        tree.delete(*tree.get_children())
        filtro = filtro_var.get()
        for ev in STEAM_CALENDAR:
            if filtro == "Solo Grandes Rebajas" and ev["type"] != "Major":
                continue
            if filtro == "Solo Temáticos" and ev["type"] != "Themed":
                continue

            start = datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(ev["end"].replace("Z", "+00:00"))
            rango = f"{start.strftime('%d/%m/%y')} - {end.strftime('%d/%m/%y')}"
            tipo_str = "Principal" if ev["type"] == "Major" else "Temático"

            if start <= now <= end:
                rem = end - now
                estado = f"🔥 ¡ACTIVA! ({rem.days}d {rem.seconds // 3600}h)"
            elif start > now:
                delta = start - now
                estado = f"En {delta.days} días"
            else:
                estado = "Finalizada"
            tree.insert("", "end", values=(ev["name"], tipo_str, rango, estado))

    refrescar_tabla()

    frame_link = ctk.CTkFrame(modal, fg_color="transparent")
    frame_link.pack(fill="x", padx=15, pady=(5, 8))
    ctk.CTkButton(frame_link, text="🌐 Abrir Steam Store en el Navegador", width=240, fg_color=pal["accent"], text_color=texto_contraste_acento(pal), command=lambda: webbrowser.open("https://store.steampowered.com")).pack(side="left")
    ctk.CTkLabel(frame_link, text="* Las ofertas comienzan a las 14:00 (ARG)", font=("Arial", 11, "italic"), text_color=pal["subtext"]).pack(side="right", padx=5)

    frame_calc = ctk.CTkFrame(modal, corner_radius=8, fg_color=pal["panel_bg"])
    frame_calc.pack(fill="x", padx=15, pady=8)

    top_calc_row = ctk.CTkFrame(frame_calc, fg_color="transparent")
    top_calc_row.pack(fill="x", padx=10, pady=(10, 0))
    ctk.CTkLabel(top_calc_row, text=" 🧮 Calculadora de Precios y Medios de Pago ", font=("Arial", 12, "bold"), text_color=pal["text"]).pack(side="left")

    f_inputs = ctk.CTkFrame(frame_calc, fg_color="transparent")
    f_inputs.pack(fill="x", pady=(8, 5), padx=10)

    ctk.CTkLabel(f_inputs, text="USD:", text_color=pal["text"]).pack(side="left", padx=(0, 2))
    entry_usd = ctk.CTkEntry(f_inputs, width=70, fg_color=pal["card_bg"], text_color=pal["text"])
    entry_usd.pack(side="left", padx=4)
    entry_usd.insert(0, "19.99")

    ctk.CTkLabel(f_inputs, text="Dólar:", text_color=pal["text"]).pack(side="left", padx=(6, 2))
    entry_cotiz = ctk.CTkEntry(f_inputs, width=75, fg_color=pal["card_bg"], text_color=pal["text"])
    entry_cotiz.pack(side="left", padx=4)
    entry_cotiz.insert(0, str(config_manager.datos.get("dolar_referencia", 1000.0)))

    def _act_dolar_tarj():
        val = consultar_dolar_api("oficial")
        if val:
            modal.after(0, lambda: (entry_cotiz.delete(0, "end"), entry_cotiz.insert(0, str(val)), entry_imp.delete(0, "end"), entry_imp.insert(0, "60"), calcular_ars()))

    def _act_dolar_wallet():
        val = consultar_dolar_api("oficial") or float(entry_cotiz.get() or 1000)
        modal.after(0, lambda: (entry_cotiz.delete(0, "end"), entry_cotiz.insert(0, str(val)), entry_imp.delete(0, "end"), entry_imp.insert(0, "0"), calcular_ars()))

    def _act_cripto_calc():
        val = consultar_dolar_api("cripto")
        if val:
            config_manager.guardar_basico("dolar_cripto_ref", val)
            modal.after(0, lambda: (entry_cotiz.delete(0, "end"), entry_cotiz.insert(0, str(val)), entry_imp.delete(0, "end"), entry_imp.insert(0, "0"), calcular_ars()))

    ctk.CTkButton(f_inputs, text="💳 Tarj (+60%)", width=82, fg_color=pal["accent"], text_color=texto_contraste_acento(pal), hover_color=pal["accent_2"], font=("Segoe UI", 10, "bold"), command=lambda: threading.Thread(target=_act_dolar_tarj, daemon=True).start()).pack(side="left", padx=2)
    ctk.CTkButton(f_inputs, text="👛 Wallet (0%)", width=80, fg_color=pal["accent_2"], text_color="white", font=("Segoe UI", 10, "bold"), command=lambda: threading.Thread(target=_act_dolar_wallet, daemon=True).start()).pack(side="left", padx=2)
    ctk.CTkButton(f_inputs, text="🪙 Cripto", width=62, fg_color=pal["card_bg"], border_width=1, border_color=pal["accent"], text_color=pal["accent"], hover_color=pal["card_hover"], font=("Segoe UI", 10, "bold"), command=lambda: threading.Thread(target=_act_cripto_calc, daemon=True).start()).pack(side="left", padx=2)

    ctk.CTkLabel(f_inputs, text="Imp %:", text_color=pal["text"]).pack(side="left", padx=(4, 2))
    entry_imp = ctk.CTkEntry(f_inputs, width=42, fg_color=pal["card_bg"], text_color=pal["text"])
    entry_imp.pack(side="left", padx=2)
    entry_imp.insert(0, str(config_manager.datos.get("impuestos_pct", 60)))

    lbl_resultado = ctk.CTkLabel(frame_calc, text="Total estimado: $0,00 ARS", font=("Arial", 13, "bold"), text_color=pal["accent"])
    lbl_resultado.pack(anchor="w", padx=12, pady=(6, 12))

    def calcular_ars(*args):
        try:
            usd = float(entry_usd.get().replace(",", "."))
            cotiz = float(entry_cotiz.get().replace(",", "."))
            imp = float(entry_imp.get().replace(",", "."))
            total = usd * cotiz * (1 + (imp / 100))
            lbl_resultado.configure(text=f"Total estimado: ${total:,.2f} ARS".replace(",", "X").replace(".", ",").replace("X", "."))
        except Exception:
            lbl_resultado.configure(text="Ingrese valores numéricos válidos.")

    entry_usd.bind("<KeyRelease>", calcular_ars)
    entry_cotiz.bind("<KeyRelease>", calcular_ars)
    entry_imp.bind("<KeyRelease>", calcular_ars)
    calcular_ars()

    ctk.CTkButton(modal, text="Cerrar", width=120, fg_color=pal["border"], text_color=pal["text"], hover_color=pal["card_hover"], command=modal.destroy).pack(anchor="e", padx=15, pady=(4, 12))


class DialogoCarrito(ctk.CTkToplevel):
    """Simulador de presupuesto (Changuito de compras) (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"🛒 Mi Changuito de Compras - {APP_NAME}")
        self.geometry("680x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.parent_app = parent

        pal = parent.palette
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 340
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 260
        self.geometry(f"+{x}+{y}")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 8))
        ctk.CTkLabel(top, text="🛒 Simulador de Presupuesto (Changuito)", font=("Segoe UI", 16, "bold"), text_color=pal["accent"]).pack(side="left")
        ctk.CTkButton(top, text="🗑 Vaciar Carrito", width=115, height=28, fg_color="#b71c1c", hover_color="#d32f2f", command=self._vaciar).pack(side="right", padx=(6, 0))
        ctk.CTkButton(top, text="🃏 Fondear con Cromos", width=145, height=28, fg_color="#673ab7", hover_color="#512da8", text_color="white", command=lambda: DialogoGestorCromos(self.parent_app)).pack(side="right", padx=6)
        ctk.CTkButton(top, text="📸 Exportar PNG", width=125, height=28, fg_color=pal["accent_2"], hover_color=pal["accent"], text_color="white", command=self.parent_app._exportar_presupuesto_png).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=8, fg_color=pal["panel_bg"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=6)

        self.resumen_frame = ctk.CTkFrame(self, fg_color=pal["card_bg"], corner_radius=8, border_width=1, border_color=pal["border"])
        self.resumen_frame.pack(fill="x", padx=20, pady=(6, 15))

        self.lbl_totales = ctk.CTkLabel(self.resumen_frame, text="", font=("Consolas", 12, "bold"), text_color=pal["text"], justify="left")
        self.lbl_totales.pack(side="left", padx=15, pady=12)

        ctk.CTkButton(self.resumen_frame, text="Cerrar", width=90, fg_color=pal["accent"], text_color=texto_contraste_acento(pal), command=self.destroy).pack(side="right", padx=15, pady=12)

        self._render_items()

    def _render_items(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        pal = self.parent_app.palette
        items = list(self.parent_app.carrito.values())

        if not items:
            ctk.CTkLabel(self.scroll, text="Tu changuito está vacío.\nTocá el botón '🛒+' en cualquier tarjeta para simular tu compra.", font=("Segoe UI", 13), text_color=pal["subtext"]).pack(pady=60)
            self.lbl_totales.configure(text="Total USD: $0.00  |  Total Final ARS: $0")
            return

        dolar = self.parent_app.config.datos.get("dolar_referencia", 1000.0)
        imp = self.parent_app.config.datos.get("impuestos_pct", 60)
        dolar_cripto = self.parent_app.config.datos.get("dolar_cripto_ref", round(dolar * 1.15))
        mult = 1 + (imp / 100.0)

        total_usd = 0.0
        ahorro_usd = 0.0

        for itm in items:
            p_usd = itm.get("precio_oferta_usd", 0.0)
            p_norm = itm.get("precio_normal_usd", p_usd)
            total_usd += p_usd
            if p_norm > p_usd:
                ahorro_usd += (p_norm - p_usd)

            p_ars = round(p_usd * dolar * mult)
            row = ctk.CTkFrame(self.scroll, fg_color=pal["card_bg"], corner_radius=6, border_width=1, border_color=pal["border"])
            row.pack(fill="x", pady=3, padx=4)

            ctk.CTkLabel(row, text=itm.get("titulo", "Juego")[:42], font=("Segoe UI", 12, "bold"), text_color=pal["text"]).pack(side="left", padx=10, pady=8)
            ctk.CTkButton(row, text="✕", width=28, height=24, fg_color="#b71c1c", command=lambda a=itm["appid"]: self._quitar(a)).pack(side="right", padx=8)
            ctk.CTkLabel(row, text=f"${p_usd:.2f} USD  (${p_ars:,.0f} ARS)", font=("Consolas", 12, "bold"), text_color=pal["accent"]).pack(side="right", padx=10)

        total_ars = round(total_usd * dolar * mult)
        total_wallet = round(total_usd * dolar)
        total_cripto_ars = round(total_usd * dolar_cripto)
        diff_cripto = total_ars - total_cripto_ars
        ahorro_ars = round(ahorro_usd * dolar * mult)
        pct_ahorro = round((ahorro_usd / (total_usd + ahorro_usd)) * 100) if (total_usd + ahorro_usd) > 0 else 0
        tag_ahorro = f"  •  🎉 ¡Ahorrás ${ahorro_usd:.2f} USD (~${ahorro_ars:,.0f} ARS, {pct_ahorro}% OFF)!" if ahorro_usd > 0 else ""

        texto_res = (
            f"Juegos: {len(items)}   |   Total: ${total_usd:.2f} USD{tag_ahorro}\n"
            f"💳 Tarjeta (+{imp}%): ${total_ars:,.0f} ARS   |   👛 Cartera Steam (0%): ${total_wallet:,.0f} ARS\n"
            f"🪙 Cripto: ${total_cripto_ars:,.0f} ARS" + (f" (Ahorro Cripto: ${diff_cripto:,.0f})" if diff_cripto > 0 else "")
        )
        self.lbl_totales.configure(text=texto_res)

    def _quitar(self, appid):
        self.parent_app._toggle_carrito_item({"appid": appid, "titulo": ""})
        self._render_items()

    def _vaciar(self):
        self.parent_app._vaciar_carrito()
        self._render_items()


class DialogoRuleta(ctk.CTkToplevel):
    """Modal interactivo de recomendación por sorteo (Loot Box) con giro in-place continuo (SRP)."""
    def __init__(self, parent, item_inicial, modo="deals"):
        super().__init__(parent)
        self.parent_app = parent
        self.modo = modo  # "deals" o "backlog"
        self.item_final = item_inicial
        self._animando = False
        self.parent_app._ruleta_activa = self

        self.title("🎲 ¡Ruleta SteamScope!" if modo != "backlog" else "🎲 ¡Ruleta de Backlog SteamScope!")
        self.geometry("500x530")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        pal = parent.palette
        self.configure(fg_color=pal["win_bg"])

        try:
            x = parent.winfo_x() + (parent.winfo_width() // 2) - 250
            y = parent.winfo_y() + (parent.winfo_height() // 2) - 265
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self._cerrar_ruleta)
        self.bind("<Escape>", lambda e: self._cerrar_ruleta())

        self.lbl_head = ctk.CTkLabel(
            self,
            text="🎲 SORTEANDO RECOMENDACIÓN..." if modo != "backlog" else "🎲 SORTEANDO TU BACKLOG...",
            font=("Segoe UI", 16, "bold"), text_color=pal["accent"]
        )
        self.lbl_head.pack(pady=(16, 6))

        self.card_box = ctk.CTkFrame(self, fg_color=pal["card_bg"], corner_radius=12, border_width=2, border_color=pal["accent"])
        self.card_box.pack(fill="both", expand=True, padx=24, pady=8)

        self.lbl_img = ctk.CTkLabel(self.card_box, text="", image=parent.placeholder_grid)
        self.lbl_img.pack(pady=(12, 6))

        self.lbl_titulo = ctk.CTkLabel(self.card_box, text="???", font=("Segoe UI", 15, "bold"), text_color=pal["text"], wraplength=420)
        self.lbl_titulo.pack(padx=12, pady=2)

        self.lbl_desc = ctk.CTkLabel(self.card_box, text="---", font=("Consolas", 15, "bold"), text_color="#00e676")
        self.lbl_desc.pack(pady=4)

        self.lbl_term = ctk.CTkLabel(self.card_box, text="", font=("Consolas", 11), text_color=pal["subtext"], justify="center")
        self.lbl_term.pack(padx=12, pady=4)

        self.btn_row = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_row.pack(fill="x", padx=24, pady=12)

        self.btn_reintentar = ctk.CTkButton(
            self.btn_row, text="🎲 Tirar de Nuevo", width=135,
            fg_color=pal["accent_2"], text_color=texto_contraste_color(pal["accent_2"]), state="disabled", command=self.girar_de_nuevo
        )
        self.btn_reintentar.pack(side="left", padx=4)

        self.btn_cart = ctk.CTkButton(
            self.btn_row, text="🛒 Sumar al Carrito" if modo != "backlog" else "🖥️ Ver Ficha",
            width=140, fg_color=pal["accent"], text_color=texto_contraste_acento(pal),
            state="disabled", command=self._accion_boton_medio
        )
        self.btn_cart.pack(side="left", padx=4)

        self.btn_steam = ctk.CTkButton(
            self.btn_row, text="🚀 Abrir Steam" if modo != "backlog" else "🚀 Lanzar Juego",
            width=125, fg_color=pal["card_bg"], border_width=1, border_color=pal["accent"],
            text_color=pal["accent"], hover_color=pal["card_hover"], state="disabled", command=self._accion_boton_derecha
        )
        self.btn_steam.pack(side="right", padx=4)

        self._iniciar_animacion_lootbox()

    def _cerrar_ruleta(self):
        if hasattr(self.parent_app, "_ruleta_activa") and self.parent_app._ruleta_activa == self:
            self.parent_app._ruleta_activa = None
        self.destroy()

    def girar_de_nuevo(self, nuevo_item=None):
        if self._animando:
            return
        if nuevo_item is not None:
            self.item_final = nuevo_item
        else:
            aid_actual = self.item_final.get("appid") if isinstance(self.item_final, dict) else None
            if hasattr(self.parent_app, "_obtener_siguiente_item_ruleta"):
                item_prox = self.parent_app._obtener_siguiente_item_ruleta(modo=self.modo, appid_actual=aid_actual)
                if item_prox:
                    self.item_final = item_prox
            else:
                if self.modo == "backlog":
                    cands = [j for j in (self.parent_app.biblioteca_data or []) if str(j.get("appid")) != str(aid_actual)]
                    sin_jugar = [j for j in cands if j.get("horas", 0) < 0.5]
                    pool = sin_jugar if sin_jugar else cands
                    if pool:
                        self.item_final = random.choice(pool)
                else:
                    fuente = self.parent_app.deals_filtradas or self.parent_app.deals_data or getattr(self.parent_app, "_ruleta_deals_pool", [])
                    cands = [d for d in fuente if str(d.get("appid")) != str(aid_actual)]
                    if cands:
                        self.item_final = random.choice(cands)

        pal = self.parent_app.palette
        self.btn_reintentar.configure(state="disabled")
        self.btn_cart.configure(state="disabled")
        self.btn_steam.configure(state="disabled")
        self.lbl_head.configure(
            text="🎲 SORTEANDO RECOMENDACIÓN..." if self.modo != "backlog" else "🎲 SORTEANDO TU BACKLOG...",
            text_color=pal["accent"]
        )
        self.lbl_titulo.configure(text="???")
        self.lbl_desc.configure(text="---", text_color="#00e676")
        self.lbl_term.configure(text="")
        self.lbl_img.configure(image=self.parent_app.placeholder_grid)
        self._iniciar_animacion_lootbox()

    def _iniciar_animacion_lootbox(self):
        self._animando = True
        if self.modo == "backlog":
            pool = self.parent_app.biblioteca_data or [self.item_final]
        else:
            pool = (
                self.parent_app.deals_filtradas
                or self.parent_app.deals_data
                or getattr(self.parent_app, "_ruleta_deals_pool", [])
                or [self.item_final]
            )
        nombres_pool = [it.get("titulo", "Juego") for it in pool]
        random.shuffle(nombres_pool)

        pasos = 14
        demora_base = 18

        def _tick(paso):
            if not self.winfo_exists():
                return
            if paso < pasos:
                nombre = random.choice(nombres_pool)
                self.lbl_titulo.configure(text=nombre[:35])
                if self.modo == "backlog":
                    hrs_rnd = random.choice([0.0, 0.5, 1.2, 5.0, 15.0])
                    self.lbl_desc.configure(text=f"⏱️ {hrs_rnd} hs jugadas")
                else:
                    desc_rnd = random.choice([25, 50, 75, 80, 90])
                    self.lbl_desc.configure(text=f"🔥 -{desc_rnd}% OFF")
                self.parent_app.sfx.play("roulette_tick")
                factor_frenado = 1.0 + (paso / pasos) ** 2.0 * 3.8
                demora = int(demora_base * factor_frenado)
                self.after(demora, lambda: _tick(paso + 1))
            else:
                self._animando = False
                self._revelar_ganador()

        _tick(0)

    def _revelar_ganador(self):
        if not self.winfo_exists():
            return
        item = self.item_final
        pal = self.parent_app.palette

        if self.modo == "backlog":
            self.lbl_head.configure(text="🎉 ¡JUEGO ELEGIDO PARA HOY!", text_color="#00e676")
            self.lbl_titulo.configure(text=item.get("titulo", "Juego"))
            hrs = item.get("horas", 0.0)
            self.lbl_desc.configure(text=f"⏱️ Tiempo jugado: {hrs} hs", text_color=pal["accent"])
            if hrs < 0.1:
                self.lbl_term.configure(text="💤 ¡Totalmente sin estrenar! Tu backlog te necesita.", text_color="#00e676")
            else:
                self.lbl_term.configure(text="🎮 ¡Una gran aventura que tenías pausada!", text_color=pal["subtext"])

            self.btn_cart.configure(
                state="normal", text="🖥️ Ver Ficha",
                fg_color=pal["card_bg"], text_color=pal["accent"]
            )
            self.btn_steam.configure(
                state="normal", text="🚀 Lanzar Steam",
                fg_color=pal["accent"], text_color=texto_contraste_acento(pal)
            )
        else:
            self.lbl_head.configure(text="🎉 ¡RECOMPENSA DESTRABADA!", text_color="#00e676")
            self.lbl_titulo.configure(text=item.get("titulo", "Juego"))
            p_off = self.parent_app._formatear_precio(item.get("precio_oferta_usd", 0.0))
            desc = item.get("descuento", 0)
            self.lbl_desc.configure(text=f"🔥 -{desc}% OFF  ➔  {p_off}", text_color="#00e676")

            veredicto, col_v, motivo = evaluar_termometro_compra(desc, item.get("es_atl", False), item.get("precio_oferta_usd", 0.0))
            self.lbl_term.configure(text=f"{veredicto}\n{motivo}", text_color=col_v)

            en_carrito = str(item.get("appid", "")) in self.parent_app.carrito
            if en_carrito:
                self.btn_cart.configure(state="disabled", text="🛒 Ya en Changuito", fg_color=pal["border"], text_color=pal["subtext"])
            else:
                self.btn_cart.configure(state="normal", text="🛒 Sumar al Carrito", fg_color=pal["accent"], text_color=texto_contraste_acento(pal))

            self.btn_steam.configure(
                state="normal", text="🚀 Abrir Steam",
                fg_color=pal["card_bg"], text_color=pal["accent"]
            )

        self.parent_app.ui_executor.submit(
            self.parent_app._cargar_imagen_async,
            item.get("appid"), item.get("thumb_url"),
            self.lbl_img, "Grilla", 160, 230,
            item.get("descuento", 0), item.get("es_atl", False)
        )
        self.parent_app.sfx.play("roulette_win")
        self.btn_reintentar.configure(state="normal")

    def _accion_boton_medio(self):
        if self.modo == "backlog":
            item = self.item_final
            DialogoFichaJuego(self.parent_app, item["appid"], item["titulo"], {
                "appid": item["appid"],
                "titulo": item["titulo"],
                "precio_oferta_usd": max(0.0, float(item.get("price_usd", 0.0))),
                "precio_normal_usd": max(0.0, float(item.get("price_usd", 0.0))),
                "descuento": 0,
                "link": f"https://store.steampowered.com/app/{item['appid']}"
            })
        else:
            self.parent_app._toggle_carrito_item(self.item_final)
            self.btn_cart.configure(state="disabled", text="🛒 Ya en Changuito", fg_color=self.parent_app.palette["border"], text_color=self.parent_app.palette["subtext"])

    def _accion_boton_derecha(self):
        item = self.item_final
        if self.modo == "backlog":
            webbrowser.open(f"steam://run/{item['appid']}")
        else:
            webbrowser.open(f"steam://store/{item['appid']}")


class DialogoActualizador(ctk.CTkToplevel):
    """Centro de auto-actualización desde GitHub Releases (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"🔄 Buscar Actualizaciones - {APP_NAME}")
        self.geometry("500x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.parent_app = parent

        pal = parent.palette
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 250
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 180
        self.geometry(f"+{x}+{y}")

        self.lbl_title = ctk.CTkLabel(self, text="🚀 Centro de Actualizaciones", font=("Arial", 16, "bold"), text_color=pal["accent"])
        self.lbl_title.pack(pady=(18, 4))

        self.lbl_ver_actual = ctk.CTkLabel(self, text=f"Versión instalada actualmente: v{APP_VERSION}", font=("Consolas", 12), text_color=pal["subtext"])
        self.lbl_ver_actual.pack(pady=(0, 12))

        self.info_box = ctk.CTkTextbox(self, width=440, height=130, font=("Consolas", 12), corner_radius=8, fg_color=pal["card_bg"], text_color=pal["text"], border_width=1, border_color=pal["border"])
        self.info_box.pack(padx=25, pady=6)
        self.info_box.insert("1.0", "⏳ Verificando repositorio oficial...")
        self.info_box.configure(state="disabled")

        self.progress = ctk.CTkProgressBar(self, width=440, progress_color=pal["accent"])
        self.progress.set(0)

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=(12, 10))

        self.btn_action = ctk.CTkButton(self.btn_frame, text="Buscando...", width=210, height=34, font=("Arial", 12, "bold"), state="disabled")
        self.btn_action.pack(side="left", padx=6)

        self.btn_close = ctk.CTkButton(self.btn_frame, text="Cerrar", width=100, height=34, fg_color=pal["border"], text_color=pal["text"], command=self.destroy)
        self.btn_close.pack(side="left", padx=6)

        threading.Thread(target=self._chequear_actualizacion, daemon=True).start()

    def _escribir_info(self, texto):
        if not self.winfo_exists():
            return
        self.info_box.configure(state="normal")
        self.info_box.delete("1.0", "end")
        self.info_box.insert("1.0", texto)
        self.info_box.configure(state="disabled")

    def _chequear_actualizacion(self):
        url_json = self.parent_app.config.datos.get("update_url", UPDATE_JSON_URL)
        rem_ver = None
        download_url = None
        notas = ""
        try:
            r = HTTP_SESSION.get(url_json, timeout=5)
            if r.status_code == 200:
                data = r.json()
                rem_ver = data.get("version", "")
                download_url = data.get("url", "")
                notas = data.get("notas", data.get("changelog", ""))
                if isinstance(notas, list):
                    notas = "\n".join([f"• {c}" for c in notas])
        except Exception:
            pass

        if not rem_ver:
            try:
                r_gh = HTTP_SESSION.get(GITHUB_API_RELEASES, timeout=5)
                if r_gh.status_code == 200:
                    data = r_gh.json()
                    rem_ver = data.get("tag_name", "")
                    notas = data.get("body", "")
                    setup_url = None
                    exe_url = None
                    for asset in data.get("assets", []):
                        aname = asset.get("name", "").lower()
                        if aname.endswith(".exe"):
                            if "setup" in aname or "instalador" in aname:
                                setup_url = asset.get("browser_download_url")
                                break
                            elif not exe_url:
                                exe_url = asset.get("browser_download_url")
                    download_url = setup_url or exe_url
                    if not download_url:
                        download_url = data.get("html_url", FALLBACK_RELEASES_WEB)
            except Exception:
                pass

        if not rem_ver:
            msg = f"✅ Tenés la versión v{APP_VERSION} instalada.\n\nNo hay un parche posterior o el servidor no está disponible."
            self.after(0, lambda: self._escribir_info(msg))
            self.after(0, lambda: self.btn_action.configure(text="🌐 Canal Oficial", state="normal", fg_color="#1f538d", command=lambda: webbrowser.open("https://www.youtube.com/@Patoma89")))
            return

        if _parse_version_tuple(rem_ver) > _parse_version_tuple(APP_VERSION):
            msg = f"🎉 ¡NUEVA VERSIÓN DISPONIBLE: {rem_ver}!\n\nNovedades:\n{notas or 'Mejoras de rendimiento y nuevas funciones.'}"
            self.after(0, lambda: self._escribir_info(msg))
            if download_url and download_url.lower().endswith(".exe"):
                self.after(0, lambda: self.btn_action.configure(text="🚀 Actualizar Ahora", state="normal", fg_color="#00c853", text_color="white", hover_color="#00e676", command=lambda: self._iniciar_descarga(download_url)))
            else:
                self.after(0, lambda: self.btn_action.configure(text="📥 Descargar desde la Web", state="normal", fg_color="#00c853", text_color="white", command=lambda: webbrowser.open(download_url or FALLBACK_RELEASES_WEB)))
        else:
            msg = f"✅ ¡Estás al día!\n\nYa tenés instalada la última versión disponible de {APP_NAME} (v{APP_VERSION})."
            self.after(0, lambda: self._escribir_info(msg))
            self.after(0, lambda: self.btn_action.configure(text="✔ Todo actualizado", state="disabled", fg_color="#2e7d32"))

    def _iniciar_descarga(self, url_exe):
        self.btn_action.configure(state="disabled", text="Descargando...")
        self.progress.pack(padx=25, pady=(4, 4), before=self.btn_frame)
        threading.Thread(target=self._hilo_descargar_instalador, args=(url_exe,), daemon=True).start()

    def _hilo_descargar_instalador(self, url_exe):
        try:
            r = HTTP_SESSION.get(url_exe, stream=True, timeout=15)
            total_len = int(r.headers.get('content-length', 0))
            destino = os.path.join(tempfile.gettempdir(), "SteamScope_Update_Setup.exe")
            descargado = 0
            with open(destino, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        descargado += len(chunk)
                        if total_len > 0:
                            pct = descargado / total_len
                            self.after(0, lambda p=pct: self.progress.set(p) if self.winfo_exists() else None)
            self.after(0, lambda: self._escribir_info("✅ Descarga completada. Ejecutando el instalador..."))
            time.sleep(1.2)

            # Sanitizar variables de entorno de PyInstaller (_MEIPASS / _MEIPASS2 / PYTHONPATH)
            # para evitar que el instalador o la nueva instancia de la app intenten
            # cargar DLLs desde el directorio temporal del proceso que se está cerrando.
            clean_env = os.environ.copy()
            for k in list(clean_env.keys()):
                if "_MEI" in k or k.startswith("PYTHON"):
                    clean_env.pop(k, None)

            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            subprocess.Popen(
                [destino, "/SILENT"],
                env=clean_env,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True
            )
            time.sleep(0.5)
            self.parent_app.tray.salir_completo()
        except Exception as e:
            self.after(0, lambda err=str(e): mostrar_alerta_skin(self, "Error", f"No se pudo descargar automáticamente:\n{err}", tipo="error"))
            webbrowser.open(url_exe)


class DialogoRedes(ctk.CTkToplevel):
    """Hub de redes sociales del creador (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        pal = parent.palette
        self.title("📱 Redes y Canales - Patoma89")
        self.geometry("360x290")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 180
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 145
        self.geometry(f"+{x}+{y}")

        card = ctk.CTkFrame(self, fg_color=pal["card_bg"], corner_radius=12, border_width=1, border_color=pal["border"])
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(card, text="👾 Patoma89 Studio", font=("Arial", 16, "bold"), text_color=pal["accent"]).pack(pady=(16, 12))
        ctk.CTkButton(card, text="▶ YouTube", font=("Segoe UI", 12, "bold"), fg_color="#d32f2f", hover_color="#b71c1c", text_color="white", height=32, command=lambda: webbrowser.open("https://www.youtube.com/@Patoma89")).pack(pady=6, fill="x", padx=28)
        ctk.CTkButton(card, text="🟪 Twitch", font=("Segoe UI", 12, "bold"), fg_color="#673ab7", hover_color="#512da8", text_color="white", height=32, command=lambda: webbrowser.open("https://www.twitch.com/patoma89")).pack(pady=6, fill="x", padx=28)
        ctk.CTkButton(card, text="💬 Discord", font=("Segoe UI", 12, "bold"), fg_color="#1976d2", hover_color="#0d47a1", text_color="white", height=32, command=lambda: webbrowser.open("https://discord.gg/MJzMg2rT37")).pack(pady=6, fill="x", padx=28)


class DialogoBlacklist(ctk.CTkToplevel):
    """Gestor de juegos ignorados (Blacklist) (SRP)."""
    def __init__(self, parent, db_manager, on_change_cb):
        super().__init__(parent)
        self.title("🚫 Gestor de Ignorados (Blacklist)")
        self.geometry("480x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.db = db_manager
        self.on_change_cb = on_change_cb
        self.pal = parent.palette
        self.configure(fg_color=self.pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 240
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 210
        self.geometry(f"+{x}+{y}")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(top, text="Juegos Ocultos (Blacklist)", font=("Arial", 15, "bold"), text_color=self.pal["text"]).pack(side="left")
        ctk.CTkButton(top, text="🗑 Vaciar Todo", width=110, height=26, fg_color="#b71c1c", hover_color="#c62828", text_color="white", command=self._vaciar_todo).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=8, fg_color=self.pal["panel_bg"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)
        self._cargar_lista()

    def _cargar_lista(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        items = self.db.get_blacklist_details()
        if not items:
            ctk.CTkLabel(self.scroll, text="No tenés ningún juego en la lista de ignorados.", text_color=self.pal["subtext"]).pack(pady=30)
            return
        for appid, titulo in items:
            row = ctk.CTkFrame(self.scroll, corner_radius=6, fg_color=self.pal["card_bg"], border_width=1, border_color=self.pal["border"])
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkLabel(row, text=f"{titulo} (ID: {appid})", font=("Arial", 12), text_color=self.pal["text"], anchor="w").pack(side="left", padx=10, pady=6)
            ctk.CTkButton(row, text="Restaurar", width=80, height=24, fg_color="#2e7d32", hover_color="#1b5e20", text_color="white", command=lambda a=appid: self._restaurar(a)).pack(side="right", padx=8, pady=4)

    def _restaurar(self, appid):
        self.db.remove_blacklist(appid)
        self._cargar_lista()
        self.on_change_cb()

    def _vaciar_todo(self):
        if preguntar_si_no_skin(self, "Confirmar", "¿Seguro que querés restaurar todos los juegos ignorados?"):
            self.db.clear_blacklist()
            self._cargar_lista()
            self.on_change_cb()


class DialogoVisorCapturas(ctk.CTkToplevel):
    """Visor interactivo HD de capturas de pantalla con navegación por teclado y botones (SRP)."""
    def __init__(self, parent, titulo_juego, lista_capturas, idx_inicial=0):
        super().__init__(parent)
        self.parent_app = getattr(parent, "parent_app", parent)
        pal = self.parent_app.palette
        self.titulo_juego = titulo_juego
        self.capturas = lista_capturas or []
        self.idx_actual = max(0, min(idx_inicial, len(self.capturas) - 1)) if self.capturas else 0
        
        # Caché de imágenes en memoria para transiciones instantáneas a 60 FPS
        self.cache_ctk = {}
        self.cache_pil = {}
        self.raw_pil_cache = {}
        self._descargando = set()
        self._es_fullscreen = False
        
        self.title(f"🖼️ Visor de Capturas: {self.titulo_juego}")
        self.geometry("980x640")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])
        
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 490
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 320
        self.geometry(f"+{max(20, x)}+{max(20, y)}")
        
        # Barra superior
        top_bar = ctk.CTkFrame(self, fg_color=pal["panel_bg"], height=42, corner_radius=0)
        top_bar.pack(fill="x", side="top")
        
        lbl_titulo = ctk.CTkLabel(
            top_bar,
            text=f"🖼️ {self.titulo_juego}",
            font=("Segoe UI", 13, "bold"),
            text_color=pal["accent"]
        )
        lbl_titulo.pack(side="left", padx=16, pady=6)
        
        ctk.CTkLabel(
            top_bar,
            text="[ ◀ / ▶ Flechas del teclado para navegar  •  ESC para salir ]",
            font=("Segoe UI", 10),
            text_color=pal["subtext"]
        ).pack(side="left", padx=12, pady=6)
        
        ctk.CTkButton(
            top_bar,
            text="✕ Cerrar",
            width=80,
            height=28,
            font=("Segoe UI", 11, "bold"),
            fg_color="#da3633",
            hover_color="#f85149",
            text_color="white",
            command=self.destroy
        ).pack(side="right", padx=14, pady=6)

        self.btn_fullscreen = ctk.CTkButton(
            top_bar,
            text="⛶ Pantalla Completa",
            width=145,
            height=28,
            font=("Segoe UI", 11),
            fg_color=pal["card_bg"],
            hover_color=pal["card_hover"],
            border_width=1,
            border_color=pal["border"],
            text_color=pal["accent"],
            command=self._toggle_fullscreen
        )
        self.btn_fullscreen.pack(side="right", padx=(0, 6), pady=6)
        
        # Barra inferior
        bot_bar = ctk.CTkFrame(self, fg_color=pal["panel_bg"], height=48, corner_radius=0)
        bot_bar.pack(fill="x", side="bottom")
        
        fg_acc = texto_contraste_acento(pal)
        
        self.btn_ant = ctk.CTkButton(
            bot_bar,
            text="◀ Anterior (←)",
            font=("Segoe UI", 11, "bold"),
            width=135,
            height=32,
            fg_color=pal["card_bg"],
            hover_color=pal["card_hover"],
            border_width=1,
            border_color=pal["border"],
            text_color=pal["text"],
            command=self._anterior
        )
        self.btn_ant.pack(side="left", padx=(16, 8), pady=8)
        
        self.lbl_contador = ctk.CTkLabel(
            bot_bar,
            text=f"Captura {self.idx_actual + 1} de {len(self.capturas)}",
            font=("Segoe UI", 12, "bold"),
            text_color=pal["text"]
        )
        self.lbl_contador.pack(side="left", padx=8, pady=8)
        
        self.btn_sig = ctk.CTkButton(
            bot_bar,
            text="Siguiente ▶ (→)",
            font=("Segoe UI", 11, "bold"),
            width=135,
            height=32,
            fg_color=pal["accent"],
            hover_color=pal["accent_2"],
            text_color=fg_acc,
            command=self._siguiente
        )
        self.btn_sig.pack(side="left", padx=8, pady=8)
        
        self.btn_web = ctk.CTkButton(
            bot_bar,
            text="🌐 Ver Original en HD",
            font=("Segoe UI", 11),
            width=160,
            height=32,
            fg_color=pal["card_bg"],
            hover_color=pal["card_hover"],
            border_width=1,
            border_color=pal["border"],
            text_color=pal["accent"],
            command=self._abrir_en_navegador
        )
        self.btn_web.pack(side="right", padx=16, pady=8)
        
        # Contenedor central
        self.main_container = ctk.CTkFrame(self, fg_color=pal["card_bg"], corner_radius=10, border_width=1, border_color=pal["border"])
        self.main_container.pack(fill="both", expand=True, padx=14, pady=10)
        
        # Botones laterales de navegación rápida
        self.btn_flotante_ant = ctk.CTkButton(
            self.main_container,
            text="◀",
            font=("Segoe UI", 20, "bold"),
            width=44,
            height=120,
            corner_radius=8,
            fg_color=pal["win_bg"],
            hover_color=pal["panel_bg"],
            text_color=pal["accent"],
            command=self._anterior
        )
        self.btn_flotante_ant.pack(side="left", padx=(10, 4), pady=20)
        
        self.lbl_imagen = ctk.CTkLabel(
            self.main_container,
            text="⏳ Cargando captura HD...",
            font=("Consolas", 14, "bold"),
            text_color=pal["accent"],
            fg_color="transparent"
        )
        self.lbl_imagen.pack(side="left", fill="both", expand=True, padx=4, pady=8)
        self.lbl_imagen.configure(cursor="hand2")
        self.lbl_imagen.bind("<Button-1>", self._on_image_click)
        
        self.btn_flotante_sig = ctk.CTkButton(
            self.main_container,
            text="▶",
            font=("Segoe UI", 20, "bold"),
            width=44,
            height=120,
            corner_radius=8,
            fg_color=pal["win_bg"],
            hover_color=pal["panel_bg"],
            text_color=pal["accent"],
            command=self._siguiente
        )
        self.btn_flotante_sig.pack(side="right", padx=(4, 10), pady=20)
        
        # Atajos de teclado para navegación fluida
        self.bind("<Left>", lambda e: self._anterior())
        self.bind("<Right>", lambda e: self._siguiente())
        self.bind("<Escape>", lambda e: self._on_key_escape())
        self.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.bind("<space>", lambda e: self._siguiente())
        self.bind("<Return>", lambda e: self._siguiente())
        self.bind("a", lambda e: self._anterior())
        self.bind("d", lambda e: self._siguiente())
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.lbl_imagen.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())
        
        self.after(50, lambda: self.focus_force() if self.winfo_exists() else None)
        self._cargar_captura_actual()

    def _toggle_fullscreen(self, event=None):
        self._es_fullscreen = not self._es_fullscreen
        self.attributes("-fullscreen", self._es_fullscreen)
        if self._es_fullscreen:
            self.btn_fullscreen.configure(text="🗗 Salir Pantalla Completa")
            self.btn_flotante_ant.configure(height=220)
            self.btn_flotante_sig.configure(height=220)
        else:
            self.btn_fullscreen.configure(text="⛶ Pantalla Completa")
            self.btn_flotante_ant.configure(height=120)
            self.btn_flotante_sig.configure(height=120)
        self.after(100, self._redimensionar_imagen_activa)

    def _on_key_escape(self):
        if self._es_fullscreen:
            self._toggle_fullscreen()
        else:
            self.destroy()

    def _redimensionar_imagen_activa(self):
        if not self.winfo_exists() or not self.capturas:
            return
        idx = self.idx_actual
        if idx in self.raw_pil_cache:
            raw_pil = self.raw_pil_cache[idx]
            w_max = max(700, self.main_container.winfo_width() - 130) if self.main_container.winfo_width() > 100 else 840
            h_max = max(420, self.main_container.winfo_height() - 30) if self.main_container.winfo_height() > 100 else 500
            pil_contain = ImageOps.contain(raw_pil, (w_max, h_max), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_contain, dark_image=pil_contain, size=pil_contain.size)
            self.cache_ctk[idx] = ctk_img
            self.lbl_imagen.configure(image=ctk_img, text="")

    def _on_image_click(self, event):
        w = self.lbl_imagen.winfo_width()
        if w > 0 and event.x < (w // 2):
            self._anterior()
        else:
            self._siguiente()

    def _on_mousewheel(self, event):
        if event.delta > 0:
            self._anterior()
        else:
            self._siguiente()

    def _anterior(self):
        if not self.capturas:
            return
        if self.idx_actual > 0:
            self.idx_actual -= 1
        else:
            self.idx_actual = len(self.capturas) - 1
        self._cargar_captura_actual()

    def _siguiente(self):
        if not self.capturas:
            return
        if self.idx_actual < len(self.capturas) - 1:
            self.idx_actual += 1
        else:
            self.idx_actual = 0
        self._cargar_captura_actual()

    def _abrir_en_navegador(self):
        url = self._get_url_actual()
        if url:
            webbrowser.open(url)

    def _get_url_actual(self):
        if not self.capturas or self.idx_actual >= len(self.capturas):
            return None
        item = self.capturas[self.idx_actual]
        if isinstance(item, dict):
            return item.get("path_full") or item.get("path_thumbnail")
        return str(item)

    def _cargar_captura_actual(self):
        if not self.capturas:
            self.lbl_imagen.configure(text="No hay capturas disponibles.", image=None)
            return

        total = len(self.capturas)
        idx = self.idx_actual
        self.lbl_contador.configure(text=f"Captura {idx + 1} de {total}")
        self.title(f"🖼️ Visor de Capturas HD ({idx + 1}/{total}) - {self.titulo_juego}")

        if idx in self.cache_ctk:
            self.lbl_imagen.configure(image=self.cache_ctk[idx], text="")
            self._precargar_adyacentes(idx)
            return

        if idx in self.cache_pil:
            pil_img = self.cache_pil[idx]
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            self.cache_ctk[idx] = ctk_img
            self.lbl_imagen.configure(image=ctk_img, text="")
            self._precargar_adyacentes(idx)
            return

        self.lbl_imagen.configure(text=f"⏳ Descargando captura HD ({idx + 1}/{total})...", image=None)
        if idx not in self._descargando:
            self._descargando.add(idx)
            threading.Thread(target=self._hilo_descargar_captura, args=(idx,), daemon=True).start()

    def _hilo_descargar_captura(self, idx):
        try:
            if idx >= len(self.capturas):
                return
            item = self.capturas[idx]
            url = item.get("path_full") if isinstance(item, dict) else str(item)
            if not url:
                return

            r = HTTP_SESSION.get(url, timeout=7)
            if r.status_code == 200 and len(r.content) > 1000:
                with Image.open(BytesIO(r.content)) as raw:
                    raw.load()
                    raw_pil = raw.convert("RGB")
                self.raw_pil_cache[idx] = raw_pil

                w_max = max(700, self.main_container.winfo_width() - 130) if self.main_container.winfo_width() > 100 else 840
                h_max = max(420, self.main_container.winfo_height() - 30) if self.main_container.winfo_height() > 100 else 500
                pil_contain = ImageOps.contain(raw_pil, (w_max, h_max), Image.Resampling.LANCZOS)

                self.cache_pil[idx] = pil_contain
                ctk_img = ctk.CTkImage(light_image=pil_contain, dark_image=pil_contain, size=pil_contain.size)
                self.cache_ctk[idx] = ctk_img

                def _mostrar():
                    if not self.winfo_exists():
                        return
                    if self.idx_actual == idx:
                        self.lbl_imagen.configure(image=ctk_img, text="")
                    self._precargar_adyacentes(idx)

                self.after(0, _mostrar)
        except Exception:
            def _err():
                if self.winfo_exists() and self.idx_actual == idx:
                    self.lbl_imagen.configure(text="❌ Error al descargar esta captura.", image=None)
            self.after(0, _err)
        finally:
            self._descargando.discard(idx)

    def _precargar_adyacentes(self, idx_base):
        total = len(self.capturas)
        if total <= 1:
            return
        idx_sig = (idx_base + 1) % total
        idx_ant = (idx_base - 1 + total) % total
        for target_idx in (idx_sig, idx_ant):
            if target_idx not in self.cache_pil and target_idx not in self._descargando:
                self._descargando.add(target_idx)
                threading.Thread(target=self._hilo_descargar_captura, args=(target_idx,), daemon=True).start()


class DialogoFichaJuego(ctk.CTkToplevel):
    """Ficha Técnica estilo Terminal con capturas HD, comparador regional y ProtonDB (SRP)."""
    def __init__(self, parent, appid, titulo, item_ref=None):
        super().__init__(parent)
        self.title(f"🖥️ Ficha Técnica: {titulo}")
        self.geometry("900x670")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.parent_app = parent
        self.appid = str(appid)
        self.titulo = titulo
        self.item_ref = item_ref or {}
        pal = parent.palette
        self.bg_term = pal["win_bg"]
        self.card_term = pal["card_bg"]
        self.border_term = pal["border"]
        self.green_term = pal["accent"]
        self.blue_term = pal["accent_2"] if pal["accent_2"] != pal["accent"] else "#58a6ff"
        self.gray_term = pal["subtext"]
        self.text_term = pal["text"]
        self.configure(fg_color=self.bg_term)

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 450
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 335
        self.geometry(f"+{max(20, x)}+{max(20, y)}")

        self.lbl_loading = ctk.CTkLabel(
            self,
            text=f"patoma89@steamscope:~$ fetch --app {appid}\n⏳ Descargando metadatos y ProtonDB...",
            font=("Consolas", 14, "bold"),
            text_color=self.green_term,
            justify="left"
        )
        self.lbl_loading.pack(expand=True)
        threading.Thread(target=self._descargar_ficha_completa, daemon=True).start()

    def _descargar_ficha_completa(self):
        data, poster_pil, review_summary, historico_global, proton_tier = (
            self.parent_app.api_client.descargar_ficha_completa_paralelo(self.appid, self.parent_app.db)
        )
        if data:
            self.after(0, lambda: self._renderizar_terminal(data, poster_pil, review_summary, historico_global, proton_tier))
        else:
            self.after(0, lambda: self.lbl_loading.configure(text="❌ Error: No se pudo obtener la ficha.", text_color="#ff5252"))

    def _analizar_espanol(self, langs_raw):
        if not langs_raw:
            return "no especificado"
        limpio = html.unescape(langs_raw)
        tiene_audio = False
        if "Español" in limpio or "Spanish" in limpio:
            for p in re.split(r',|\n|<br\s*/?>', limpio):
                if "español" in p.lower() or "spanish" in p.lower():
                    if "*" in p:
                        tiene_audio = True
            return "voces y textos (doblaje)" if tiene_audio else "solo textos / subtítulos"
        return "no disponible en español"

    def _renderizar_terminal(self, data, poster_pil, review_summary, historico_global, proton_tier):
        if not self.winfo_exists():
            return
        self.lbl_loading.destroy()
        scroll = ctk.CTkScrollableFrame(self, fg_color=self.bg_term, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=18, pady=12)
        prompt_top = ctk.CTkFrame(scroll, fg_color="transparent")
        prompt_top.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(prompt_top, text=f"🎮 FICHA TÉCNICA // {self.titulo.upper()}", font=("Consolas", 14, "bold"), text_color=self.green_term).pack(side="left")
        main_row = ctk.CTkFrame(scroll, fg_color="transparent")
        main_row.pack(fill="x", pady=4)
        poster_card = ctk.CTkFrame(main_row, fg_color=self.card_term, corner_radius=6, border_width=1, border_color=self.border_term)
        poster_card.pack(side="left", anchor="n", padx=(0, 22))
        poster_hdr = ctk.CTkFrame(poster_card, fg_color=self.parent_app.palette["panel_bg"], height=24, corner_radius=0)
        poster_hdr.pack(fill="x", padx=1, pady=(1, 0))
        ctk.CTkLabel(poster_hdr, text=" • portada.webp", font=("Consolas", 10), text_color=self.green_term).pack(side="left", padx=4)
        ctk.CTkLabel(poster_hdr, text="300×450 ", font=("Consolas", 10), text_color=self.gray_term).pack(side="right", padx=4)
        if poster_pil is None:
            poster_pil = Image.new("RGB", (200, 300), color=(22, 27, 34))
            ImageDraw.Draw(poster_pil).text((55, 140), "STEAM POSTER", fill=(110, 118, 129))
        ctk_poster = ctk.CTkImage(light_image=poster_pil, dark_image=poster_pil, size=(200, 300))
        ctk.CTkLabel(poster_card, text="", image=ctk_poster).pack(padx=2, pady=2)
        meta_col = ctk.CTkFrame(main_row, fg_color="transparent")
        meta_col.pack(side="left", fill="both", expand=True, anchor="n")
        tit_row = ctk.CTkFrame(meta_col, fg_color="transparent")
        tit_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(tit_row, text="# ", font=("Consolas", 20, "bold"), text_color=self.green_term).pack(side="left")
        ctk.CTkLabel(tit_row, text=data.get("name", self.titulo), font=("Consolas", 20, "bold"), text_color=self.text_term, anchor="w", justify="left", wraplength=540).pack(side="left")

        def add_kv_row(key_name, val_text, val_color=self.blue_term, extra_text=None, badge_age=None, copy_link=False):
            r_frame = ctk.CTkFrame(meta_col, fg_color="transparent")
            r_frame.pack(fill="x", pady=2)
            dots = "." * max(2, 13 - len(key_name))
            ctk.CTkLabel(r_frame, text=f"{key_name} ", font=("Consolas", 12), text_color=self.gray_term).pack(side="left")
            ctk.CTkLabel(r_frame, text=f"{dots} ", font=("Consolas", 12), text_color=self.border_term).pack(side="left")
            if badge_age:
                col_bg = "#ef6c00" if int(badge_age) >= 16 else "#2e7d32"
                ctk.CTkLabel(r_frame, text=f" {badge_age} ", fg_color=col_bg, text_color="white", corner_radius=3, font=("Consolas", 11, "bold")).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(r_frame, text=val_text, font=("Consolas", 12, "bold" if val_color in (self.blue_term, self.green_term) else "normal"), text_color=val_color, anchor="w").pack(side="left")
            if extra_text:
                ctk.CTkLabel(r_frame, text=f" {extra_text}", font=("Consolas", 12), text_color=self.gray_term).pack(side="left")
            if copy_link:
                ctk.CTkButton(r_frame, text="copiar enlace", width=95, height=20, font=("Consolas", 11), fg_color=self.card_term, hover_color=self.parent_app.palette["card_hover"], border_width=1, border_color=self.border_term, text_color=self.gray_term, command=lambda: self.parent_app._copiar_al_portapapeles(f"https://store.steampowered.com/app/{self.appid}", self.titulo)).pack(side="left", padx=10)

        rel_date = data.get("release_date", {}).get("date", "N/A")
        devs = ", ".join(data.get("developers", ["Desconocido"]))[:42]
        pubs = ", ".join(data.get("publishers", ["Desconocido"]))[:42]
        edad_num = int(re.sub(r'[^0-9]', '', str(data.get("required_age", 0))) or 0)
        metacritic = data.get("metacritic", {}).get("score")
        generos_str = " · ".join([g.get("description", "").lower() for g in data.get("genres", [])]) or "acción · aventura"
        cats = [c.get("description", "").lower() for c in data.get("categories", [])]
        extras_list = [
            x for x, cond in [
                ("cromos", any("cromos" in c or "cards" in c for c in cats)),
                ("logros", any("logros" in c or "achievements" in c for c in cats)),
                ("cloud", any("cloud" in c for c in cats)),
                ("mando", any("mando" in c or "controller" in c for c in cats)),
                ("co-op", any("cooperativo" in c or "co-op" in c for c in cats)),
            ] if cond
        ]
        extras_str = " · ".join(extras_list) if extras_list else "estándar"
        idioma_es = self._analizar_espanol(data.get("supported_languages", ""))

        add_kv_row("id", f"APP-{self.appid}", val_color=self.text_term, copy_link=True)
        add_kv_row("lanzamiento", rel_date, val_color=self.blue_term)
        add_kv_row("estudio", devs, val_color=self.blue_term)
        add_kv_row("editora", pubs, val_color=self.blue_term)
        sub_info = detectar_suscripcion(data.get("name", self.titulo), pubs)
        if sub_info:
            add_kv_row("suscripción", f"incluido en {sub_info[0].lower()}", val_color="#00e676", extra_text="(ahorrá tu compra)")

        po = data.get("price_overview", {})
        p_actual_usd = (po.get("final", 0) / 100.0) if po else self.item_ref.get("precio_oferta_usd", 0.0)
        desc_actual = po.get("discount_percent", 0) if po else self.item_ref.get("descuento", 0)
        if p_actual_usd > 0:
            dolar_t = self.parent_app.config.datos.get("dolar_referencia", 1000.0)
            imp_t = self.parent_app.config.datos.get("impuestos_pct", 60)
            ars_tarj = round(p_actual_usd * dolar_t * (1 + imp_t / 100.0))
            ars_wallet = round(p_actual_usd * dolar_t)
            add_kv_row("pago ars", f"💳 ${ars_tarj:,.0f}  |  👛 ${ars_wallet:,.0f} (wallet)", val_color=self.green_term, extra_text="(sin imp en wallet)")

        us_info = data.get("_us_price_info")
        if us_info and p_actual_usd > 0 and us_info.get("final_us", 0) > 0:
            p_us = us_info["final_us"]
            ahorro_reg = round(((p_us - p_actual_usd) / p_us) * 100)
            if ahorro_reg >= 12:
                add_kv_row("región ar", f"🇦🇷 -{ahorro_reg}% más barato que EE.UU. (${p_us:.2f} US)", val_color="#00e676", extra_text="(precio regional cuidado)")
            elif ahorro_reg <= -5:
                add_kv_row("región ar", f"⚠️ +{abs(ahorro_reg)}% más caro que EE.UU. (${p_us:.2f} US)", val_color="#ff5252")
            else:
                add_kv_row("región ar", f"🌎 Mismo precio que EE.UU. (${p_us:.2f} US)", val_color="#ffab00", extra_text="(sin descuento regional)")

        veredicto, col_term, motivo_term = evaluar_termometro_compra(desc_actual, self.item_ref.get("es_atl", False), p_actual_usd)
        add_kv_row("termómetro", veredicto.lower(), val_color=col_term, extra_text=f"— {motivo_term[:35]}")
        if edad_num > 0:
            add_kv_row("clasificación", "contenido adulto / violencia", val_color=self.gray_term, badge_age=str(edad_num))
        else:
            add_kv_row("clasificación", "apto para todo público", val_color=self.text_term)
        if review_summary:
            add_kv_row("jugadores", f"steam: {review_summary[0]}", val_color=self.blue_term, extra_text=review_summary[1])
        if metacritic:
            add_kv_row("crítica", f"metacritic: {metacritic}/100", val_color=self.blue_term)
        add_kv_row("español", idioma_es, val_color=self.blue_term if "voces" in idioma_es else self.text_term)
        add_kv_row("género", generos_str, val_color=self.blue_term)
        add_kv_row("funciones", extras_str, val_color=self.blue_term)
        if historico_global:
            add_kv_row("mín. global", f"${historico_global[0]:.2f} USD", val_color=self.green_term, extra_text=f"(récord el {historico_global[1]})")

        pkg_groups = data.get("package_groups", [])
        if pkg_groups:
            subs = pkg_groups[0].get("subs", [])
            if len(subs) > 1 and p_actual_usd > 0:
                ediciones = []
                for s in subs:
                    p_cents = s.get("price_in_cents_with_discount", 0)
                    if p_cents > 0:
                        ediciones.append((limpiar_html(s.get("option_text", "Edición")), p_cents / 100.0))
                ediciones.sort(key=lambda x: x[1])
                if len(ediciones) >= 2:
                    base_pack = ediciones[0]
                    deluxe_pack = ediciones[1]
                    dif_usd = deluxe_pack[1] - base_pack[1]
                    if 0 <= dif_usd <= 6.0:
                        add_kv_row("pack / dlc", f"📦 {deluxe_pack[0][:28]} (${deluxe_pack[1]:.2f} USD)", val_color="#ffab00", extra_text=f"(+${dif_usd:.2f} vs base)")
                    else:
                        add_kv_row("ediciones", f"📦 {len(ediciones)} packs disponibles en tienda", val_color=self.blue_term, extra_text=f"(desde ${base_pack[1]:.2f} USD)")

        pc_req_raw = data.get("pc_requirements", {})
        min_txt = pc_req_raw.get("minimum", "") if isinstance(pc_req_raw, dict) else ""
        gb_almacenamiento = extraer_espacio_disco(min_txt)
        if gb_almacenamiento != "N/D":
            add_kv_row("espacio pc", f"💾 {gb_almacenamiento} requeridos", val_color=self.blue_term)

        if po and po.get("discount_percent", 0) > 0:
            time_end = self.item_ref.get("time_end")
            aviso_tiempo = calcular_tiempo_restante(time_end)
            if aviso_tiempo:
                add_kv_row("rebaja activa", f"⏳ {aviso_tiempo}", val_color="#ff7518", extra_text="(precio por tiempo limitado)")

        if proton_tier:
            colors_proton = {"Platinum": "#b0e0e6", "Gold": "#ffd700", "Silver": "#c0c0c0", "Bronze": "#cd7f32", "Borked": "#ff4500"}
            col_p = colors_proton.get(proton_tier, self.blue_term)
            add_kv_row("protondb", f"medalla {proton_tier.lower()}", val_color=col_p, extra_text="(comunidad steam deck)")

        ctk.CTkLabel(scroll, text="─" * 92, font=("Consolas", 11), text_color=self.border_term).pack(fill="x", pady=(14, 10))
        ctk.CTkLabel(scroll, text=limpiar_html(data.get("short_description", "Sin descripción disponible.")), font=("Consolas", 13), text_color=self.text_term, justify="left", anchor="w", wraplength=800).pack(fill="x", pady=(0, 12))

        # Bloque de Nota Personal
        nota_existente = self.parent_app.db.get_game_note(self.appid)
        nota_f = ctk.CTkFrame(scroll, fg_color=self.card_term, corner_radius=8, border_width=1, border_color=self.border_term)
        nota_f.pack(fill="x", pady=(0, 12))

        nota_top = ctk.CTkFrame(nota_f, fg_color="transparent")
        nota_top.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(nota_top, text="📝 Mi Nota Personal:", font=("Consolas", 12, "bold"), text_color=self.blue_term).pack(side="left")

        lbl_nota_texto = ctk.CTkLabel(
            nota_f, text=nota_existente if nota_existente else "(Sin nota. Tocá 'Editar Nota' para agregar apuntes privados)",
            font=("Consolas", 11, "italic" if not nota_existente else "normal"),
            text_color=self.text_term if nota_existente else self.gray_term,
            justify="left", anchor="w", wraplength=780
        )
        lbl_nota_texto.pack(anchor="w", padx=12, pady=(2, 6))

        def _editar_nota():
            actual = self.parent_app.db.get_game_note(self.appid)
            res = pedir_input_skin(self, "Nota Personal", f"Escribí tu apunte para '{self.titulo}':", valor_inicial=actual)
            if res is not None:
                self.parent_app.db.save_game_note(self.appid, res)
                limpia = res.strip()
                lbl_nota_texto.configure(
                    text=limpia if limpia else "(Sin nota. Tocá 'Editar Nota' para agregar apuntes privados)",
                    font=("Consolas", 11, "italic" if not limpia else "normal"),
                    text_color=self.text_term if limpia else self.gray_term
                )
                self.parent_app._show_toast("📝 Nota guardada.", "#00e676")
                if hasattr(self.parent_app, "_renderizar_watchlist"):
                    self.parent_app._renderizar_watchlist()
                elif hasattr(self.parent_app, "_render_watchlist"):
                    self.parent_app._render_watchlist()

        ctk.CTkButton(
            nota_top, text="✏️ Editar Nota", font=("Consolas", 11, "bold"), width=105, height=24,
            fg_color=self.bg_term, border_width=1, border_color=self.blue_term, text_color=self.blue_term,
            hover_color=self.border_term, command=_editar_nota
        ).pack(side="right")

        screenshots = data.get("screenshots", [])
        self.screenshots = screenshots
        if screenshots:
            gal_header = ctk.CTkFrame(scroll, fg_color="transparent")
            gal_header.pack(fill="x", pady=(2, 4))
            ctk.CTkLabel(gal_header, text="🖼️ Capturas del Juego (clic para ampliar en HD):", font=("Consolas", 13, "bold"), text_color=self.blue_term).pack(side="left")
            ctk.CTkButton(
                gal_header,
                text="🔍 Visor HD Completo (← →)",
                font=("Consolas", 11, "bold"),
                width=200,
                height=24,
                fg_color=self.card_term,
                border_width=1,
                border_color=self.green_term,
                text_color=self.green_term,
                hover_color=self.parent_app.palette["card_hover"],
                command=lambda: DialogoVisorCapturas(self, self.titulo, self.screenshots, 0)
            ).pack(side="right")
            gal_row = ctk.CTkFrame(scroll, fg_color=self.card_term, corner_radius=8, border_width=1, border_color=self.border_term)
            gal_row.pack(fill="x", pady=(0, 12))
            for idx_ss, ss in enumerate(screenshots[:4]):
                thumb_ss = ss.get("path_thumbnail")
                lbl_ss = ctk.CTkLabel(gal_row, text="📷...", width=172, height=96, fg_color=self.bg_term, corner_radius=6, cursor="hand2", font=("Consolas", 10), text_color=self.gray_term)
                lbl_ss.grid(row=0, column=idx_ss, padx=6, pady=8)
                lbl_ss.bind("<Button-1>", lambda e, idx=idx_ss: DialogoVisorCapturas(self, self.titulo, self.screenshots, idx))
                self.parent_app.ui_executor.submit(self._cargar_captura_miniatura, thumb_ss, lbl_ss)

        prompt_req = ctk.CTkFrame(scroll, fg_color="transparent")
        prompt_req.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(prompt_req, text="💻 Requisitos del Sistema (PC):", font=("Consolas", 14, "bold"), text_color=self.green_term).pack(side="left")
        pc_req = data.get("pc_requirements", {})
        min_req = limpiar_html(pc_req.get("minimum", "No especificados.")) if isinstance(pc_req, dict) else "No especificados."
        rec_req = limpiar_html(pc_req.get("recommended", "")) if isinstance(pc_req, dict) else ""
        req_box = ctk.CTkFrame(scroll, fg_color=self.card_term, corner_radius=6, border_width=1, border_color=self.border_term)
        req_box.pack(fill="x", pady=4)
        ctk.CTkLabel(req_box, text=min_req, font=("Consolas", 11), text_color=self.text_term, justify="left", anchor="w", wraplength=780).pack(anchor="w", padx=12, pady=8)
        if rec_req:
            ctk.CTkLabel(req_box, text="─" * 80, font=("Consolas", 10), text_color=self.border_term).pack(fill="x", padx=12)
            ctk.CTkLabel(req_box, text=rec_req, font=("Consolas", 11), text_color=self.text_term, justify="left", anchor="w", wraplength=780).pack(anchor="w", padx=12, pady=8)

        movies = data.get("movies", [])
        trailer_url = None
        if movies and isinstance(movies, list):
            m0 = movies[0]
            mp4_dict = m0.get("mp4", {}) if isinstance(m0.get("mp4"), dict) else {}
            webm_dict = m0.get("webm", {}) if isinstance(m0.get("webm"), dict) else {}
            trailer_url = mp4_dict.get("max") or mp4_dict.get("480") or webm_dict.get("max") or m0.get("hls_h264")
        if not trailer_url:
            trailer_url = f"https://www.youtube.com/results?search_query={self.titulo.replace(' ', '+')}+steam+trailer"

        pal = self.parent_app.palette
        fg_acc = texto_contraste_acento(pal)
        bot_bar = ctk.CTkFrame(self, fg_color=pal["panel_bg"], height=48)
        bot_bar.pack(fill="x", side="bottom", padx=16, pady=10)

        # 1. Botón de Cerrar empaquetado a la DERECHA primero (nunca se desborda ni se corta)
        ctk.CTkButton(
            bot_bar, text="[ ESC / Cerrar ]", font=("Consolas", 11, "bold"),
            fg_color="#da3633", hover_color="#f85149", text_color="white",
            width=115, height=32, command=self.destroy
        ).pack(side="right", padx=(4, 0))

        # 2. Botones de acción empaquetados a la IZQUIERDA
        ctk.CTkButton(
            bot_bar, text="🚀 App", font=("Consolas", 11, "bold"),
            width=76, fg_color=pal["accent"], text_color=fg_acc,
            hover_color=pal["accent_2"], height=32,
            command=lambda: webbrowser.open(f"steam://store/{self.appid}")
        ).pack(side="left", padx=(0, 3))

        txt_web = f"🌐 Web (-{desc_actual}%)" if desc_actual > 0 else "🌐 Web"
        w_web = 100 if desc_actual > 0 else 76
        ctk.CTkButton(
            bot_bar, text=txt_web, font=("Consolas", 11, "bold"),
            width=w_web, fg_color="#00695c", hover_color="#00897b",
            text_color="white", height=32,
            command=lambda: webbrowser.open(f"https://store.steampowered.com/app/{self.appid}")
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            bot_bar, text="🎬 Trailer", font=("Consolas", 11, "bold"),
            width=85, fg_color=pal["accent_2"], text_color="white",
            hover_color=pal["accent"], height=32,
            command=lambda u=trailer_url: webbrowser.open(u)
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            bot_bar, text="📈 Historial", font=("Consolas", 11, "bold"),
            width=95, fg_color=pal["card_bg"], border_width=1,
            border_color=pal["accent"], text_color=pal["accent"],
            hover_color=pal["card_hover"], height=32,
            command=lambda: DialogoGraficoHistorico(self.parent_app, self.titulo, self.parent_app.db.get_price_log(self.appid), appid=self.appid, item_ref=self.item_ref)
        ).pack(side="left", padx=3)

        ctk.CTkButton(
            bot_bar, text="🌍 SteamDB", font=("Consolas", 11),
            width=85, fg_color=pal["card_bg"], border_width=1,
            border_color=pal["border"], text_color=self.text_term,
            hover_color=pal["card_hover"], height=32,
            command=lambda: webbrowser.open(f"https://steamdb.info/app/{self.appid}/")
        ).pack(side="left", padx=3)

        if self.item_ref:
            ctk.CTkButton(
                bot_bar, text="📸 Placa", font=("Consolas", 11, "bold"),
                width=76, fg_color=pal["card_bg"], border_width=1,
                border_color=pal["accent_2"], text_color=pal["text"],
                hover_color=pal["card_hover"], height=32,
                command=lambda: self.parent_app._exportar_placa_redes(self.item_ref)
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                bot_bar, text="📢 Discord", font=("Consolas", 11, "bold"),
                width=85, fg_color="#5865F2", hover_color="#4752C4",
                text_color="white", height=32,
                command=lambda: self.parent_app._enviar_oferta_discord(self.item_ref)
            ).pack(side="left", padx=3)

        ctk.CTkButton(
            bot_bar, text="💬 Compartir", font=("Consolas", 11, "bold"),
            width=92, fg_color="#37474f", hover_color="#455a64",
            text_color="white", height=32,
            command=lambda: self.parent_app._copiar_oferta_al_portapapeles(self.item_ref or {"appid": self.appid, "titulo": self.titulo, "precio_oferta_usd": p_actual_usd, "descuento": desc_actual})
        ).pack(side="left", padx=3)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Right>", lambda e: DialogoVisorCapturas(self, self.titulo, self.screenshots, 0) if getattr(self, "screenshots", None) else None)
        self.bind("<Left>", lambda e: DialogoVisorCapturas(self, self.titulo, self.screenshots, 0) if getattr(self, "screenshots", None) else None)

    def _cargar_captura_miniatura(self, url, lbl_widget):
        if not url:
            return
        try:
            r = HTTP_SESSION.get(url, timeout=4)
            if r.status_code == 200 and len(r.content) > 600:
                with Image.open(BytesIO(r.content)) as raw_pil:
                    raw_pil.load()
                    pil_fit = ImageOps.fit(raw_pil.convert("RGB"), (172, 96), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=pil_fit, dark_image=pil_fit, size=(172, 96))

                def _set():
                    if lbl_widget.winfo_exists():
                        lbl_widget._ctk_img = ctk_img
                        lbl_widget.configure(image=ctk_img, text="")
                self.after(0, _set)
        except Exception:
            pass

    def _abrir_captura_hd(self, url_full, num_cap=1):
        """Redirige al visor interactivo de capturas (compatibilidad SRP)."""
        idx = max(0, num_cap - 1)
        scs = getattr(self, "screenshots", []) or [{"path_full": url_full}]
        DialogoVisorCapturas(self, self.titulo, scs, idx)


class DialogoConfiguracion(ctk.CTkToplevel):
    """Panel de ajustes generales, cotización del dólar y backups portátiles (.zip/.db) (SRP)."""
    def __init__(self, parent, config_manager, db_manager, on_save_callback):
        super().__init__(parent)
        pal = parent.palette
        self.title(f"⚙ Ajustes de {APP_NAME} v{APP_VERSION}")
        self.geometry("460x650")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])
        self.parent_app = parent
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.on_save_callback = on_save_callback

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 230
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 325
        self.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=15)
        ctk.CTkLabel(frame, text="Steam ID o Vanity:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=0, column=0, sticky="w", pady=7)
        id_frame = ctk.CTkFrame(frame, fg_color="transparent")
        id_frame.grid(row=0, column=1, padx=10, sticky="w")
        self.ent_steam = ctk.CTkEntry(id_frame, width=170, placeholder_text="Ej: 765611... o patoma89", fg_color=pal["card_bg"], text_color=pal["text"], border_color=pal["border"])
        self.ent_steam.pack(side="left")
        ctk.CTkButton(id_frame, text="?", width=28, fg_color=pal["accent"], text_color=texto_contraste_acento(pal), command=lambda: mostrar_alerta_skin(self, "¿Qué ID ingresar?", "Ingresá tu Steam ID de 17 dígitos o tu nombre de usuario público.")).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(frame, text="Steam API Key:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=1, column=0, sticky="w", pady=7)
        api_frame = ctk.CTkFrame(frame, fg_color="transparent")
        api_frame.grid(row=1, column=1, padx=10, sticky="w")
        self.ent_api = ctk.CTkEntry(api_frame, width=138, placeholder_text="Requerida p/ Biblioteca", fg_color=pal["card_bg"], text_color=pal["text"], border_color=pal["border"])
        self.ent_api.pack(side="left")
        ctk.CTkButton(api_frame, text="🔑 Web", width=56, fg_color=pal["accent_2"], hover_color=pal["accent"], text_color="white", font=("Segoe UI", 11, "bold"), command=lambda: webbrowser.open("https://steamcommunity.com/dev/apikey")).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(frame, text="Dólar Base (ARS):", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=2, column=0, sticky="w", pady=7)
        dolar_frame = ctk.CTkFrame(frame, fg_color="transparent")
        dolar_frame.grid(row=2, column=1, padx=10, sticky="w")
        self.ent_dolar = ctk.CTkEntry(dolar_frame, width=105, fg_color=pal["card_bg"], text_color=pal["text"], border_color=pal["border"])
        self.ent_dolar.pack(side="left")
        self.btn_act_dolar = ctk.CTkButton(dolar_frame, text="💳 Tarj", width=48, fg_color=pal["accent"], text_color=texto_contraste_acento(pal), font=("Segoe UI", 11, "bold"), command=lambda: self._obtener_dolar_online("oficial", 60))
        self.btn_act_dolar.pack(side="left", padx=(4, 2))
        self.btn_act_cripto = ctk.CTkButton(dolar_frame, text="🪙 Cripto", width=54, fg_color=pal["accent_2"], text_color="white", font=("Segoe UI", 11, "bold"), command=lambda: self._obtener_dolar_online("cripto", 0))
        self.btn_act_cripto.pack(side="left", padx=(2, 0))

        ctk.CTkLabel(frame, text="Impuestos (%):", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=3, column=0, sticky="w", pady=7)
        self.ent_impuestos = ctk.CTkEntry(frame, width=200, fg_color=pal["card_bg"], text_color=pal["text"], border_color=pal["border"])
        self.ent_impuestos.grid(row=3, column=1, padx=10)

        ctk.CTkLabel(frame, text="Umbral Alertas (%):", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=4, column=0, sticky="w", pady=7)
        self.ent_umbral = ctk.CTkEntry(frame, width=200, fg_color=pal["card_bg"], text_color=pal["text"], border_color=pal["border"])
        self.ent_umbral.grid(row=4, column=1, padx=10)

        ctk.CTkLabel(frame, text="Discord Webhook:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=5, column=0, sticky="w", pady=7)
        self.ent_webhook = ctk.CTkEntry(frame, width=200, placeholder_text="URL Webhook (Opcional)", fg_color=pal["card_bg"], text_color=pal["text"], border_color=pal["border"])
        self.ent_webhook.grid(row=5, column=1, padx=10)

        ctk.CTkLabel(frame, text="Al Minimizar:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=6, column=0, sticky="w", pady=7)
        self.seg_min = ctk.CTkSegmentedButton(frame, values=["Barra", "Bandeja", "Preguntar"], selected_color=pal["accent"], text_color=texto_contraste_acento(pal) if pal["mode"] == "Dark" else "white")
        self.seg_min.grid(row=6, column=1, padx=10, sticky="w")

        ctk.CTkLabel(frame, text="Sonidos UI (SFX):", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=7, column=0, sticky="w", pady=7)
        self.sw_sfx = ctk.CTkSwitch(frame, text="Efectos sonoros activos", progress_color=pal["accent"], text_color=pal["text"])
        self.sw_sfx.grid(row=7, column=1, padx=10, sticky="w")

        ctk.CTkLabel(frame, text="Centinela Wishlist:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=8, column=0, sticky="w", pady=7)
        watch_frame = ctk.CTkFrame(frame, fg_color="transparent")
        watch_frame.grid(row=8, column=1, padx=10, sticky="w")
        self.sw_watchdog = ctk.CTkSwitch(watch_frame, text="Activo", progress_color=pal["accent"], text_color=pal["text"], width=70)
        self.sw_watchdog.pack(side="left")
        self.combo_watch_int = ctk.CTkComboBox(watch_frame, values=["2 hs", "4 hs", "6 hs", "12 hs", "24 hs"], state="readonly", width=85)
        self.combo_watch_int.set("6 hs")
        self.combo_watch_int.pack(side="left", padx=(6, 0))

        ctk.CTkLabel(frame, text="Gestor de Datos:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=9, column=0, sticky="w", pady=7)
        backup_frame = ctk.CTkFrame(frame, fg_color="transparent")
        backup_frame.grid(row=9, column=1, padx=10, sticky="w")
        ctk.CTkButton(backup_frame, text="📥 Importar (.zip/.db)", width=98, fg_color=pal["card_bg"], border_width=1, border_color=pal["border"], text_color=pal["text"], hover_color=pal["card_hover"], font=("Segoe UI", 11, "bold"), command=self._importar_db).pack(side="left", padx=(0, 5))
        ctk.CTkButton(backup_frame, text="📤 Backup .ZIP", width=98, fg_color=pal["accent_2"], text_color="white", font=("Segoe UI", 11, "bold"), command=self._exportar_db).pack(side="left")

        ctk.CTkLabel(frame, text="Mantenimiento:", font=("Segoe UI", 12, "bold"), text_color=pal["text"]).grid(row=10, column=0, sticky="w", pady=7)
        maint_frame = ctk.CTkFrame(frame, fg_color="transparent")
        maint_frame.grid(row=10, column=1, padx=10, sticky="w")
        ctk.CTkButton(maint_frame, text="🧹 Caché", fg_color=pal["card_bg"], border_width=1, border_color=pal["accent"], text_color=pal["accent"], hover_color=pal["card_hover"], width=68, command=self._limpiar_cache).pack(side="left", padx=(0, 4))
        ctk.CTkButton(maint_frame, text="⚡ Optimizar DB", fg_color=pal["card_bg"], border_width=1, border_color=pal["accent_2"], text_color=pal["accent_2"], hover_color=pal["card_hover"], width=98, command=self._optimizar_db).pack(side="left", padx=(0, 4))
        ctk.CTkButton(maint_frame, text="🚫 Blacklist", fg_color=pal["card_bg"], border_width=1, border_color=pal["border"], text_color=pal["text"], hover_color=pal["card_hover"], width=72, command=lambda: DialogoBlacklist(self.parent_app, self.db_manager, self.on_save_callback)).pack(side="left")

        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(pady=(5, 15))
        ctk.CTkButton(btn_box, text="Guardar Cambios", command=self._guardar, fg_color=pal["accent"], text_color=texto_contraste_acento(pal), hover_color=pal["accent_2"], font=("Segoe UI", 12, "bold"), width=140).pack(side="left", padx=10)
        ctk.CTkButton(btn_box, text="Cancelar", command=self.destroy, fg_color=pal["panel_bg"], border_width=1, border_color=pal["border"], text_color=pal["text"], hover_color=pal["card_hover"], font=("Segoe UI", 12, "bold"), width=140).pack(side="left", padx=10)
        self._cargar_datos()

    def _obtener_dolar_online(self, tipo="oficial", imp_sugerido=60):
        self.btn_act_dolar.configure(state="disabled")
        self.btn_act_cripto.configure(state="disabled")

        def _fetch():
            val = consultar_dolar_api(tipo)
            if val:
                if tipo == "cripto":
                    self.config_manager.guardar_basico("dolar_cripto_ref", val)

                def _aplicar():
                    self.parent_app.sfx.play("coin")
                    self.ent_dolar.delete(0, "end")
                    self.ent_dolar.insert(0, str(val))
                    self.ent_impuestos.delete(0, "end")
                    self.ent_impuestos.insert(0, str(imp_sugerido))
                    self.parent_app._show_toast(f"💵 Dólar ({tipo}): ${val} ARS")
                self.after(0, _aplicar)
            else:
                self.after(0, lambda: mostrar_alerta_skin(self, "Aviso", "No se pudo conectar con DolarAPI ni CriptoYa.", tipo="warning"))
            self.after(0, lambda: (self.btn_act_dolar.configure(state="normal"), self.btn_act_cripto.configure(state="normal")))
        threading.Thread(target=_fetch, daemon=True).start()

    def _limpiar_cache(self):
        borrados, mb = limpiar_cache_imagenes()
        mostrar_alerta_skin(
            self, "Caché de Imágenes",
            f"🧹 Limpieza completada con éxito.\n\nSe eliminaron {borrados} portadas temporales y se recuperaron {mb} MB de espacio en disco.",
            tipo="info"
        )

    def _optimizar_db(self):
        ok = self.db_manager.optimizar_base_datos()
        if ok:
            mostrar_alerta_skin(
                self, "Optimización SQLite",
                "⚡ Base de datos compactada e indexada exitosamente (VACUUM & PRAGMA optimize).\nTu biblioteca y consultas seguirán respondiendo al instante.",
                tipo="info"
            )
        else:
            mostrar_alerta_skin(self, "Error", "No se pudo optimizar la base de datos.", tipo="error")

    def _exportar_db(self):
        fecha_str = datetime.now().strftime("%Y%m%d")
        dst = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("Backup Completo SteamScope (.zip)", "*.zip"), ("SQLite Database (.db)", "*.db")],
            initialfile=f"SteamScope_Backup_{fecha_str}.zip"
        )
        if not dst:
            return
        try:
            if dst.lower().endswith(".zip"):
                appdata_dir = obtener_ruta_appdata()
                with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
                    if os.path.exists(self.db_manager.db_path):
                        zf.write(self.db_manager.db_path, arcname="steam_cache.db")
                    if os.path.exists(self.config_manager.config_path):
                        zf.write(self.config_manager.config_path, arcname="config.json")
                    custom_th = os.path.join(appdata_dir, "custom_themes.json")
                    if os.path.exists(custom_th):
                        zf.write(custom_th, arcname="custom_themes.json")
                mostrar_alerta_skin(self, "Backup Completo", "Se exportaron tu Base de Datos (Watchlist, Historial, Ignorados) y tus Ajustes en un único archivo .ZIP portátil.")
            else:
                shutil.copy2(self.db_manager.db_path, dst)
                mostrar_alerta_skin(self, "Éxito", "Base de datos exportada.")
        except Exception as e:
            mostrar_alerta_skin(self, "Error", f"No se pudo exportar:\n{e}", tipo="error")

    def _importar_db(self):
        src = filedialog.askopenfilename(
            filetypes=[("Backup SteamScope (.zip o .db)", "*.zip *.db"), ("Archivo ZIP", "*.zip"), ("SQLite Database", "*.db")]
        )
        if src and preguntar_si_no_skin(self, "Confirmación", "Al importar se restaurarán tu base de datos y tus ajustes guardados. ¿Continuar?"):
            try:
                if src.lower().endswith(".zip"):
                    appdata_dir = obtener_ruta_appdata()
                    with zipfile.ZipFile(src, "r") as zf:
                        names = zf.namelist()
                        if "steam_cache.db" in names:
                            zf.extract("steam_cache.db", appdata_dir)
                        elif "steam_tracker.db" in names:
                            zf.extract("steam_tracker.db", appdata_dir)
                            shutil.move(os.path.join(appdata_dir, "steam_tracker.db"), self.db_manager.db_path)
                        if "config.json" in names:
                            zf.extract("config.json", appdata_dir)
                            self.config_manager.datos = self.config_manager.cargar()
                        if "custom_themes.json" in names:
                            zf.extract("custom_themes.json", appdata_dir)
                    self.db_manager.invalidate_caches()
                    mostrar_alerta_skin(self, "Éxito", "Backup completo (.ZIP) restaurado correctamente.")
                else:
                    shutil.copy2(src, self.db_manager.db_path)
                    self.db_manager.invalidate_caches()
                    mostrar_alerta_skin(self, "Éxito", "Base de datos restaurada.")
            except Exception as e:
                mostrar_alerta_skin(self, "Error", f"Falló la importación:\n{e}", tipo="error")

    def _cargar_datos(self):
        d = self.config_manager.datos
        self.ent_steam.insert(0, d.get("steam_id", ""))
        self.ent_api.insert(0, d.get("steam_api_key", ""))
        self.ent_dolar.insert(0, str(d.get("dolar_referencia", 1000.0)))
        self.ent_impuestos.insert(0, str(d.get("impuestos_pct", 60)))
        self.ent_umbral.insert(0, str(d.get("umbral_alerta_pct", 50)))
        self.ent_webhook.insert(0, d.get("discord_webhook", ""))
        self.seg_min.set(d.get("minimizar_a", "Preguntar"))
        if d.get("sfx_enabled", True):
            self.sw_sfx.select()
        else:
            self.sw_sfx.deselect()

        if d.get("watchdog_activado", True):
            self.sw_watchdog.select()
        else:
            self.sw_watchdog.deselect()
        int_hs = d.get("watchdog_intervalo_hs", 6)
        self.combo_watch_int.set(f"{int_hs} hs")

    def _guardar(self):
        try:
            int_str = self.combo_watch_int.get().replace(" hs", "").strip()
            int_val = int(int_str) if int_str.isdigit() else 6
            self.config_manager.guardar(
                self.ent_steam.get().strip(),
                self.ent_api.get().strip(),
                int(self.ent_impuestos.get()),
                float(self.ent_dolar.get().replace(',', '.')),
                int(self.ent_umbral.get()),
                self.seg_min.get(),
                bool(self.sw_sfx.get()),
                self.ent_webhook.get().strip(),
                watchdog_activado=bool(self.sw_watchdog.get()),
                watchdog_intervalo_hs=int_val
            )
            self.parent_app._actualizar_barra_carrito()
            self.on_save_callback()
            if self.ent_steam.get().strip():
                self.parent_app.after(100, self.parent_app._iniciar_analisis_biblioteca)
            self.destroy()
        except ValueError:
            mostrar_alerta_skin(self, "Error", "Ingresá valores numéricos válidos.", tipo="error")


class DialogoMinimizar(ctk.CTkToplevel):
    """Selector de modo de minimización (Barra de Tareas vs Bandeja) (SRP)."""
    def __init__(self, parent, on_normal, on_tray):
        super().__init__(parent)
        pal = parent.palette
        self.title(f"Minimizar {APP_NAME}")
        self.geometry("380x180")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])
        self.on_normal = on_normal
        self.on_tray = on_tray

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 190
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 90
        self.geometry(f"+{x}+{y}")

        ctk.CTkLabel(self, text="¿Cómo deseás minimizar la aplicación?", font=("Arial", 14, "bold"), text_color=pal["text"]).pack(pady=(22, 8))
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(pady=15)
        ctk.CTkButton(btn_box, text="Barra de Tareas", fg_color=pal["card_bg"], text_color=pal["text"], hover_color=pal["card_hover"], border_width=1, border_color=pal["border"], command=self._elegir_normal).pack(side="left", padx=8)
        ctk.CTkButton(btn_box, text="Bandeja (Reloj)", fg_color=pal["accent"], hover_color=pal["accent_2"], text_color=texto_contraste_acento(pal), command=self._elegir_tray).pack(side="left", padx=8)

    def _elegir_normal(self):
        self.destroy()
        self.on_normal()

    def _elegir_tray(self):
        self.destroy()
        self.on_tray()


class DialogoComparadorVersus(ctk.CTkToplevel):
    """Comparador Cara a Cara (Versus) entre dos juegos de Steam con análisis de métricas (SRP)."""
    def __init__(self, parent, item_a, item_b):
        super().__init__(parent)
        self.parent_app = parent
        self.item_a = item_a
        self.item_b = item_b
        pal = parent.palette

        self.title(f"⚔️ Comparador Cara a Cara: {item_a.get('titulo', 'A')[:22]} vs {item_b.get('titulo', 'B')[:22]}")
        self.geometry("900x640")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 450
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 320
        self.geometry(f"+{x}+{y}")

        self.lbl_loading = ctk.CTkLabel(
            self,
            text="⚔️ Descargando fichas técnicas en paralelo para comparar frente a frente...",
            font=("Consolas", 14, "bold"),
            text_color=pal["accent"]
        )
        self.lbl_loading.pack(expand=True)
        threading.Thread(target=self._descargar_ambos, daemon=True).start()

    def _descargar_ambos(self):
        aid_a = str(self.item_a.get("appid"))
        aid_b = str(self.item_b.get("appid"))
        res_a = self.parent_app.api_client.descargar_ficha_completa_paralelo(aid_a, self.parent_app.db)
        res_b = self.parent_app.api_client.descargar_ficha_completa_paralelo(aid_b, self.parent_app.db)
        self.after(0, lambda: self._renderizar_versus(res_a, res_b))

    def _extraer_metricas(self, item_base, res_tuple):
        data, poster_pil, review_sum, hist_global, proton_tier = res_tuple
        data = data or {}
        po = data.get("price_overview", {})
        p_usd = (po.get("final", 0) / 100.0) if po else float(item_base.get("precio_oferta_usd") or 0.0)
        desc = int(po.get("discount_percent", 0)) if po else int(item_base.get("descuento") or 0)
        atl_usd = float(hist_global[0]) if hist_global else p_usd
        metacritic = int(data.get("metacritic", {}).get("score") or 0)
        pc_req = data.get("pc_requirements", {})
        min_txt = pc_req.get("minimum", "") if isinstance(pc_req, dict) else ""
        disco_str = extraer_espacio_disco(min_txt)
        cats = [c.get("description", "").lower() for c in data.get("categories", [])]
        tiene_cromos = any("cromos" in c or "cards" in c for c in cats) or item_base.get("tiene_cromos", False)
        es_coop = any("cooperativo" in c or "co-op" in c or "multi" in c for c in cats)
        veredicto, col_v, _ = evaluar_termometro_compra(desc, item_base.get("es_atl", False), p_usd)
        return {
            "appid": str(item_base.get("appid")),
            "titulo": data.get("name") or item_base.get("titulo", "Juego"),
            "poster": poster_pil,
            "p_usd": p_usd,
            "desc": desc,
            "atl_usd": atl_usd,
            "metacritic": metacritic,
            "reviews": f"{review_sum[0]} {review_sum[1]}" if review_sum else f"Rating: {item_base.get('rating', 'N/A')}%",
            "disco": disco_str,
            "proton": proton_tier or "N/D",
            "cromos": "Sí 🃏" if tiene_cromos else "No",
            "coop": "Sí 🤝" if es_coop else "Single-Player",
            "veredicto": veredicto,
            "col_v": col_v,
            "item_raw": item_base,
        }

    def _renderizar_versus(self, res_a, res_b):
        if not self.winfo_exists():
            return
        self.lbl_loading.destroy()
        pal = self.parent_app.palette
        ma = self._extraer_metricas(self.item_a, res_a)
        mb = self._extraer_metricas(self.item_b, res_b)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkLabel(top, text="⚔️ COMPARATIVA CARA A CARA (VERSUS)", font=("Consolas", 16, "bold"), text_color=pal["accent"]).pack(side="left")
        ctk.CTkButton(top, text="Cerrar [ESC]", width=105, height=28, fg_color="#da3633", text_color="white", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())

        scroll = ctk.CTkScrollableFrame(self, fg_color=pal["panel_bg"], corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=20, pady=(4, 14))
        scroll.grid_columnconfigure(0, weight=4)
        scroll.grid_columnconfigure(1, weight=2)
        scroll.grid_columnconfigure(2, weight=4)

        # Cabecera de Pósters
        for col_idx, m in [(0, ma), (2, mb)]:
            box = ctk.CTkFrame(scroll, fg_color=pal["card_bg"], corner_radius=10, border_width=1, border_color=pal["border"])
            box.grid(row=0, column=col_idx, padx=10, pady=10, sticky="nsew")
            p_pil = m["poster"]
            if p_pil is None:
                p_pil = Image.new("RGB", (140, 210), color=(22, 27, 34))
            else:
                p_pil = p_pil.resize((140, 210), Image.Resampling.LANCZOS)
            ctk_p = ctk.CTkImage(light_image=p_pil, dark_image=p_pil, size=(140, 210))
            lbl_p = ctk.CTkLabel(box, text="", image=ctk_p)
            lbl_p._ctk_img = ctk_p
            lbl_p.pack(pady=(10, 6))
            ctk.CTkLabel(box, text=m["titulo"][:32], font=("Segoe UI", 14, "bold"), text_color=pal["text"], wraplength=310).pack(padx=8, pady=(0, 4))
            ctk.CTkLabel(box, text=m["veredicto"], font=("Consolas", 11, "bold"), text_color=m["col_v"]).pack(pady=(0, 8))

        vs_mid = ctk.CTkFrame(scroll, fg_color="transparent")
        vs_mid.grid(row=0, column=1)
        ctk.CTkLabel(vs_mid, text="⚡\nVS", font=("Segoe UI", 26, "bold"), text_color=pal["accent"]).pack()

        dolar = self.parent_app.config.datos.get("dolar_referencia", 1000.0)
        imp = self.parent_app.config.datos.get("impuestos_pct", 60)
        mult = 1 + (imp / 100.0)
        ars_a = round(ma["p_usd"] * dolar * mult)
        ars_b = round(mb["p_usd"] * dolar * mult)

        filas = [
            ("💵 Precio Actual", f"${ma['p_usd']:.2f} USD (${ars_a:,.0f} ARS)", f"${mb['p_usd']:.2f} USD (${ars_b:,.0f} ARS)",
             1 if (0 < ma["p_usd"] < mb["p_usd"]) else (2 if (0 < mb["p_usd"] < ma["p_usd"]) else 0)),
            ("🏷️ Descuento", f"-{ma['desc']}% OFF", f"-{mb['desc']}% OFF",
             1 if ma["desc"] > mb["desc"] else (2 if mb["desc"] > ma["desc"] else 0)),
            ("🔥 Mínimo Histórico", f"${ma['atl_usd']:.2f} USD", f"${mb['atl_usd']:.2f} USD",
             1 if (0 < ma["atl_usd"] < mb["atl_usd"]) else (2 if (0 < mb["atl_usd"] < ma["atl_usd"]) else 0)),
            ("🏆 Metacritic", f"{ma['metacritic']}/100" if ma["metacritic"] else "N/D", f"{mb['metacritic']}/100" if mb["metacritic"] else "N/D",
             1 if ma["metacritic"] > mb["metacritic"] else (2 if mb["metacritic"] > ma["metacritic"] else 0)),
            ("👥 Reseñas Steam", ma["reviews"], mb["reviews"], 0),
            ("💾 Espacio en Disco", ma["disco"], mb["disco"], 0),
            ("🐧 Steam Deck / Proton", ma["proton"], mb["proton"], 0),
            ("🃏 Cromos de Steam", ma["cromos"], mb["cromos"], 1 if ("Sí" in ma["cromos"] and "No" in mb["cromos"]) else (2 if ("Sí" in mb["cromos"] and "No" in ma["cromos"]) else 0)),
            ("🎮 Modalidad", ma["coop"], mb["coop"], 0),
        ]

        pts_a = sum(1 for f in filas if f[3] == 1)
        pts_b = sum(1 for f in filas if f[3] == 2)

        for idx, (label_cat, val_a, val_b, winner) in enumerate(filas, start=1):
            col_a = "#00e676" if winner == 1 else pal["text"]
            col_b = "#00e676" if winner == 2 else pal["text"]
            fa = ctk.CTkFrame(scroll, fg_color=pal["card_bg"], corner_radius=6, border_width=1, border_color="#00e676" if winner == 1 else pal["border"])
            fa.grid(row=idx, column=0, padx=10, pady=3, sticky="ew")
            ctk.CTkLabel(fa, text=("🏆 " if winner == 1 else "") + val_a, font=("Consolas", 12, "bold" if winner == 1 else "normal"), text_color=col_a).pack(pady=7)

            fm = ctk.CTkFrame(scroll, fg_color="transparent")
            fm.grid(row=idx, column=1, padx=4, pady=3)
            ctk.CTkLabel(fm, text=label_cat, font=("Segoe UI", 11, "bold"), text_color=pal["subtext"]).pack()

            fb = ctk.CTkFrame(scroll, fg_color=pal["card_bg"], corner_radius=6, border_width=1, border_color="#00e676" if winner == 2 else pal["border"])
            fb.grid(row=idx, column=2, padx=10, pady=3, sticky="ew")
            ctk.CTkLabel(fb, text=("🏆 " if winner == 2 else "") + val_b, font=("Consolas", 12, "bold" if winner == 2 else "normal"), text_color=col_b).pack(pady=7)

        # Botones de acción directa abajo de cada columna
        fg_acc = texto_contraste_acento(pal)
        for col_idx, m in [(0, ma), (2, mb)]:
            act = ctk.CTkFrame(scroll, fg_color="transparent")
            act.grid(row=len(filas) + 1, column=col_idx, padx=10, pady=10)
            ctk.CTkButton(act, text="🛒 Sumar al Changuito", width=155, fg_color=pal["accent"], text_color=fg_acc, hover_color=pal["accent_2"], command=lambda it=m["item_raw"]: self.parent_app._toggle_carrito_item(it)).pack(side="left", padx=4)
            ctk.CTkButton(act, text="🖥️ Ficha", width=95, fg_color=pal["card_bg"], border_width=1, border_color=pal["accent"], text_color=pal["accent"], hover_color=pal["card_hover"], command=lambda it=m["item_raw"]: DialogoFichaJuego(self.parent_app, it["appid"], it["titulo"], it)).pack(side="left", padx=4)

        veredicto_vs = "🤝 Empate técnico" if pts_a == pts_b else (f"🏆 Ventaja: {ma['titulo'][:20]}" if pts_a > pts_b else f"🏆 Ventaja: {mb['titulo'][:20]}")
        ctk.CTkLabel(scroll, text=veredicto_vs, font=("Segoe UI", 12, "bold"), text_color=pal["accent"]).grid(row=len(filas) + 1, column=1)


class DialogoHistorialATL(ctk.CTkToplevel):
    """Modal skin-aware que muestra las alertas de récords históricos cazadas por el Centinela (SRP)."""
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.pal = parent_app.palette
        self.title("SteamScope - Historial de Récords Históricos (ATL)")
        self.geometry("680x480")
        self.resizable(False, False)
        self.configure(fg_color=self.pal["win_bg"])
        self.transient(parent_app)
        self.grab_set()

        # Centrar ventana
        try:
            x = parent_app.winfo_x() + (parent_app.winfo_width() // 2) - 340
            y = parent_app.winfo_y() + (parent_app.winfo_height() // 2) - 240
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 8))

        lbl_box = ctk.CTkFrame(top, fg_color="transparent")
        lbl_box.pack(side="left")
        ctk.CTkLabel(
            lbl_box, text="⭐ HISTORIAL DE RÉCORDS HISTÓRICOS (ATL)",
            font=("Consolas", 15, "bold"), text_color=self.pal["accent"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            lbl_box, text="Ofertas récord detectadas en segundo plano por el Centinela silencioso.",
            font=("Segoe UI", 11), text_color=self.pal["subtext"]
        ).pack(anchor="w")

        btn_box = ctk.CTkFrame(top, fg_color="transparent")
        btn_box.pack(side="right")
        ctk.CTkButton(
            btn_box, text="🗑 Limpiar", width=85, height=28,
            fg_color="#b71c1c", hover_color="#d32f2f", text_color="white",
            command=self._limpiar
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_box, text="Cerrar [ESC]", width=95, height=28,
            fg_color=self.pal["card_bg"], border_width=1, border_color=self.pal["border"],
            text_color=self.pal["text"], hover_color=self.pal["card_hover"],
            command=self.destroy
        ).pack(side="left", padx=4)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=self.pal["panel_bg"], corner_radius=10)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(4, 15))

        self.bind("<Escape>", lambda e: self.destroy())
        self._cargar_alertas()

    def _cargar_alertas(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        alertas = self.parent_app.db.obtener_alertas_atl(limite=50)
        if not alertas:
            ctk.CTkLabel(
                self.scroll,
                text="🔔 No hay récords históricos registrados todavía.\n\nEl Centinela guardará aquí automáticamente las ofertas récord\ncada vez que un juego de tu Wishlist rompa su precio mínimo histórico.",
                font=("Segoe UI", 12), text_color=self.pal["subtext"], justify="center"
            ).pack(pady=50)
            return

        for a in alertas:
            card = ctk.CTkFrame(
                self.scroll, fg_color=self.pal["card_bg"], corner_radius=8,
                border_width=1, border_color=self.pal["border"]
            )
            card.pack(fill="x", pady=4, padx=6)

            info_f = ctk.CTkFrame(card, fg_color="transparent")
            info_f.pack(side="left", fill="both", expand=True, padx=12, pady=8)

            t_row = ctk.CTkFrame(info_f, fg_color="transparent")
            t_row.pack(anchor="w", fill="x")

            ctk.CTkLabel(
                t_row, text=a["titulo"], font=("Segoe UI", 13, "bold"),
                text_color=self.pal["text"]
            ).pack(side="left")
            ctk.CTkLabel(
                t_row, text=" ⭐ RÉCORD ATL ", fg_color="#ffd700",
                text_color="#000000", corner_radius=4, font=("Segoe UI", 9, "bold")
            ).pack(side="left", padx=6)

            ctk.CTkLabel(
                info_f, text=f"📅 Registrado: {a['fecha']}",
                font=("Consolas", 10), text_color=self.pal["subtext"]
            ).pack(anchor="w", pady=(2, 0))

            act_f = ctk.CTkFrame(card, fg_color="transparent")
            act_f.pack(side="right", padx=10, pady=8)

            if a.get("desc_pct", 0) > 0:
                ctk.CTkLabel(
                    act_f, text=f"-{a['desc_pct']}%", fg_color=self.pal["deal_badge"],
                    text_color=self.pal["deal_text"], corner_radius=4, font=("Consolas", 12, "bold"),
                    width=48, height=26
                ).pack(side="left", padx=4)

            ctk.CTkLabel(
                act_f, text=f"${a['precio_usd']:.2f} USD", font=("Consolas", 13, "bold"),
                text_color=self.pal["accent"]
            ).pack(side="left", padx=6)

            ctk.CTkButton(
                act_f, text="🚀 Steam", width=68, height=26, corner_radius=6,
                font=("Segoe UI", 11, "bold"), fg_color=self.pal["accent_2"],
                hover_color=self.pal["accent"], text_color="white",
                command=lambda aid=a["appid"]: webbrowser.open(f"steam://store/{aid}")
            ).pack(side="left", padx=4)

    def _limpiar(self):
        self.parent_app.db.limpiar_alertas_atl()
        self._cargar_alertas()


class DialogoCommandPalette(ctk.CTkToplevel):
    """
    Buscador rápido global tipo Spotlight / Discord (Ctrl+K) (SRP).
    Permite filtrar en tiempo real sobre Ofertas, Watchlist y Biblioteca.
    """
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.pal = parent_app.palette
        self.title("SteamScope - Búsqueda Rápida Global [Ctrl+K]")
        self.geometry("660x520")
        self.resizable(False, False)
        self.configure(fg_color=self.pal["win_bg"])
        self.transient(parent_app)
        self.grab_set()

        try:
            x = parent_app.winfo_x() + (parent_app.winfo_width() // 2) - 330
            y = parent_app.winfo_y() + (parent_app.winfo_height() // 2) - 260
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self.bind("<Escape>", lambda e: self.destroy())

        top = ctk.CTkFrame(self, fg_color=self.pal["panel_bg"], corner_radius=10)
        top.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(top, text="⚡", font=("Segoe UI", 16)).pack(side="left", padx=(12, 6))

        self.ent_search = ctk.CTkEntry(
            top, placeholder_text="Escribí el nombre de cualquier juego (ESC para salir)...",
            font=("Segoe UI", 13), fg_color="transparent", border_width=0,
            text_color=self.pal["text"]
        )
        self.ent_search.pack(side="left", fill="x", expand=True, padx=4, pady=8)
        self.ent_search.bind("<KeyRelease>", self._on_type)
        self.after(60, self.ent_search.focus_set)

        self.lbl_count = ctk.CTkLabel(top, text="", font=("Segoe UI", 11), text_color=self.pal["subtext"])
        self.lbl_count.pack(side="right", padx=12)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=self.pal["panel_bg"], corner_radius=10)
        self.scroll.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self._render_resultados("")

    def _on_type(self, event=None):
        texto = self.ent_search.get().strip()
        self._render_resultados(texto)

    def _render_resultados(self, query):
        for w in self.scroll.winfo_children():
            w.destroy()

        q = normalizar_texto(query)
        encontrados = []

        # 0. Acciones del Sistema (Comandos Rápidos)
        acciones_rapidas = [
            {"titulo": "🎁 Abrir Radar de Regalos Epic Games", "detalle": "Juegos Gratis Semanales", "action": lambda: DialogoRadarRegalos(self.parent_app)},
            {"titulo": "🃏 Abrir Gestor de Cromos & Billetera Steam", "detalle": "Fondear Carrito", "action": lambda: DialogoGestorCromos(self.parent_app)},
            {"titulo": "🎲 Girar Ruleta de Ofertas Sorpresa", "detalle": "Descubrir juego", "action": self.parent_app._lanzar_ruleta_sorpresa},
            {"titulo": "🛒 Ver Carrito de Compras", "detalle": "Total y Ahorro", "action": self.parent_app._abrir_modal_carrito},
        ]
        for acc in acciones_rapidas:
            if not q or q in normalizar_texto(acc["titulo"]) or (q and q in "radar regalos cromos ruleta carrito"):
                encontrados.append({
                    "origen": "⚡ Acción",
                    "origen_color": "#00e676",
                    "appid": None,
                    "titulo": acc["titulo"],
                    "detalle": acc["detalle"],
                    "action": acc["action"],
                    "raw": None
                })

        # 1. Buscar en Ofertas cargadas
        for d in (self.parent_app.deals_data or []):
            if not q or q in normalizar_texto(d.get("titulo", "")):
                encontrados.append({
                    "origen": "🔥 Oferta",
                    "origen_color": "#ff7518",
                    "appid": d.get("appid"),
                    "titulo": d.get("titulo", "Juego"),
                    "detalle": f"-{d.get('descuento', 0)}% ➔ ${d.get('precio_oferta_usd', 0.0):.2f} USD",
                    "raw": d
                })
                if len(encontrados) >= 40:
                    break

        # 2. Buscar en Watchlist
        if len(encontrados) < 40:
            for w in self.parent_app.db.get_all_watchlist():
                aid = str(w[0])
                tit = str(w[1])
                p_guard = float(w[2] or 0.0)
                if not q or q in normalizar_texto(tit):
                    encontrados.append({
                        "origen": "⭐ Watchlist",
                        "origen_color": "#ffd700",
                        "appid": aid,
                        "titulo": tit,
                        "detalle": f"Guardado a ${p_guard:.2f} USD",
                        "raw": {"appid": aid, "titulo": tit, "precio_oferta_usd": p_guard, "link": f"https://store.steampowered.com/app/{aid}"}
                    })
                    if len(encontrados) >= 40:
                        break

        # 3. Buscar en Mi Biblioteca
        if len(encontrados) < 40:
            for b in (self.parent_app.biblioteca_data or []):
                aid = str(b.get("appid"))
                tit = str(b.get("titulo", ""))
                hrs = float(b.get("horas", 0.0))
                if not q or q in normalizar_texto(tit):
                    encontrados.append({
                        "origen": "🎮 Biblioteca",
                        "origen_color": "#00e676",
                        "appid": aid,
                        "titulo": tit,
                        "detalle": f"{hrs:.1f} hs jugadas",
                        "raw": {"appid": aid, "titulo": tit, "precio_oferta_usd": float(b.get("price_usd", 0.0)), "link": f"https://store.steampowered.com/app/{aid}"}
                    })
                    if len(encontrados) >= 40:
                        break

        self.lbl_count.configure(text=f"{len(encontrados)} resultados")

        if not encontrados:
            ctk.CTkLabel(
                self.scroll,
                text="🔍 No se encontraron coincidencias.\nProbá con otra palabra clave.",
                font=("Segoe UI", 12), text_color=self.pal["subtext"]
            ).pack(pady=40)
            return

        for item in encontrados[:25]:
            row = ctk.CTkFrame(
                self.scroll, fg_color=self.pal["card_bg"], corner_radius=6,
                border_width=1, border_color=self.pal["border"], cursor="hand2"
            )
            row.pack(fill="x", pady=2, padx=4)

            badge = ctk.CTkFrame(row, fg_color="transparent")
            badge.pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(badge, text=item["origen"], font=("Consolas", 10, "bold"), text_color=item["origen_color"]).pack()

            lbl_tit = ctk.CTkLabel(row, text=item["titulo"][:45], font=("Segoe UI", 12, "bold"), text_color=self.pal["text"], anchor="w")
            lbl_tit.pack(side="left", fill="x", expand=True, padx=4)

            lbl_det = ctk.CTkLabel(row, text=item["detalle"], font=("Consolas", 11), text_color=self.pal["subtext"])
            lbl_det.pack(side="right", padx=10)

            def _abrir(it=item):
                self.destroy()
                if it.get("action"):
                    it["action"]()
                elif it.get("appid"):
                    DialogoFichaJuego(self.parent_app, it["appid"], it["titulo"], it["raw"])

            row.bind("<Button-1>", lambda e, it=item: _abrir(it))
            lbl_tit.bind("<Button-1>", lambda e, it=item: _abrir(it))
            lbl_det.bind("<Button-1>", lambda e, it=item: _abrir(it))


class DialogoRadarRegalos(ctk.CTkToplevel):
    """Radar de Juegos Gratis Semanales de Epic Games Store (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        pal = parent.palette
        self.parent_app = parent
        self.title("🎁 Radar de Juegos Gratis - Epic Games Store")
        self.geometry("780x600")
        self.minsize(680, 480)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 390
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 300
        self.geometry(f"+{max(20, x)}+{max(20, y)}")

        # Encabezado
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 8))
        
        ctk.CTkLabel(top, text="🎁 Radar de Juegos Gratuitos Semanales", font=("Segoe UI", 16, "bold"), text_color=pal["accent"]).pack(side="left")
        ctk.CTkLabel(top, text="⚡ 100% Legal & Oficial", font=("Segoe UI", 10, "bold"), fg_color="#107c10", text_color="white", corner_radius=4).pack(side="left", padx=10)

        ctk.CTkButton(top, text="🔄 Refrescar", width=100, height=28, fg_color=pal["card_bg"], hover_color=pal["card_hover"], border_width=1, border_color=pal["border"], text_color=pal["text"], command=self._cargar_promociones_async).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=10, fg_color=pal["panel_bg"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=8)

        # Barra inferior
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=20, pady=(6, 15))
        ctk.CTkButton(bot, text="🌐 Abrir Epic Games Store", width=200, height=32, fg_color=pal["accent_2"], hover_color=pal["accent"], text_color="white", font=("Segoe UI", 11, "bold"), command=lambda: webbrowser.open("https://store.epicgames.com/es-ES/free-games")).pack(side="left")
        ctk.CTkButton(bot, text="Cerrar", width=100, height=32, fg_color=pal["border"], hover_color=pal["card_hover"], text_color=pal["text"], command=self.destroy).pack(side="right")

        self._cargar_promociones_async()

    def _cargar_promociones_async(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        lbl_cargando = ctk.CTkLabel(self.scroll, text="⏳ Obteniendo promociones activas de Epic Games Store...", font=("Segoe UI", 13), text_color=self.parent_app.palette["accent"])
        lbl_cargando.pack(pady=60)
        
        def _hilo():
            items = obtener_promociones_epic()
            self.after(0, lambda: self._render_promociones(items, lbl_cargando))
        threading.Thread(target=_hilo, daemon=True).start()

    def _render_promociones(self, items, lbl_loader):
        if not self.winfo_exists():
            return
        lbl_loader.destroy()
        pal = self.parent_app.palette

        if not items:
            ctk.CTkLabel(self.scroll, text="No se pudieron cargar promociones o no hay juegos gratis activos en este momento.", font=("Segoe UI", 12), text_color=pal["subtext"]).pack(pady=40)
            return

        for itm in items:
            card = ctk.CTkFrame(self.scroll, fg_color=pal["card_bg"], corner_radius=10, border_width=1, border_color=pal["border"])
            card.pack(fill="x", pady=6, padx=4)

            lbl_img = ctk.CTkLabel(card, text="🎮...", width=160, height=84, fg_color=pal["win_bg"], corner_radius=6, cursor="hand2")
            lbl_img.pack(side="left", padx=10, pady=10)
            lbl_img.bind("<Button-1>", lambda e, u=itm["url_tienda"]: webbrowser.open(u))

            img_url = itm.get("imagen_url")
            if img_url:
                self.parent_app.ui_executor.submit(self._cargar_imagen_epic_async, img_url, lbl_img)

            info_col = ctk.CTkFrame(card, fg_color="transparent")
            info_col.pack(side="left", fill="both", expand=True, padx=8, pady=8)

            tit_row = ctk.CTkFrame(info_col, fg_color="transparent")
            tit_row.pack(fill="x", anchor="w")
            ctk.CTkLabel(tit_row, text=itm["titulo"][:40], font=("Segoe UI", 14, "bold"), text_color=pal["text"]).pack(side="left")

            col_badge = "#00c853" if itm["es_activo"] else "#0288d1"
            txt_badge = " 🔥 DISPONIBLE AHORA " if itm["es_activo"] else " ⏳ PRÓXIMA SEMANA "
            ctk.CTkLabel(tit_row, text=txt_badge, font=("Segoe UI", 9, "bold"), fg_color=col_badge, text_color="white", corner_radius=4).pack(side="left", padx=8)

            desc = itm.get("descripcion", "")
            desc_corta = (desc[:90] + "...") if len(desc) > 90 else desc
            ctk.CTkLabel(info_col, text=desc_corta, font=("Segoe UI", 11), text_color=pal["subtext"], justify="left", anchor="w", wraplength=380).pack(anchor="w", pady=(2, 4))

            fechas_txt = f"Vence el: {itm['fecha_fin']}" if itm.get("fecha_fin") else "Promoción por tiempo limitado"
            ctk.CTkLabel(info_col, text=f"📅 {fechas_txt}", font=("Consolas", 10), text_color=pal["accent"]).pack(anchor="w")

            act_col = ctk.CTkFrame(card, fg_color="transparent")
            act_col.pack(side="right", padx=14, pady=10)

            orig_p = itm.get("precio_original_usd", 0.0)
            if orig_p > 0:
                ctk.CTkLabel(act_col, text=f"${orig_p:.2f} USD", font=("Consolas", 10, "overstrike"), text_color=pal["subtext"]).pack(anchor="e")
            ctk.CTkLabel(act_col, text="GRATIS", font=("Consolas", 14, "bold"), text_color="#00e676").pack(anchor="e", pady=(0, 4))

            btn_txt = "🎁 Reclamar" if itm["es_activo"] else "🔍 Ver en Epic"
            btn_col = "#00c853" if itm["es_activo"] else pal["panel_bg"]
            btn_text_col = "white" if itm["es_activo"] else pal["text"]
            ctk.CTkButton(act_col, text=btn_txt, width=105, height=28, font=("Segoe UI", 11, "bold"), fg_color=btn_col, text_color=btn_text_col, hover_color="#00e676", command=lambda u=itm["url_tienda"]: webbrowser.open(u)).pack(anchor="e")

    def _cargar_imagen_epic_async(self, url, lbl_widget):
        try:
            r = HTTP_SESSION.get(url, timeout=4)
            if r.status_code == 200 and len(r.content) > 500:
                with Image.open(BytesIO(r.content)) as raw_pil:
                    raw_pil.load()
                    pil_fit = ImageOps.fit(raw_pil.convert("RGB"), (160, 84), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=pil_fit, dark_image=pil_fit, size=(160, 84))

                def _set():
                    if lbl_widget.winfo_exists():
                        lbl_widget._ctk_img = ctk_img
                        lbl_widget.configure(image=ctk_img, text="")
                self.after(0, _set)
        except Exception:
            pass


class DialogoGestorCromos(ctk.CTkToplevel):
    """Gestor y Valorizador de Cromos de la Billetera Steam (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        pal = parent.palette
        self.parent_app = parent
        self.title("🃏 Billetera & Gestor de Cromos Steam - SteamScope 2.0")
        self.geometry("680x560")
        self.minsize(600, 460)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 340
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 280
        self.geometry(f"+{max(20, x)}+{max(20, y)}")

        # Encabezado
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(15, 8))
        ctk.CTkLabel(top, text="🃏 Billetera & Valorizador de Cromos", font=("Segoe UI", 16, "bold"), text_color=pal["accent"]).pack(side="left")

        ctk.CTkButton(top, text="🔄 Analizar", width=95, height=28, fg_color=pal["card_bg"], hover_color=pal["card_hover"], border_width=1, border_color=pal["border"], text_color=pal["text"], command=lambda: self._analizar_async(forzar=True)).pack(side="right")

        # Contenedor de métricas / KPIs
        self.kpis_frame = ctk.CTkFrame(self, fg_color=pal["card_bg"], corner_radius=10, border_width=1, border_color=pal["border"])
        self.kpis_frame.pack(fill="x", padx=20, pady=6)

        self.lbl_kpi_total = ctk.CTkLabel(self.kpis_frame, text="🃏 Cromos: --", font=("Segoe UI", 12, "bold"), text_color=pal["text"])
        self.lbl_kpi_total.pack(side="left", padx=15, pady=10)

        self.lbl_kpi_bruto = ctk.CTkLabel(self.kpis_frame, text="💵 Valor Bruto: --", font=("Segoe UI", 12), text_color=pal["subtext"])
        self.lbl_kpi_bruto.pack(side="left", padx=10, pady=10)

        self.lbl_kpi_neto = ctk.CTkLabel(self.kpis_frame, text="👛 Cartera Neta (-15%): --", font=("Segoe UI", 13, "bold"), text_color="#00e676")
        self.lbl_kpi_neto.pack(side="right", padx=15, pady=10)

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=10, fg_color=pal["panel_bg"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=8)

        # Barra inferior
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=20, pady=(6, 15))
        ctk.CTkButton(bot, text="💰 Mercado de Steam", width=170, height=32, fg_color="#00695c", hover_color="#00897b", text_color="white", font=("Segoe UI", 11, "bold"), command=lambda: webbrowser.open("https://steamcommunity.com/market/")).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bot, text="🏆 Mis Insignias", width=140, height=32, fg_color=pal["card_bg"], hover_color=pal["card_hover"], border_width=1, border_color=pal["border"], text_color=pal["text"], font=("Segoe UI", 11), command=lambda: webbrowser.open("https://steamcommunity.com/my/badges/")).pack(side="left")
        ctk.CTkButton(bot, text="Cerrar", width=100, height=32, fg_color=pal["border"], hover_color=pal["card_hover"], text_color=pal["text"], command=self.destroy).pack(side="right")

        self._analizar_async()

    def _analizar_async(self, forzar: bool = False):
        for w in self.scroll.winfo_children():
            w.destroy()
        lbl_loader = ctk.CTkLabel(self.scroll, text="⏳ Conectando con Steam Community Inventory...", font=("Segoe UI", 13), text_color=self.parent_app.palette["accent"])
        lbl_loader.pack(pady=50)

        steamid = self.parent_app.config.datos.get("steam_id", "")
        dolar = self.parent_app.config.datos.get("dolar_referencia", 1000.0)

        def _hilo():
            res = analizar_inventario_cromos(steamid, dolar, forzar_refresco=forzar)
            self.after(0, lambda: self._mostrar_resultado(res, lbl_loader))
        threading.Thread(target=_hilo, daemon=True).start()

    def _mostrar_resultado(self, res, lbl_loader):
        if not self.winfo_exists():
            return
        lbl_loader.destroy()
        pal = self.parent_app.palette

        if not res.get("exito"):
            err = res.get("error", "Error desconocido.")
            ctk.CTkLabel(self.scroll, text=f"❌ {err}", font=("Segoe UI", 12), text_color="#ff5252", justify="center", wraplength=520).pack(pady=40)
            return

        total_c = res["total_cromos"]
        val_bruto = res["valor_bruto_usd"]
        val_neto = res["valor_neto_usd"]
        val_ars = res["valor_neto_ars"]

        self.lbl_kpi_total.configure(text=f"🃏 {total_c} Cromos en {res['total_juegos']} Juegos")
        self.lbl_kpi_bruto.configure(text=f"💵 Bruto: ${val_bruto:.2f} USD")
        self.lbl_kpi_neto.configure(text=f"👛 Billetera Neta: ${val_neto:.2f} USD (~${val_ars:,.0f} ARS)")

        if not res.get("juegos"):
            ctk.CTkLabel(self.scroll, text="No se encontraron cromos vendibles en tu inventario público de Steam.", font=("Segoe UI", 12), text_color=pal["subtext"]).pack(pady=40)
            return

        for j in res["juegos"]:
            row = ctk.CTkFrame(self.scroll, fg_color=pal["card_bg"], corner_radius=8, border_width=1, border_color=pal["border"])
            row.pack(fill="x", pady=3, padx=4)

            ctk.CTkLabel(row, text=j["game_name"][:40], font=("Segoe UI", 12, "bold"), text_color=pal["text"]).pack(side="left", padx=12, pady=8)

            ctk.CTkLabel(row, text=f"{j['cantidad']} cromo(s)", font=("Consolas", 11), text_color=pal["subtext"]).pack(side="left", padx=8)

            net_juego = round(j['cantidad'] * 0.06 * 0.85, 2)
            ctk.CTkLabel(row, text=f"+${net_juego:.2f} USD a wallet", font=("Consolas", 11, "bold"), text_color="#00e676").pack(side="right", padx=12)


