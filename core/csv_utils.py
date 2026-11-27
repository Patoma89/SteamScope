"""Utilidades puras de exportación CSV sin dependencias de interfaz gráfica."""
import csv


def escribir_csv(ruta_destino, cabeceras, filas):
    """Escribe un archivo CSV con codificación utf-8-sig para máxima compatibilidad con Microsoft Excel."""
    with open(ruta_destino, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(cabeceras)
        for fila in filas:
            writer.writerow(fila)
