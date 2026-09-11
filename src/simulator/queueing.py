"""
Módulo A — Teoría de Colas (Líneas de Espera).

Modela llegadas Poisson (λ) y servicio exponencial (μ), y calcula
en tiempo real las métricas clásicas L, Lq, W y Wq.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QueueMetrics:
    """Acumuladores y métricas derivadas de un sistema de colas M/M/1-like."""

    # Contadores de eventos
    arrivals: int = 0
    departures: int = 0
    lost: int = 0

    # Integrales temporales para promedios de Little
    _area_system: float = 0.0  # ∫ N(t) dt  → L
    _area_queue: float = 0.0  # ∫ Nq(t) dt → Lq
    _last_t: float = 0.0
    _n_system: int = 0
    _n_queue: int = 0

    # Tiempos individuales (para W y Wq empíricos)
    _wait_sum: float = 0.0  # suma de Wq
    _sojourn_sum: float = 0.0  # suma de W
    _samples: int = 0

    def advance(self, now: float) -> None:
        """Actualiza las áreas bajo la curva hasta el instante `now`."""
        dt = now - self._last_t
        if dt > 0:
            self._area_system += self._n_system * dt
            self._area_queue += self._n_queue * dt
            self._last_t = now

    def set_occupancy(self, now: float, system_size: int, queue_size: int) -> None:
        """Actualiza N(t) / Nq(t) sin registrar un evento de llegada."""
        self.advance(now)
        self._n_system = system_size
        self._n_queue = queue_size

    def on_enqueue(self, now: float, system_size: int, queue_size: int) -> None:
        self.advance(now)
        self.arrivals += 1
        self._n_system = system_size
        self._n_queue = queue_size

    def on_loss(self, now: float) -> None:
        self.advance(now)
        self.lost += 1

    def on_start_service(self, now: float, system_size: int, queue_size: int) -> None:
        self.advance(now)
        self._n_system = system_size
        self._n_queue = queue_size

    def on_departure(
        self,
        now: float,
        wait_time: float,
        sojourn_time: float,
        system_size: int,
        queue_size: int,
    ) -> None:
        self.advance(now)
        self.departures += 1
        self._wait_sum += wait_time
        self._sojourn_sum += sojourn_time
        self._samples += 1
        self._n_system = system_size
        self._n_queue = queue_size

    @property
    def L(self) -> float:
        """Número promedio de paquetes en el sistema."""
        t = self._last_t
        return self._area_system / t if t > 0 else 0.0

    @property
    def Lq(self) -> float:
        """Número promedio de paquetes en cola."""
        t = self._last_t
        return self._area_queue / t if t > 0 else 0.0

    @property
    def W(self) -> float:
        """Tiempo medio de estancia total en la red."""
        return self._sojourn_sum / self._samples if self._samples else 0.0

    @property
    def Wq(self) -> float:
        """Tiempo medio de espera en cola antes de ser transmitido."""
        return self._wait_sum / self._samples if self._samples else 0.0

    @property
    def loss_rate(self) -> float:
        """Tasa de pérdida = perdidos / (procesados + perdidos)."""
        total = self.departures + self.lost
        return (self.lost / total * 100.0) if total else 0.0

    def snapshot(self, now: float) -> dict[str, float]:
        self.advance(now)
        return {
            "L": self.L,
            "Lq": self.Lq,
            "W": self.W,
            "Wq": self.Wq,
            "loss_rate": self.loss_rate,
            "processed": float(self.departures),
            "lost": float(self.lost),
        }


def poisson_interarrival(rng, lam: float) -> float:
    """Tiempo entre llegadas ~ Exp(λ) equivalente a proceso de Poisson."""
    if lam <= 0:
        return float("inf")
    return float(rng.exponential(1.0 / lam))


def exponential_service(rng, mu: float) -> float:
    """Tiempo de servicio ~ Exp(μ)."""
    if mu <= 0:
        return float("inf")
    return float(rng.exponential(1.0 / mu))
