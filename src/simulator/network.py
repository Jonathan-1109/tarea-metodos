"""
Modelo de red: nodos (routers), enlaces y paquetes animables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from .inventory import BufferInventory, FlowSignal
from .queueing import QueueMetrics


@dataclass
class Packet:
    """Paquete de datos que atraviesa la red."""

    id: str = field(default_factory=lambda: str(uuid4())[:8])
    created_at: float = 0.0
    enqueue_at: float = 0.0
    service_start: float = 0.0
    first_service_start: float = 0.0  # para Wq extremo-a-extremo
    source: int = 0
    destination: int = 0
    current_node: int = 0
    next_hop: Optional[int] = None
    path: list[int] = field(default_factory=list)
    # Animación sincronizada con el tiempo de SimPy
    progress: float = 0.0  # 0..1 sobre el enlace actual
    transit_start: float = 0.0
    transit_duration: float = 0.05
    in_transit: bool = False
    color: tuple[int, int, int] = (80, 160, 255)

    def update_progress(self, now: float) -> None:
        """Progress = fracción del tiempo de tránsito ya transcurrida."""
        if not self.in_transit or self.transit_duration <= 0:
            return
        self.progress = min(1.0, max(0.0, (now - self.transit_start) / self.transit_duration))


@dataclass
class Link:
    """Enlace de comunicación entre dos nodos."""

    src: int
    dst: int
    # Latencia visible (~0.35s): con λ≈15 se ven varios paquetes en vuelo
    base_latency: float = 0.35
    bandwidth: float = 1.0
    failed: bool = False

    @property
    def current_latency(self) -> float:
        return 1e6 if self.failed else self.base_latency


@dataclass
class Node:
    """Router / switch con buffer de inventario y métricas de cola."""

    id: int
    name: str
    x: float
    y: float
    mu: float = 18.0
    buffer: BufferInventory = field(default_factory=BufferInventory)
    metrics: QueueMetrics = field(default_factory=QueueMetrics)
    queue: list[Packet] = field(default_factory=list)
    busy: bool = False
    flow_throttled: bool = False  # canal de entrada restringido
    pending_admit: int = 0  # créditos Q restantes tras señal de flujo

    def saturation_color(self) -> tuple[int, int, int]:
        """Verde <50%, Amarillo 50–80%, Rojo >80%."""
        sat = self.buffer.saturation
        if sat < 0.5:
            return (46, 204, 113)  # green
        if sat < 0.8:
            return (241, 196, 15)  # yellow
        return (231, 76, 60)  # red

    @property
    def queue_size(self) -> int:
        return len(self.queue)

    @property
    def system_size(self) -> int:
        return len(self.queue) + (1 if self.busy else 0)


@dataclass
class NetworkTopology:
    """Topología estática de la red simulada."""

    nodes: list[Node]
    links: list[Link]

    def link_between(self, a: int, b: int) -> Optional[Link]:
        for link in self.links:
            if (link.src == a and link.dst == b) or (link.src == b and link.dst == a):
                return link
        return None

    def neighbors(self, node_id: int, only_active: bool = True) -> list[int]:
        result = []
        for link in self.links:
            if link.src == node_id:
                other = link.dst
            elif link.dst == node_id:
                other = link.src
            else:
                continue
            if only_active and link.failed:
                continue
            result.append(other)
        return result

    def fail_random_link(self, rng) -> Optional[Link]:
        active = [lk for lk in self.links if not lk.failed]
        if not active:
            return None
        link = active[int(rng.integers(0, len(active)))]
        link.failed = True
        return link

    def repair_all_links(self) -> None:
        for link in self.links:
            link.failed = False


def default_topology(
    mu: float = 18.0,
    S: int = 50,
    s: int = 10,
    Q: int = 20,
    holding: float = 0.01,
    shortage: float = 10.0,
) -> NetworkTopology:
    """
    Topología de ejemplo: 5 nodos (fuente, 3 routers centrales, destino).

        [0 Fuente]
           /  |  \\
        [1]  [2]  [3]   ← routers con buffers
           \\  |  /
        [4 Destino]
    """

    def make_buffer() -> BufferInventory:
        return BufferInventory(
            capacity_S=S,
            threshold_s=s,
            batch_Q=Q,
            holding_cost_rate=holding,
            shortage_penalty=shortage,
        )

    nodes = [
        Node(0, "Fuente", 400, 80, mu=mu, buffer=make_buffer()),
        Node(1, "R1", 160, 280, mu=mu, buffer=make_buffer()),
        Node(2, "R2", 400, 280, mu=mu, buffer=make_buffer()),
        Node(3, "R3", 640, 280, mu=mu, buffer=make_buffer()),
        Node(4, "Destino", 400, 480, mu=mu, buffer=make_buffer()),
    ]

    links = [
        Link(0, 1, base_latency=0.40),
        Link(0, 2, base_latency=0.35),
        Link(0, 3, base_latency=0.45),
        Link(1, 4, base_latency=0.38),
        Link(2, 4, base_latency=0.32),
        Link(3, 4, base_latency=0.40),
        Link(1, 2, base_latency=0.28),
        Link(2, 3, base_latency=0.28),
    ]
    return NetworkTopology(nodes=nodes, links=links)
