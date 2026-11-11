import threading
from datetime import datetime, timedelta
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class DialogoGraficoHistorico(ctk.CTkToplevel):
    """Ventana modal dedicada al gráfico interactivo de historial de precios (SRP)."""
    def __init__(self, parent, titulo_juego, registros=None, appid=None, item_ref=None):
        super().__init__(parent)
        self.parent_app = parent
        self.titulo_juego = titulo_juego
        self.appid = str(appid) if appid else (str(registros[0][0]) if registros else None)
        self.item_ref = item_ref or {}
        pal = parent.palette
        self.title(f"📈 Historial de Precios: {titulo_juego}")
        self.geometry("740x480")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])
        self.fig = None

        self.lbl_loading = ctk.CTkLabel(
            self,
            text="⏳ Consultando historial global en Steam / CheapShark y base local...",
            font=("Consolas", 13, "bold"),
            text_color=pal["accent"]
        )
        self.lbl_loading.pack(expand=True)
        self.protocol("WM_DELETE_WINDOW", self._cerrar_grafico)

        threading.Thread(target=self._cargar_y_dibujar, daemon=True).start()

    def _cargar_y_dibujar(self):
        info_atl = None
        if self.appid and hasattr(self.parent_app, "api_client"):
            info_atl = self.parent_app.api_client.obtener_historial_global_cheapshark(
                self.appid, db_manager=self.parent_app.db
            )
        registros_actualizados = self.parent_app.db.get_price_log(self.appid) if self.appid else []
        self.after(0, lambda: self._renderizar_plot(registros_actualizados, info_atl))

    def _renderizar_plot(self, registros, info_atl):
        if not self.winfo_exists():
            return
        if hasattr(self, "lbl_loading") and self.lbl_loading.winfo_exists():
            self.lbl_loading.destroy()

        pal = self.parent_app.palette
        if not registros and not info_atl:
            ctk.CTkLabel(self, text="No hay suficientes datos históricos para este juego.", font=("Segoe UI", 14), text_color=pal["text"]).pack(expand=True)
            return

        fechas = [datetime.strptime(r[2], "%Y-%m-%d") for r in registros]
        precios = [float(r[1]) for r in registros]

        precio_normal = float(self.item_ref.get("precio_normal_usd") or 0.0)
        if info_atl and info_atl.get("retail_price", 0) > precio_normal:
            precio_normal = float(info_atl["retail_price"])
        atl_global = float(info_atl["atl_price"]) if info_atl and info_atl.get("atl_price") else (min(precios) if precios else 0.0)
        atl_fecha_str = info_atl.get("atl_date_display") if info_atl else ""

        top_info = ctk.CTkFrame(self, fg_color=pal["panel_bg"], corner_radius=8)
        top_info.pack(fill="x", padx=12, pady=(10, 0))
        actual_usd = precios[-1] if precios else float(self.item_ref.get("precio_oferta_usd") or 0.0)
        resumen_txt = f"💵 Actual: ${actual_usd:.2f} USD"
        if precio_normal > 0:
            resumen_txt += f"   |   🏷️ Precio Normal Base: ${precio_normal:.2f} USD"
        if atl_global > 0:
            resumen_txt += f"   |   🔥 Récord Histórico Real: ${atl_global:.2f} USD" + (f" ({atl_fecha_str})" if atl_fecha_str else "")
        ctk.CTkLabel(top_info, text=resumen_txt, font=("Consolas", 11, "bold"), text_color=pal["accent"]).pack(padx=12, pady=7)

        self.fig, ax = plt.subplots(figsize=(7.2, 4.0), facecolor=pal["win_bg"])
        ax.set_facecolor(pal["card_bg"])

        if len(fechas) == 1 and precio_normal > precios[0]:
            fechas = [fechas[0] - timedelta(days=30), fechas[0]]
            precios = [precio_normal, precios[0]]

        ax.plot(fechas, precios, color=pal["accent"], linewidth=6, alpha=0.15)
        ax.plot(fechas, precios, marker='o', color=pal["accent"], linestyle='-', linewidth=2.5, markersize=7, markeredgecolor=pal["win_bg"], markeredgewidth=1, label="Precio registrado")

        if precio_normal > 0:
            ax.axhline(y=precio_normal, color="#8b929a", linestyle="--", linewidth=1.2, alpha=0.7, label=f"Normal (${precio_normal:.2f})")
        if atl_global > 0:
            ax.axhline(y=atl_global, color="#00e676", linestyle=":", linewidth=1.5, alpha=0.85, label=f"Mín. Histórico (${atl_global:.2f})")

        todos_y = precios + ([precio_normal] if precio_normal > 0 else []) + ([atl_global] if atl_global > 0 else [])
        min_y = min(todos_y) * 0.85 if todos_y and min(todos_y) > 0 else 0
        max_y = max(todos_y) * 1.12 if todos_y else 10
        ax.set_ylim(min_y, max_y)
        ax.fill_between(fechas, precios, min_y, color=pal["accent_2"], alpha=0.15)

        ax.set_title(f"Evolución y Récord Histórico: {self.titulo_juego}", color=pal["text"], pad=12)
        ax.set_ylabel("Precio USD", color=pal["text"])
        ax.tick_params(axis='x', colors=pal["text"], rotation=30)
        ax.tick_params(axis='y', colors=pal["text"])
        ax.grid(True, linestyle='--', alpha=0.3, color=pal["border"])
        ax.legend(facecolor=pal["card_bg"], edgecolor=pal["border"], labelcolor=pal["text"], fontsize=9, loc="best")

        try:
            import mplcursors
            cursor = mplcursors.cursor(ax.lines[1], hover=True)

            @cursor.connect("add")
            def on_add(sel):
                idx_pt = min(max(0, int(round(sel.index))), len(fechas) - 1)
                fecha_hover = fechas[idx_pt].strftime('%d/%m/%Y')
                precio_hover = sel.target[1]
                sel.annotation.set_text(f"${precio_hover:.2f} USD\n{fecha_hover}")
                sel.annotation.get_bbox_patch().set(fc=pal["card_bg"], alpha=0.95, ec=pal["accent"], lw=1.5)
                sel.annotation.set_color(pal["text"])
                sel.annotation.set_fontname("Consolas")
        except ImportError:
            pass

        self.fig.tight_layout()
        canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=8)

    def _cerrar_grafico(self):
        if self.fig:
            plt.close(self.fig)
        self.destroy()


class DialogoDashboardVisual(ctk.CTkToplevel):
    """Dashboard Ejecutivo Visual con 4 gráficos interactivos en vivo (Ofertas + Biblioteca) (SRP)."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_app = parent
        pal = parent.palette
        self.title("📊 Dashboard de Estadísticas Visuales — SteamScope")
        self.geometry("1020x680")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=pal["win_bg"])
        self.fig = None

        x = parent.winfo_x() + (parent.winfo_width() // 2) - 510
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 340
        self.geometry(f"+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._construir_dashboard()

    def _construir_dashboard(self):
        pal = self.parent_app.palette
        deals = self.parent_app.deals_filtradas or self.parent_app.deals_data or []
        lib = self.parent_app.biblioteca_data or []
        carrito = list(self.parent_app.carrito.values())

        # KPI Top Cards
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", padx=18, pady=(14, 6))
        for i in range(4):
            kpi_row.grid_columnconfigure(i, weight=1)

        total_deals = len(deals)
        atl_deals = sum(1 for d in deals if d.get("es_atl"))
        ahorro_cart_usd = sum(max(0.0, d.get("precio_normal_usd", 0) - d.get("precio_oferta_usd", 0)) for d in carrito)
        total_lib = len(lib)
        horas_lib = sum(j.get("horas", 0.0) for j in lib)
        sin_jugar = sum(1 for j in lib if j.get("horas", 0.0) == 0)
        val_lib_usd = sum(j.get("price_usd", 0.0) for j in lib if j.get("price_usd", -1.0) > 0)

        cards_info = [
            ("🔥 Ofertas Encontradas", f"{total_deals} títulos", f"🏆 {atl_deals} en Mínimo Histórico", pal["accent"]),
            ("🛒 Ahorro en Changuito", f"${ahorro_cart_usd:.2f} USD", f"📦 {len(carrito)} juegos seleccionados", "#00e676"),
            ("🎮 Mi Biblioteca Steam", f"{total_lib} juegos", f"⏱️ {horas_lib:,.1f} hs totales ({sin_jugar} en 0 hs)", "#38bdf8"),
            ("💰 Valor Cuenta Valuado", f"${val_lib_usd:,.2f} USD" if val_lib_usd > 0 else "Sin valuar aún", "Tocá '💰 Valuar Cuenta' en Biblioteca" if val_lib_usd == 0 else f"Ratio: ${(val_lib_usd / horas_lib):.2f} USD/h" if horas_lib > 0 else "0 hs", "#ffab00"),
        ]

        for idx, (t_head, t_big, t_sub, col_b) in enumerate(cards_info):
            c = ctk.CTkFrame(kpi_row, fg_color=pal["card_bg"], corner_radius=10, border_width=1, border_color=col_b)
            c.grid(row=0, column=idx, padx=6, pady=4, sticky="nsew")
            ctk.CTkLabel(c, text=t_head, font=("Segoe UI", 11, "bold"), text_color=pal["subtext"]).pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(c, text=t_big, font=("Consolas", 18, "bold"), text_color=col_b).pack(anchor="w", padx=12, pady=2)
            ctk.CTkLabel(c, text=t_sub, font=("Segoe UI", 10), text_color=pal["text"]).pack(anchor="w", padx=12, pady=(0, 8))

        # Figura con 4 Subplots (2x2)
        self.fig, axes = plt.subplots(2, 2, figsize=(9.8, 5.1), facecolor=pal["win_bg"])
        ((ax1, ax2), (ax3, ax4)) = axes

        for ax in (ax1, ax2, ax3, ax4):
            ax.set_facecolor(pal["card_bg"])
            ax.tick_params(colors=pal["text"], labelsize=8.5)
            for spine in ax.spines.values():
                spine.set_color(pal["border"])

        # 1. Distribución de Descuentos (Ofertas)
        if deals:
            rangos = ["< 25%", "25-49%", "50-74%", "75-100%"]
            vals = [
                sum(1 for d in deals if d.get("descuento", 0) < 25),
                sum(1 for d in deals if 25 <= d.get("descuento", 0) < 50),
                sum(1 for d in deals if 50 <= d.get("descuento", 0) < 75),
                sum(1 for d in deals if d.get("descuento", 0) >= 75),
            ]
            bars = ax1.bar(rangos, vals, color=["#38bdf8", "#00f0ff", "#ffab00", "#00e676"], width=0.55)
            for b in bars:
                h = b.get_height()
                if h > 0:
                    ax1.text(b.get_x() + b.get_width() / 2, h + 0.3, str(int(h)), ha="center", va="bottom", color=pal["text"], fontsize=8, fontweight="bold")
        else:
            ax1.text(0.5, 0.5, "Escaneá ofertas para ver descuentos", ha="center", va="center", color=pal["subtext"], transform=ax1.transAxes)
        ax1.set_title("Distribución por Nivel de Descuento", color=pal["text"], fontsize=10.5, fontweight="bold")

        # 2. Top Géneros en Ofertas
        if deals:
            gen_counts = {}
            for d in deals:
                g = (d.get("genero") or "General").split(",")[0].strip()[:16]
                gen_counts[g] = gen_counts.get(g, 0) + 1
            top_g = sorted(gen_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_g:
                names = [x[0] for x in reversed(top_g)]
                counts = [x[1] for x in reversed(top_g)]
                ax2.barh(names, counts, color=pal["accent"], height=0.55)
        else:
            ax2.text(0.5, 0.5, "Sin ofertas activas en memoria", ha="center", va="center", color=pal["subtext"], transform=ax2.transAxes)
        ax2.set_title("Top Géneros en Catálogo Escaneado", color=pal["text"], fontsize=10.5, fontweight="bold")

        # 3. Estado del Backlog (Mi Biblioteca)
        if lib:
            jugados_fuerte = sum(1 for j in lib if j.get("horas", 0) >= 10)
            jugados_poco = sum(1 for j in lib if 0 < j.get("horas", 0) < 10)
            nunca_abiertos = sum(1 for j in lib if j.get("horas", 0) == 0)
            etiquetas = []
            partes = []
            colores = []
            for lbl, cnt, col in [
                (f"Viciados +10h ({jugados_fuerte})", jugados_fuerte, "#00e676"),
                (f"Probados <10h ({jugados_poco})", jugados_poco, "#38bdf8"),
                (f"Backlog 0h ({nunca_abiertos})", nunca_abiertos, "#ff5252"),
            ]:
                if cnt > 0:
                    etiquetas.append(lbl)
                    partes.append(cnt)
                    colores.append(col)
            if partes:
                wedges, texts, autotexts = ax3.pie(
                    partes, labels=etiquetas, autopct="%1.0f%%", startangle=140,
                    colors=colores, textprops={"color": pal["text"], "fontsize": 8.5},
                    wedgeprops={"width": 0.45, "edgecolor": pal["card_bg"]}
                )
                for at in autotexts:
                    at.set_color("black")
                    at.set_fontweight("bold")
        else:
            ax3.text(0.5, 0.5, "Cargá tu Biblioteca para ver tu Backlog", ha="center", va="center", color=pal["subtext"], transform=ax3.transAxes)
        ax3.set_title("Estado de Uso de Mi Biblioteca (Backlog)", color=pal["text"], fontsize=10.5, fontweight="bold")

        # 4. Top 5 Juegos Más Jugados
        if lib:
            top_lib = sorted(lib, key=lambda x: x.get("horas", 0), reverse=True)[:5]
            if any(x.get("horas", 0) > 0 for x in top_lib):
                l_names = [(x["titulo"][:18] + ".." if len(x["titulo"]) > 18 else x["titulo"]) for x in reversed(top_lib)]
                l_hrs = [x["horas"] for x in reversed(top_lib)]
                ax4.barh(l_names, l_hrs, color="#bd93f9", height=0.55)
                ax4.set_xlabel("Horas registradas", color=pal["subtext"], fontsize=8)
            else:
                ax4.text(0.5, 0.5, "Tus juegos registran 0 hs (perfil privado de horas)", ha="center", va="center", color=pal["subtext"], transform=ax4.transAxes)
        else:
            ax4.text(0.5, 0.5, "Sin datos de biblioteca", ha="center", va="center", color=pal["subtext"], transform=ax4.transAxes)
        ax4.set_title("Top 5 Juegos Más Jugados en tu Cuenta", color=pal["text"], fontsize=10.5, fontweight="bold")

        self.fig.tight_layout(pad=1.6)
        canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=16, pady=(4, 12))

    def _cerrar(self):
        if self.fig:
            plt.close(self.fig)
        self.destroy()

