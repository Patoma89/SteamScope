import csv
import re
import threading
from datetime import datetime
from io import BytesIO
from tkinter import filedialog
import pandas as pd
from PIL import Image, ImageDraw, ImageOps, ImageFont
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages

from core.config import APP_NAME, APP_VERSION
from core.api_client import HTTP_SESSION
from core.pricing import detectar_suscripcion, evaluar_termometro_compra
from ui.modals import mostrar_alerta_skin


def escribir_csv(ruta_destino, cabeceras, filas):
    """Escribe un archivo CSV con codificación utf-8-sig para máxima compatibilidad con Microsoft Excel."""
    with open(ruta_destino, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(cabeceras)
        for fila in filas:
            writer.writerow(fila)


class ExportService:
    """
    Servicio dedicado a la exportación de datos e integraciones externas (SRP & OCP):
    - Presupuesto del changuito en PNG.
    - Placa promocional 1080x1080 para redes sociales en PNG.
    - Resumen formateado para WhatsApp / Telegram.
    - Publicación mediante Webhook de Discord.
    - Reporte Ejecutivo en PDF (con gráficos Matplotlib en segundo plano).
    - Reporte Ejecutivo en Excel (.xlsx con Pandas).
    """
    def __init__(self, app_context):
        self.app = app_context

    def exportar_presupuesto_png(self):
        if not self.app.carrito:
            return
        self.app.sfx.play("click")
        dst = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("Imagen PNG", "*.png")],
            initialfile="SteamScope_Presupuesto.png"
        )
        if not dst:
            return
        try:
            items = list(self.app.carrito.values())
            W, H = 900, 220 + len(items) * 55
            img = Image.new("RGB", (W, H), color=(17, 20, 28))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([(20, 20), (W - 20, H - 20)], radius=20, outline=(0, 240, 255), width=3)
            try:
                f_title = ImageFont.truetype("arialbd.ttf", 26)
                f_item = ImageFont.truetype("consola.ttf", 18)
                f_tot = ImageFont.truetype("consolab.ttf", 20)
            except Exception:
                f_title = f_item = f_tot = ImageFont.load_default()
            draw.text((45, 45), f"🛒 PRESUPUESTO DE COMPRAS - {APP_NAME}", fill=(0, 240, 255), font=f_title)
            y = 105
            dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
            imp = self.app.config.datos.get("impuestos_pct", 60)
            mult = 1 + (imp / 100.0)
            tot_usd = 0.0
            for itm in items:
                p_usd = itm.get("precio_oferta_usd", 0.0)
                tot_usd += p_usd
                p_ars = round(p_usd * dolar * mult)
                draw.text((45, y), f"• {itm.get('titulo', 'Juego')[:38]}", fill=(255, 255, 255), font=f_item)
                draw.text((W - 340, y), f"${p_usd:.2f} USD  (${p_ars:,.0f} ARS)", fill=(74, 246, 38), font=f_item)
                y += 45
            draw.line([(45, y + 10), (W - 45, y + 10)], fill=(40, 44, 52), width=2)
            tot_ars_final = round(tot_usd * dolar * mult)
            tot_wallet_final = round(tot_usd * dolar)
            draw.text(
                (45, y + 30),
                f"TOTAL: ${tot_usd:.2f} USD  ➔  💳 Tarjeta: ${tot_ars_final:,.0f} ARS  |  👛 Wallet: ${tot_wallet_final:,.0f} ARS",
                fill=(0, 230, 118),
                font=f_tot
            )
            img.save(dst, "PNG")
            self.app._show_toast("✅ Presupuesto exportado como imagen.", "#00e676")
        except Exception as e:
            mostrar_alerta_skin(self.app, "Error", f"No se pudo exportar:\n{e}", tipo="error")

    def copiar_resumen_whatsapp(self):
        """Exportador directo a texto optimizado para WhatsApp / Telegram."""
        if not self.app.deals_filtradas:
            return
        self.app.sfx.play("click")
        dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
        imp = self.app.config.datos.get("impuestos_pct", 60)
        mult = 1 + (imp / 100.0)

        lineas = ["🔥 *OFERTAS DESTACADAS EN STEAM* (por SteamScope)", ""]
        top_items = self.app.deals_filtradas[:15]
        for it in top_items:
            p_usd = it['precio_oferta_usd']
            p_ars = round(p_usd * dolar * mult)
            lineas.append(f"• *{it['titulo']}*: ${p_usd:.2f} USD (~${p_ars:,.0f} ARS) [-{it['descuento']}%]")

        lineas.append("")
        lineas.append(f"_Cotización base: ${dolar} ARS (+{imp}% imp). Canal: youtube.com/@Patoma89_")

        texto_final = "\n".join(lineas)
        self.app.clipboard_clear()
        self.app.clipboard_append(texto_final)
        self.app._show_toast("📋 Texto copiado para WhatsApp/Telegram.", "#00e676")

    def enviar_oferta_discord(self, item):
        webhook_url = self.app.config.datos.get("discord_webhook", "").strip()
        if not webhook_url:
            mostrar_alerta_skin(self.app, "Atención", "Configurá tu Discord Webhook URL en Ajustes primero.", tipo="warning")
            self.app._abrir_configuracion()
            return
        self.app.sfx.play("click")
        self.app._show_toast("📢 Enviando oferta a Discord...", self.app.palette["accent"])

        def _hilo_discord():
            try:
                dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
                imp = self.app.config.datos.get("impuestos_pct", 60)
                p_usd = item.get("precio_oferta_usd", 0.0)
                p_ars = round(p_usd * dolar * (1 + imp / 100.0))
                desc = item.get("descuento", 0)
                embed = {
                    "title": f"🔥 Oferta en Steam: {item.get('titulo', 'Juego')}",
                    "url": item.get("link", "https://store.steampowered.com"),
                    "color": 65280,
                    "fields": [
                        {"name": "Descuento", "value": f"-{desc}% OFF", "inline": True},
                        {"name": "Precio USD", "value": f"${p_usd:.2f} USD", "inline": True},
                        {"name": "Precio Final ARS", "value": f"${p_ars:,.0f} ARS", "inline": True}
                    ],
                    "footer": {"text": f"Enviado desde {APP_NAME} by Patoma89"}
                }
                r = HTTP_SESSION.post(webhook_url, json={"embeds": [embed]}, timeout=6)
                if r.status_code in (200, 204):
                    self.app.after(0, lambda: self.app._show_toast("✅ ¡Oferta publicada en Discord!", "#00e676"))
                else:
                    self.app.after(0, lambda: mostrar_alerta_skin(self.app, "Error Discord", f"Código HTTP {r.status_code}", tipo="error"))
            except Exception as e:
                self.app.after(0, lambda err=str(e): mostrar_alerta_skin(self.app, "Error", f"No se pudo enviar:\n{err}", tipo="error"))

        threading.Thread(target=_hilo_discord, daemon=True).start()

    def exportar_placa_redes(self, item):
        self.app.sfx.play("click")
        self.app._show_toast("📸 Generando placa 1080x1080...", self.app.palette["accent"])
        threading.Thread(target=self._hilo_generar_placa, args=(item,), daemon=True).start()

    def _hilo_generar_placa(self, item):
        try:
            W, H = 1080, 1080
            canvas = Image.new("RGB", (W, H), color=(11, 13, 18))
            draw = ImageDraw.Draw(canvas)
            for y in range(H):
                draw.line([(0, y), (W, y)], fill=(int(11 + (y / H) * 14), int(13 + (y / H) * 18), int(20 + (y / H) * 32)))
            draw.rounded_rectangle([(30, 30), (W - 30, H - 30)], radius=32, outline=(0, 240, 255), width=5)
            draw.rounded_rectangle([(46, 46), (W - 46, H - 46)], radius=26, fill=(17, 20, 28))
            try:
                f_header = ImageFont.truetype("consolab.ttf", 34)
                f_title = ImageFont.truetype("arialbd.ttf", 48)
                f_price = ImageFont.truetype("consolab.ttf", 64)
                f_sub = ImageFont.truetype("consola.ttf", 30)
                f_badge = ImageFont.truetype("arialbd.ttf", 44)
            except Exception:
                f_header = f_title = f_price = f_sub = f_badge = ImageFont.load_default()
            draw.text((85, 78), f"⚡ STEAMSCOPE v{APP_VERSION} // OFERTA", fill=(0, 240, 255), font=f_header)
            appid = item.get("appid")
            poster_img = None
            for u in [
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg",
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
                item.get("thumb_url")
            ]:
                if not u:
                    continue
                try:
                    r = HTTP_SESSION.get(u, timeout=5)
                    if r.status_code == 200 and len(r.content) > 800:
                        poster_img = Image.open(BytesIO(r.content)).convert("RGB")
                        break
                except Exception:
                    continue
            if poster_img:
                canvas.paste(ImageOps.fit(poster_img, (380, 540), Image.Resampling.LANCZOS), (85, 160))
                draw.rectangle([(85, 160), (465, 700)], outline=(56, 189, 248), width=3)
            x_txt = 505
            t_limpio = item.get("titulo", "Juego")[:22]
            draw.text((x_txt, 175), t_limpio, fill=(255, 255, 255), font=f_title)
            desc = item.get("descuento", 0)
            p_usd = item.get("precio_oferta_usd", 0.0)
            if p_usd == 0 and desc < 100:
                draw.text((x_txt, 300), "⏳ PRÓXIMAMENTE", fill=(200, 200, 200), font=f_title)
            else:
                draw.rounded_rectangle([(x_txt, 255), (x_txt + 260, 340)], radius=14, fill=(0, 230, 118))
                draw.text((x_txt + 30, 273), f"-{desc}% OFF", fill=(0, 0, 0), font=f_badge)
                if item.get("es_atl"):
                    draw.rounded_rectangle([(x_txt + 280, 255), (x_txt + 510, 340)], radius=14, fill=(255, 0, 60))
                    draw.text((x_txt + 300, 280), "MÍN. HISTÓRICO", fill=(255, 255, 255), font=f_sub)
                dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
                imp = self.app.config.datos.get("impuestos_pct", 60)
                draw.text((x_txt, 380), f"Antes: ${item.get('precio_normal_usd', 0):.2f} USD", fill=(148, 163, 184), font=f_sub)
                draw.text((x_txt, 430), f"${p_usd:.2f} USD", fill=(0, 240, 255), font=f_price)
                draw.text((x_txt, 520), f"🇦🇷 ${round(p_usd * dolar * (1 + imp / 100)):,.0f} ARS", fill=(74, 246, 38), font=f_price)
            veredicto, _, _ = evaluar_termometro_compra(desc, item.get("es_atl", False), p_usd)
            draw.rounded_rectangle([(85, 745), (W - 85, 865)], radius=16, fill=(24, 28, 38), outline=(56, 189, 248), width=2)
            draw.text((115, 785), f"Termómetro: {veredicto}", fill=(255, 255, 255), font=f_header)
            draw.text((85, 935), "👾 Creado con SteamScope by Patoma89", fill=(161, 161, 170), font=f_sub)

            def _guardar_dialogo():
                dst = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("Imagen PNG", "*.png")],
                    initialfile="SteamScope_Placa.png"
                )
                if dst:
                    canvas.save(dst, "PNG")
                    self.app._show_toast("✅ Placa guardada.", "#00e676")

            self.app.after(0, _guardar_dialogo)
        except Exception as e:
            self.app.after(0, lambda err=str(e): mostrar_alerta_skin(self.app, "Error", f"No se pudo crear la placa:\n{err}", tipo="error"))

    def exportar_pdf(self):
        if not self.app.deals_filtradas:
            return
        self.app.sfx.play("click")
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("Documento PDF", "*.pdf")],
            initialfile=f"{APP_NAME}_Reporte_Ejecutivo_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )
        if not path:
            return
        self.app._show_toast("📄 Generando Reporte PDF Ejecutivo...", self.app.palette["accent"])
        threading.Thread(target=self._hilo_generar_pdf, args=(path,), daemon=True).start()

    def _hilo_generar_pdf(self, path):
        try:
            mult = 1 + (self.app.config.datos.get("impuestos_pct", 60) / 100.0)
            dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
            items = list(self.app.deals_filtradas)

            total_juegos = len(items)
            total_usd = sum(d["precio_oferta_usd"] for d in items)
            total_ars = round(total_usd * dolar * mult)
            atl_count = sum(1 for d in items if d.get("es_atl"))

            with PdfPages(path) as pdf:
                fig = Figure(figsize=(8.27, 11.69), facecolor="#111318")
                fig.suptitle(
                    f"⚡ {APP_NAME} v{APP_VERSION} — Reporte Ejecutivo de Ofertas",
                    color="#00f0ff", fontsize=16, fontweight="bold", y=0.96
                )

                ax_info = fig.add_axes([0.08, 0.78, 0.84, 0.14])
                ax_info.set_facecolor("#181b22")
                ax_info.set_xticks([])
                ax_info.set_yticks([])
                for spine in ax_info.spines.values():
                    spine.set_color("#00f0ff")
                resumen_txt = (
                    f"Fecha de emisión: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   Autor: Patoma89\n"
                    f"Cotización aplicada: Dólar ${dolar} ARS + {self.app.config.datos.get('impuestos_pct', 60)}% imp.\n\n"
                    f"• Total de Juegos Analizados: {total_juegos} títulos\n"
                    f"• Costo Acumulado Total: ${total_usd:.2f} USD  (${total_ars:,.0f} ARS final)\n"
                    f"• Juegos en Mínimo Histórico (ATL): {atl_count} ({(atl_count / total_juegos * 100):.1f}%)"
                )
                ax_info.text(0.04, 0.5, resumen_txt, color="#f8fafc", fontsize=10.5, family="monospace", va="center")

                ax1 = fig.add_axes([0.12, 0.45, 0.78, 0.25], facecolor="#181b22")
                rangos = ["< 25%", "25% - 49%", "50% - 74%", "75% - 100%"]
                conteos_desc = [
                    sum(1 for d in items if d["descuento"] < 25),
                    sum(1 for d in items if 25 <= d["descuento"] < 50),
                    sum(1 for d in items if 50 <= d["descuento"] < 75),
                    sum(1 for d in items if d["descuento"] >= 75)
                ]
                ax1.bar(rangos, conteos_desc, color=["#38bdf8", "#00f0ff", "#ffab00", "#00e676"], width=0.55)
                ax1.set_title("Distribución por Nivel de Descuento", color="white", fontsize=12, fontweight="bold", pad=10)
                ax1.tick_params(colors="white")
                for spine in ax1.spines.values():
                    spine.set_color("#282c34")

                ax2 = fig.add_axes([0.18, 0.10, 0.72, 0.26], facecolor="#181b22")
                gen_counts = {}
                for d in items:
                    g = (d.get("genero") or "General").split(",")[0].strip()[:18]
                    gen_counts[g] = gen_counts.get(g, 0) + 1
                top_gen = sorted(gen_counts.items(), key=lambda x: x[1], reverse=True)[:6]
                if top_gen:
                    g_names = [x[0] for x in reversed(top_gen)]
                    g_vals = [x[1] for x in reversed(top_gen)]
                    ax2.barh(g_names, g_vals, color="#bd93f9", height=0.55)
                ax2.set_title("Top Géneros en este Reporte", color="white", fontsize=12, fontweight="bold", pad=10)
                ax2.tick_params(colors="white")
                for spine in ax2.spines.values():
                    spine.set_color("#282c34")

                pdf.savefig(fig, facecolor=fig.get_facecolor())

                chunk_size = 28
                for p_idx in range(0, len(items), chunk_size):
                    sub_items = items[p_idx:p_idx + chunk_size]
                    fig_t = Figure(figsize=(8.27, 11.69), facecolor="#111318")
                    num_pag = (p_idx // chunk_size) + 2
                    fig_t.suptitle(
                        f"📋 Listado Detallado de Ofertas — Página {num_pag}",
                        color="#00f0ff", fontsize=13, fontweight="bold", y=0.96
                    )
                    ax_t = fig_t.add_axes([0.04, 0.05, 0.92, 0.88])
                    ax_t.axis("off")

                    table_data = [["Título", "Desc.", "USD", "Final ARS", "Récord", "Termómetro"]]
                    for it in sub_items:
                        p_u = it["precio_oferta_usd"]
                        p_a = round(p_u * dolar * mult)
                        vered = evaluar_termometro_compra(it["descuento"], it.get("es_atl", False), p_u)[0]
                        vered_clean = re.sub(r'[^\x00-\x7F¡!¿?áéíóúÁÉÍÓÚñÑ()$%-]', '', vered).strip()[:18]
                        table_data.append([
                            it["titulo"][:32], f"-{it['descuento']}%", f"${p_u:.2f}", f"${p_a:,.0f}",
                            "SÍ" if it.get("es_atl") else "-", vered_clean
                        ])

                    tabla = ax_t.table(
                        cellText=table_data, loc="upper center", cellLoc="center",
                        colWidths=[0.36, 0.10, 0.11, 0.15, 0.08, 0.20]
                    )
                    tabla.auto_set_font_size(False)
                    tabla.set_fontsize(8.5)
                    tabla.scale(1, 1.38)

                    for (row, col), cell in tabla.get_celld().items():
                        cell.set_edgecolor("#282c34")
                        if row == 0:
                            cell.set_facecolor("#1f538d")
                            cell.get_text().set_color("white")
                            cell.get_text().set_weight("bold")
                        else:
                            cell.set_facecolor("#181b20" if row % 2 == 0 else "#121418")
                            cell.get_text().set_color("#f8fafc")

                    pdf.savefig(fig_t, facecolor=fig_t.get_facecolor())

            self.app.after(0, lambda: self.app._show_toast("✅ Reporte PDF Ejecutivo exportado con éxito.", "#00e676"))
        except Exception as e:
            self.app.after(0, lambda err=str(e): mostrar_alerta_skin(self.app, "Error al crear PDF", f"No se pudo exportar el PDF:\n{err}", tipo="error"))

    def exportar_excel(self):
        if not self.app.deals_filtradas:
            return
        self.app.sfx.play("click")
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"{APP_NAME}_Deals_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        )
        if path:
            try:
                mult = 1 + (self.app.config.datos.get("impuestos_pct", 60) / 100)
                dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
                df_deals = pd.DataFrame([
                    {
                        "Título": d["titulo"],
                        "Modalidad": d["modalidad"],
                        "Género": d["genero"],
                        "Descuento": f"{d['descuento']}%",
                        "Precio USD": d["precio_oferta_usd"],
                        "Precio Final ARS": round(d["precio_oferta_usd"] * dolar * mult, 2),
                        "Rating Steam": f"{d['rating']}%",
                        "Mínimo Histórico": "SÍ" if d.get("es_atl") else "NO",
                        "Suscripción": (detectar_suscripcion(d["titulo"]) or ("No",))[0],
                        "Termómetro": evaluar_termometro_compra(d["descuento"], d.get("es_atl", False), d["precio_oferta_usd"])[0],
                        "Enlace": d["link"]
                    }
                    for d in self.app.deals_filtradas
                ])
                total_juegos = len(df_deals)
                costo_total = df_deals["Precio USD"].sum()
                costo_total_ars = df_deals["Precio Final ARS"].sum()
                atl_count = df_deals[df_deals["Mínimo Histórico"] == "SÍ"].shape[0]
                df_res = pd.DataFrame({
                    "Métrica": ["Total Juegos", "Costo USD", "Costo ARS", "Mínimos Históricos"],
                    "Valor": [total_juegos, f"${costo_total:.2f}", f"${costo_total_ars:,.2f}", atl_count]
                })
                df_gen = df_deals["Género"].value_counts().reset_index()
                df_gen.columns = ["Género", "Cantidad"]
                with pd.ExcelWriter(path, engine='openpyxl') as writer:
                    df_deals.to_excel(writer, sheet_name='Ofertas', index=False)
                    df_res.to_excel(writer, sheet_name='Dashboard', index=False)
                    df_gen.to_excel(writer, sheet_name='Dashboard', startrow=8, index=False)
                self.app._show_toast("✅ Excel exportado.", "#00e676")
            except Exception as e:
                mostrar_alerta_skin(self.app, "Error", f"¿Instalaste openpyxl?\n{e}", tipo="error")

    def exportar_biblioteca_csv(self):
        """Exporta la colección de juegos propia a una planilla CSV compatible con Excel."""
        if not self.app.biblioteca_data:
            mostrar_alerta_skin(self.app, "Biblioteca Vacía", "Primero sincronizá tu biblioteca de Steam para poder exportarla.", tipo="info")
            return
        self.app.sfx.play("click")
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivo CSV (Excel)", "*.csv")],
            initialfile=f"{APP_NAME}_Biblioteca_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        )
        if not path:
            return
        try:
            dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
            imp = self.app.config.datos.get("impuestos_pct", 60)
            mult = 1 + (imp / 100.0)
            notas = self.app.db.get_all_game_notes()

            cabeceras = ["AppID", "Título", "Horas Jugadas", "Minutos", "Precio Base USD", "Precio Base ARS (Tarjeta)", "Estado Backlog", "Nota Personal", "Enlace Tienda"]
            filas = []
            for j in self.app.biblioteca_data:
                aid = str(j.get("appid", ""))
                hrs = float(j.get("horas", 0.0))
                mins = int(j.get("minutos", 0))
                p_usd = float(j.get("price_usd", -1.0))
                p_usd_str = f"${p_usd:.2f}" if p_usd >= 0 else "N/D"
                p_ars_str = f"${round(p_usd * dolar * mult):,}" if p_usd >= 0 else "N/D"

                if hrs < 0.1:
                    estado = "💤 Sin estrenar (0 hs)"
                elif hrs < 2.0:
                    estado = "⏳ Apenas probado (< 2 hs)"
                elif hrs >= 20.0:
                    estado = "🏆 Viciado (+20 hs)"
                else:
                    estado = "🎮 Jugado"

                nota = notas.get(aid, "")
                link = f"https://store.steampowered.com/app/{aid}"
                filas.append([aid, j.get("titulo", "Desconocido"), f"{hrs:.1f}", mins, p_usd_str, p_ars_str, estado, nota, link])

            escribir_csv(path, cabeceras, filas)
            self.app._show_toast("✅ Biblioteca exportada a CSV.", "#00e676")
        except Exception as e:
            mostrar_alerta_skin(self.app, "Error al exportar", f"No se pudo guardar el archivo CSV:\n{e}", tipo="error")

    def exportar_watchlist_csv(self):
        """Exporta la lista de seguimiento a una planilla CSV compatible con Excel."""
        items = self.app.db.get_all_watchlist()
        if not items:
            mostrar_alerta_skin(self.app, "Watchlist Vacía", "No tenés juegos guardados en tu Watchlist para exportar.", tipo="info")
            return
        self.app.sfx.play("click")
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivo CSV (Excel)", "*.csv")],
            initialfile=f"{APP_NAME}_Watchlist_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        )
        if not path:
            return
        try:
            dolar = self.app.config.datos.get("dolar_referencia", 1000.0)
            imp = self.app.config.datos.get("impuestos_pct", 60)
            mult = 1 + (imp / 100.0)
            notas = self.app.db.get_all_game_notes()

            cabeceras = ["AppID", "Título", "Precio Guardado USD", "Precio Guardado ARS", "Precio Objetivo USD", "Etiqueta Personal", "Nota Personal", "Fecha Registro", "Enlace"]
            filas = []
            for r in items:
                aid = str(r[0])
                tit = str(r[1])
                p_guard = float(r[2] or 0.0)
                fecha = str(r[3] or "")
                link = str(r[4] or f"https://store.steampowered.com/app/{aid}")
                tag = str(r[5] or "")
                target_p = float(r[6] or 0.0)
                nota = notas.get(aid, "")
                p_ars = round(p_guard * dolar * mult)

                target_str = f"${target_p:.2f}" if target_p > 0 else "Sin límite"
                filas.append([aid, tit, f"${p_guard:.2f}", f"${p_ars:,}", target_str, tag, nota, fecha, link])

            escribir_csv(path, cabeceras, filas)
            self.app._show_toast("✅ Watchlist exportada a CSV.", "#00e676")
        except Exception as e:
            mostrar_alerta_skin(self.app, "Error al exportar", f"No se pudo guardar el archivo CSV:\n{e}", tipo="error")
