"""
Módulo de Notificaciones Enriquecidas de Windows 10/11 para SteamScope 2.0 (SRP / Core Puro).
Genera alertas Toast nativas interactivas con imagen en alta definición, desglose en ARS
y botones directos de acción (protocolo web para evitar impuestos).
"""

import os
import tempfile
import threading
import subprocess
from core.api_client import HTTP_SESSION
from core.pricing import notificar_windows


def notificar_oferta_enriquecida(
    titulo: str,
    precio_usd: float,
    descuento: int,
    precio_ars: float = 0,
    banner_url: str = None,
    appid: str = None,
    es_gratis: bool = False
):
    """
    Despacha una notificación enriquecida en segundo plano con imagen y botón interactivo.
    """
    threading.Thread(
        target=_hilo_notificar_toast,
        args=(titulo, precio_usd, descuento, precio_ars, banner_url, appid, es_gratis),
        daemon=True
    ).start()


def _hilo_notificar_toast(titulo, precio_usd, descuento, precio_ars, banner_url, appid, es_gratis):
    # 1. Descargar imagen temporal si existe
    img_temp_path = None
    if banner_url:
        try:
            r = HTTP_SESSION.get(banner_url, timeout=5)
            if r.status_code == 200 and len(r.content) > 1000:
                tmp_dir = tempfile.gettempdir()
                img_temp_path = os.path.join(tmp_dir, f"steamscope_toast_{appid or 'promo'}.jpg")
                with open(img_temp_path, "wb") as f:
                    f.write(r.content)
        except Exception:
            img_temp_path = None

    # 2. Formatear textos
    tag_tipo = "🎁 ¡JUEGO 100% GRATIS!" if es_gratis else f"⭐ ¡MÍNIMO HISTÓRICO (-{descuento}%)!"
    if es_gratis:
        cuerpo = f"¡{titulo} está disponible GRATIS por tiempo limitado!\nReclamalo antes de que finalice la promoción."
    else:
        cuerpo = f"{titulo} alcanzó su precio récord de ${precio_usd:.2f} USD (~${precio_ars:,.0f} ARS con tarjeta)."

    web_url = f"https://store.steampowered.com/app/{appid}" if appid else "https://store.steampowered.com"

    # 3. Intentar notificación nativa interactiva de Windows Toast (PowerShell con XML Toast)
    try:
        xml_img = f'<image placement="hero" src="{img_temp_path}"/>' if (img_temp_path and os.path.exists(img_temp_path)) else ""
        
        # Script PowerShell codificado para ejecución limpia en Windows 10 y 11
        ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$template = @"
<toast launch="{web_url}">
    <visual>
        <binding template="ToastGeneric">
            <text>{tag_tipo}</text>
            <text>{cuerpo}</text>
            {xml_img}
        </binding>
    </visual>
    <actions>
        <action content="🌐 Abrir en Steam Web (-21%)" arguments="{web_url}" activationType="protocol"/>
    </actions>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("SteamScope.App").Show($toast)
"""
        flags = 0x08000000  # CREATE_NO_WINDOW
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            creationflags=flags,
            timeout=4,
            capture_output=True
        )
    except Exception:
        # Fallback estándar seguro
        notificar_windows(tag_tipo, cuerpo)
