"""
Módulo C — Asignación Óptima (Algoritmo Húngaro).

En intervalos Δt construye la matriz de costos:

    C[i][j] = latencia_enlace_ij + α · saturación_buffer_j

y resuelve la asignación uno-a-uno de mínimo costo con el
Algoritmo Húngaro (scipy.optimize.linear_sum_assignment).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass
class AssignmentResult:
    """Resultado de una corrida del Algoritmo Húngaro."""

    row_ind: np.ndarray
    col_ind: np.ndarray
    total_cost: float
    cost_matrix: np.ndarray
    pairs: list[tuple[int, int, float]]  # (flujo_i, enlace_j, costo)


def build_cost_matrix(
    link_latencies: np.ndarray,
    buffer_saturations: np.ndarray,
    alpha: float = 1.0,
) -> np.ndarray:
    """
    Construye C[i,j] = latencia[i,j] + α * saturación[j].

    Args:
        link_latencies: matriz (N flujos × M enlaces/nodos) de latencias.
        buffer_saturations: vector (M,) con saturación [0,1] de cada destino.
        alpha: peso de la saturación en el costo.
    """
    lat = np.asarray(link_latencies, dtype=float)
    sat = np.asarray(buffer_saturations, dtype=float).reshape(1, -1)
    if lat.ndim != 2:
        raise ValueError("link_latencies debe ser una matriz 2D")
    if sat.shape[1] != lat.shape[1]:
        raise ValueError("Dimensión de saturaciones no coincide con columnas de latencia")
    return lat + alpha * sat


def hungarian_assign(cost_matrix: np.ndarray) -> AssignmentResult:
    """
    Ejecuta el Algoritmo Húngaro para minimizar el costo total de asignación.

    Usa scipy.optimize.linear_sum_assignment (método húngaro / Jonker-Volgenant).
    """
    C = np.asarray(cost_matrix, dtype=float)
    # Enlaces caídos / no disponibles se marcan con un costo muy alto
    C = np.nan_to_num(C, nan=1e9, posinf=1e9, neginf=1e9)

    row_ind, col_ind = linear_sum_assignment(C)
    pairs: list[tuple[int, int, float]] = []
    total = 0.0
    for r, c in zip(row_ind, col_ind):
        cost = float(C[r, c])
        pairs.append((int(r), int(c), cost))
        total += cost

    return AssignmentResult(
        row_ind=row_ind,
        col_ind=col_ind,
        total_cost=total,
        cost_matrix=C,
        pairs=pairs,
    )


def optimize_routing(
    link_latencies: np.ndarray,
    buffer_saturations: np.ndarray,
    alpha: float = 1.0,
) -> AssignmentResult:
    """Atajo: construye C y resuelve la asignación óptima."""
    C = build_cost_matrix(link_latencies, buffer_saturations, alpha)
    return hungarian_assign(C)
