"""
Módulo B — Modelos de Inventario (Buffer Control).

Cada router gestiona un buffer de capacidad S con política (s, Q):
cuando el nivel cae por debajo de s se solicita un lote Q (control de flujo).
Incluye costos de mantenimiento (holding) y ruptura (shortage / overflow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class FlowSignal(Enum):
    """Señales de control de flujo emitidas por el buffer."""

    NONE = auto()
    REQUEST_BATCH = auto()  # nivel < s → pedir lote Q / liberar canal
    RELEASE_CHANNEL = auto()


@dataclass
class BufferInventory:
    """
    Inventario de paquetes en el buffer de un nodo.

    Parámetros:
        S: capacidad máxima (inventario).
        s: umbral de reabastecimiento / control de flujo.
        Q: tamaño del lote solicitado al caer bajo s.
        holding_cost_rate: costo por paquete·segundo en buffer.
        shortage_penalty: penalización fija por paquete descartado.
    """

    capacity_S: int = 50
    threshold_s: int = 10
    batch_Q: int = 20
    holding_cost_rate: float = 0.01
    shortage_penalty: float = 10.0

    level: int = 0
    holding_cost: float = 0.0
    shortage_cost: float = 0.0
    overflow_count: int = 0
    flow_requests: int = 0

    _last_t: float = 0.0
    _pending_flow: bool = False

    @property
    def saturation(self) -> float:
        """Fracción de ocupación del buffer [0, 1]."""
        if self.capacity_S <= 0:
            return 1.0
        return min(1.0, self.level / self.capacity_S)

    @property
    def free_slots(self) -> int:
        return max(0, self.capacity_S - self.level)

    def advance_holding(self, now: float) -> None:
        """Acumula costo de almacenamiento proporcional al nivel · tiempo."""
        dt = now - self._last_t
        if dt > 0 and self.level > 0:
            self.holding_cost += self.level * dt * self.holding_cost_rate
        self._last_t = now

    def try_enqueue(self, now: float) -> bool:
        """
        Intenta almacenar un paquete.
        Retorna False ante overflow (ruptura de inventario).
        Al recuperar nivel >= s se rearma la política (s, Q) (histéresis).
        """
        self.advance_holding(now)
        if self.level >= self.capacity_S:
            self.overflow_count += 1
            self.shortage_cost += self.shortage_penalty
            return False
        self.level += 1
        # Histéresis: solo se puede volver a disparar el pedido tras recuperar s
        if self.level >= self.threshold_s:
            self._pending_flow = False
        return True

    def dequeue(self, now: float) -> FlowSignal:
        """
        Extrae un paquete del buffer. Si el nivel cae bajo s,
        emite UNA señal de reabastecimiento / control de flujo
        (no se repite hasta recuperar nivel >= s).
        """
        self.advance_holding(now)
        if self.level <= 0:
            return FlowSignal.NONE
        self.level -= 1
        if self.level < self.threshold_s and not self._pending_flow:
            self._pending_flow = True
            self.flow_requests += 1
            return FlowSignal.REQUEST_BATCH
        return FlowSignal.NONE

    def apply_batch(self, now: float, amount: int | None = None) -> int:
        """
        Aplica el lote Q (o `amount`) liberando capacidad de entrada.
        Retorna cuántos créditos de admisión se otorgan.
        En redes el lote Q modela la reapertura del canal de entrada
        permitiendo hasta Q nuevos ingresos. La bandera de pedido
        permanece activa hasta que el nivel vuelva a >= s.
        """
        self.advance_holding(now)
        q = amount if amount is not None else self.batch_Q
        return min(q, self.free_slots)

    def acknowledge_flow(self) -> None:
        """Fuerza el rearme de la política (p. ej. tras reparación)."""
        self._pending_flow = False

    @property
    def total_cost(self) -> float:
        return self.holding_cost + self.shortage_cost
