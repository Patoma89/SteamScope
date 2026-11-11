---
name: python-gui-customtkinter
description: >-
  Use this skill whenever developing, modifying, styling, or debugging CustomTkinter or Tkinter desktop graphical user interfaces in Python. Covers async non-blocking UI patterns, dynamic multi-skin theming, batch rendering for lag-free scrolling, skin-aware modal dialogs, and embedded data visualizations.
---

# 🎨 Python GUI Pro: CustomTkinter & Modern Desktop Architecture

Esta skill establece las directrices de nivel senior para desarrollar, optimizar y refactorizar aplicaciones de escritorio modernas en Python utilizando **CustomTkinter** y **Tkinter**.

---

## ⚡ Regla de Oro: Hilo Principal (Main Thread) 100% Fluido

En Tkinter/CustomTkinter, el bucle `mainloop()` corre en un único hilo. **Cualquier llamada de red (`requests`), base de datos pesada o sleep en el hilo principal congela la ventana por completo.**

### Patrón Asincrónico Canónico (Thread + `root.after`)
```python
import threading

def iniciar_accion_pesada(self):
    self.boton.configure(state="disabled")
    self.lbl_estado.configure(text="⏳ Procesando...", text_color="orange")
    threading.Thread(target=self._hilo_pesado, daemon=True).start()

def _hilo_pesado(self):
    try:
        # 1. Operación bloqueante de red / I/O
        resultado = self.api_client.obtener_datos()
        
        # 2. Devolver SIEMPRE el control de la UI al hilo principal
        self.after(0, lambda: self._finalizar_exito(resultado))
    except Exception as e:
        self.after(0, lambda err=str(e): self._finalizar_error(err))

def _finalizar_exito(self, datos):
    if not self.winfo_exists():
        return
    self.boton.configure(state="normal")
    self.lbl_estado.configure(text="✅ Listo", text_color="#00e676")
    self._renderizar_datos(datos)

def _finalizar_error(self, err_msg):
    if not self.winfo_exists():
        return
    self.boton.configure(state="normal")
    self.lbl_estado.configure(text=f"❌ Error: {err_msg}", text_color="#ff5252")
```

---

## 🏎️ Optimización de Rendimiento: Renderizado por Lotes (Batch Rendering)

Cuando un `CTkScrollableFrame` necesita mostrar cientos de elementos, instanciar todos los widgets juntos traba la UI durante segundos.

### Patrón de Carga Escalonada
```python
def renderizar_lista_optimizada(self, items):
    self._token_render += 1
    token_actual = self._token_render
    
    # Limpiar widgets previos
    for w in self.scroll_frame.winfo_children():
        w.destroy()
        
    def _dibujar_lote(inicio=0, tamano_lote=8):
        if token_actual != self._token_render or not self.winfo_exists():
            return
        fin = min(inicio + tamano_lote, len(items))
        for i in range(inicio, fin):
            self._crear_tarjeta_item(self.scroll_frame, items[i])
        
        # Si quedan items, ceder el hilo principal y dibujar el siguiente lote en 12ms
        if fin < len(items):
            self.after(12, lambda: _dibujar_lote(fin, tamano_lote))

    _dibujar_lote(0)
```

---

## 🎭 Motor de Skins Dinámicas y Paletas

Nunca utilizar colores hexadecimales fijos (`#ffffff`, `#1f6feb`) directamente en tarjetas o botones generales. Todos los componentes deben alimentarse de la paleta activa:

### Claves Esenciales de Paleta
```python
SKIN_PALETTE = {
    "mode": "Dark",         # "Dark" o "Light"
    "win_bg": "#191a21",     # Fondo de la ventana raíz
    "panel_bg": "#21222c",   # Fondo de barras de navegación y pestañas
    "card_bg": "#282a36",    # Fondo de tarjetas y marcos contenedores
    "card_hover": "#343746", # Color al pasar el cursor (hover)
    "border": "#6272a4",     # Color de bordes y separadores
    "accent": "#ff5555",     # Color primario de acción/destaque
    "accent_2": "#bd93f9",   # Color secundario
    "text": "#f8f8f2",       # Texto principal
    "subtext": "#6272a4",    # Texto secundario o descriptivo
    "deal_badge": "#ff5555", # Badges de descuento o estado
    "deal_text": "#ffffff",  # Texto sobre el badge
    "price_bg": "#1e1f29"    # Fondo de etiquetas de precio
}
```

### Contraste Inteligente para Botones de Acento
Para evitar texto blanco ilegible sobre acentos claros (como cian `#00f0ff` o verde lima `#39ff14`):
```python
def texto_contraste_acento(pal):
    acc = pal.get("accent", "").lower()
    if acc in ("#00f0ff", "#39ff14", "#fcee0a", "#1a9fff", "#ff7518", "#00e676"):
        return "black"
    return "white"
```

---

## 🪟 Modales Custom 100% Skin-Aware (Cero `messagebox` nativos)

Los diálogos de Windows (`tkinter.messagebox` y `tkinter.simpledialog`) generan ventanas grises clásicas que rompen la inmersión del usuario.

### Estructura de Modal Personalizado
1. Derivar siempre de `ctk.CTkToplevel(parent)`.
2. Establecer `self.transient(parent)`, `self.grab_set()` y centrar sobre el padre:
   ```python
   x = parent.winfo_x() + (parent.winfo_width() // 2) - (ancho // 2)
   y = parent.winfo_y() + (parent.winfo_height() // 2) - (alto // 2)
   self.geometry(f"+{x}+{y}")
   ```
3. Utilizar un marco interno `CTkFrame` con `corner_radius=12`, `border_width=1` y `border_color=pal["border"]`.
4. Asignar icono de la aplicación con `self.iconbitmap(ico_path)`.

---

## 📊 Embeber Gráficos de Matplotlib sin Fugas de Memoria

```python
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class DialogoGrafico(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.fig, self.ax = plt.subplots(facecolor=parent.palette["win_bg"])
        self.ax.set_facecolor(parent.palette["card_bg"])
        
        # Dibujar datos...
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _al_cerrar(self):
        # OBLIGATORIO: cerrar figura para liberar memoria RAM
        if self.fig:
            plt.close(self.fig)
        self.destroy()
```

---

## ✅ Checklist de Verificación de UI
- [ ] ¿Toda tarea de red corre en un thread con `daemon=True`?
- [ ] ¿Todas las actualizaciones de UI regresan con `self.after(0, ...)`?
- [ ] ¿Se verificó `if self.winfo_exists():` antes de manipular widgets en callbacks?
- [ ] ¿Se eliminaron llamadas a `messagebox` nativos en favor de `mostrar_alerta_skin()`?
- [ ] ¿Los botones sobre fondos `accent` utilizan `texto_contraste_acento()`?
