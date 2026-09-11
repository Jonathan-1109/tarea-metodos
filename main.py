#!/usr/bin/env python3
"""
Simulador Dinámico de Redes de Computadoras
==========================================

Punto de entrada principal. Lanza la interfaz Pygame que integra:

  A) Teoría de colas (Poisson λ / Exponencial μ → L, Lq, W, Wq)
  B) Modelos de inventario (buffer S, política s-Q, costos holding/shortage)
  C) Asignación óptima (Algoritmo Húngaro / scipy.optimize.linear_sum_assignment)
  D) Exportación a reporte_simulacion.txt + análisis Gemini API

Uso:
    python main.py              # GUI interactiva
    python main.py --headless   # simulación sin GUI (genera reporte)
    python main.py --headless --seconds 120

Controles (GUI):
    SPACE     Pausar / reanudar
    ↑ / ↓     Aumentar / disminuir λ
    F         Simular falla de enlace
    R         Reparar enlaces
    [ / ]     Reducir / aumentar velocidad
    E         Exportar reporte + consultar Gemini
    ESC       Exportar, analizar y salir
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Asegurar que el paquete src/ esté en el path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def run_gui(lam: float | None = None) -> None:
    from simulator.gui import SimulatorApp
    from simulator.simulation import SimConfig

    config = SimConfig()
    if lam is not None:
        config.lam = lam
    SimulatorApp(config).run()


def run_headless(seconds: float = 120.0, lam: float | None = None, analyze: bool = True) -> None:
    """Ejecuta la simulación sin Pygame y genera el reporte."""
    from simulator.api_client import analyze_with_gemini
    from simulator.report import append_analysis, build_report_body, save_report
    from simulator.simulation import NetworkSimulation, SimConfig

    config = SimConfig()
    if lam is not None:
        config.lam = lam
    # Acelerar para headless
    config.sim_speed = 1.0

    sim = NetworkSimulation(config)
    step = 0.05
    target = seconds
    print(f"Simulación headless: {target:.0f}s (λ={config.lam}, μ={config.mu})...")
    while sim.now < target:
        sim.step(step)
        if int(sim.now) % 20 == 0 and abs(sim.now - int(sim.now)) < step:
            m = sim.stats.metrics
            print(
                f"  t={sim.now:6.1f}s  proc={m.departures}  lost={m.lost}  "
                f"L={m.L:.2f}  cost=${sim.stats.total_cost:.2f}"
            )

    path = save_report(sim)
    body = build_report_body(sim)
    print("\n" + body)
    print(f"Reporte guardado en: {path.resolve()}")

    if analyze:
        print("Consultando Gemini API...")
        analysis = analyze_with_gemini(body)
        print("\n===== ANÁLISIS GEMINI =====\n")
        print(analysis)
        append_analysis(analysis, path)
        print(f"\nAnálisis anexado a {path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador dinámico de redes de computadoras")
    parser.add_argument("--headless", action="store_true", help="Correr sin GUI")
    parser.add_argument("--seconds", type=float, default=120.0, help="Duración headless (s)")
    parser.add_argument("--lambda", dest="lam", type=float, default=None, help="Tasa de llegada λ")
    parser.add_argument("--no-api", action="store_true", help="No llamar a Gemini al exportar")
    args = parser.parse_args()

    if args.headless:
        run_headless(seconds=args.seconds, lam=args.lam, analyze=not args.no_api)
    else:
        run_gui(lam=args.lam)


if __name__ == "__main__":
    main()
