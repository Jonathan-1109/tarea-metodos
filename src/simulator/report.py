"""
Exportación del reporte de simulación a reporte_simulacion.txt
y anexado del análisis de la API.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .simulation import NetworkSimulation

REPORT_FILENAME = "reporte_simulacion.txt"

ANALYSIS_PROMPT = (
    "Analiza los siguientes resultados de desempeño de un simulador de red "
    "basado en teoría de colas e inventario. Evalúa la tasa de pérdida de "
    "paquetes, tiempos de espera y costos, e indica conclusiones detalladas "
    "y 3 recomendaciones de optimización."
)


def build_report_body(sim: "NetworkSimulation") -> str:
    """Construye el cuerpo del reporte con el formato exigido por la consignación."""
    cfg = sim.config
    st = sim.stats
    m = st.metrics
    m.advance(sim.now)

    lines = [
        "====================================================",
        "           REPORTE DE SIMULACIÓN DE RED",
        "====================================================",
        f"Tiempo Total de Simulación: {sim.now:.2f} s",
        f"Tasa de Llegada (lambda): {cfg.lam:.1f} paquetes/s",
        f"Tasa de Servicio (mu): {cfg.mu:.1f} paquetes/s",
        f"Capacidad de Buffer (S): {cfg.S} paquetes",
        f"Umbral Reabastecimiento (s): {cfg.s} paquetes",
        "METRICAS OBTENIDAS:",
        f"- Paquetes Procesados: {m.departures}",
        f"- Paquetes Perdidos (Overflow): {m.lost}",
        f"- Tasa de Pérdida: {m.loss_rate:.2f}%",
        f"- Tiempo Medio en Cola (Wq): {m.Wq:.2f} s",
        f"- Promedio Paquetes en Sistema (L): {m.L:.2f}",
        f"- Costo Total de Almacenamiento: ${st.holding_cost:.2f}",
        f"- Costo Total de Penalización (Ruptura): ${st.shortage_cost:.2f}",
        f"- Costo Global del Sistema: ${st.total_cost:.2f}",
        "====================================================",
        "",
        "METRICAS ADICIONALES:",
        f"- Lq (promedio en cola): {m.Lq:.2f}",
        f"- W (tiempo medio en sistema): {m.W:.2f} s",
        f"- Ejecuciones Algoritmo Húngaro: {st.assignment_runs}",
        f"- Último costo de asignación: {st.last_assignment_cost:.4f}",
        f"- Señales de control de flujo: {st.flow_signals}",
        f"- Tabla de ruteo actual: {st.routing_table}",
        "====================================================",
    ]
    return "\n".join(lines) + "\n"


def save_report(sim: "NetworkSimulation", path: str | Path | None = None) -> Path:
    """Guarda el reporte en disco y retorna la ruta."""
    out = Path(path) if path else Path(REPORT_FILENAME)
    out.write_text(build_report_body(sim), encoding="utf-8")
    return out


def append_analysis(analysis: str, path: str | Path | None = None) -> Path:
    """Anexa la respuesta de la API al final del reporte."""
    out = Path(path) if path else Path(REPORT_FILENAME)
    block = (
        "\n"
        "====================================================\n"
        "     ANÁLISIS AUTOMATIZADO (GEMINI API)\n"
        "====================================================\n"
        f"{analysis.strip()}\n"
        "====================================================\n"
    )
    with out.open("a", encoding="utf-8") as fh:
        fh.write(block)
    return out
