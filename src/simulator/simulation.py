"""
Motor de simulación discreta (SimPy) acoplado al reloj de Pygame.

Procesos:
  - Generación de tráfico Poisson (λ)
  - Servicio exponencial (μ) en cada nodo
  - Optimización periódica de enrutamiento (Δt) vía Algoritmo Húngaro
  - Control de flujo (s, Q) sobre buffers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import simpy

from .assignment import optimize_routing
from .inventory import FlowSignal
from .network import NetworkTopology, Packet, default_topology
from .queueing import QueueMetrics, exponential_service, poisson_interarrival


@dataclass
class SimConfig:
    """Parámetros configurables de la simulación."""

    lam: float = 15.0  # λ llegada
    mu: float = 18.0  # μ servicio
    S: int = 50  # capacidad buffer
    s: int = 10  # umbral reabastecimiento
    Q: int = 20  # lote de control de flujo
    alpha: float = 2.0  # peso saturación en Cij
    delta_t: float = 1.0  # intervalo de reoptimización
    holding_cost_rate: float = 0.05
    shortage_penalty: float = 10.0
    seed: int = 42
    sim_speed: float = 1.0  # 1.0 = tiempo real; subir con ] si se quiere más rápido


@dataclass
class GlobalStats:
    """Estadísticas agregadas de toda la red."""

    metrics: QueueMetrics = field(default_factory=QueueMetrics)
    holding_cost: float = 0.0
    shortage_cost: float = 0.0
    assignment_runs: int = 0
    last_assignment_cost: float = 0.0
    flow_signals: int = 0
    # Tabla de enrutamiento: origen → siguiente salto preferido hacia destino
    routing_table: dict[int, int] = field(default_factory=dict)

    @property
    def total_cost(self) -> float:
        return self.holding_cost + self.shortage_cost


class NetworkSimulation:
    """Orquesta SimPy + topología + métricas."""

    DEST = 4  # id del nodo destino

    def __init__(self, config: SimConfig | None = None):
        self.config = config or SimConfig()
        self.rng = np.random.default_rng(self.config.seed)
        self.env = simpy.Environment()
        self.network = default_topology(
            mu=self.config.mu,
            S=self.config.S,
            s=self.config.s,
            Q=self.config.Q,
            holding=self.config.holding_cost_rate,
            shortage=self.config.shortage_penalty,
        )
        # Propagar μ a todos los nodos
        for node in self.network.nodes:
            node.mu = self.config.mu

        self.stats = GlobalStats()
        self.paused = False
        self.finished = False
        self.packets_in_flight: list[Packet] = []
        self._packet_counter = 0
        self._log: list[str] = []

        # Enrutamiento inicial: Fuente→R2, R1/R2/R3→Destino
        self.stats.routing_table = {0: 2, 1: 4, 2: 4, 3: 4}

        # Arrancar procesos SimPy
        self.env.process(self._traffic_generator())
        self.env.process(self._routing_optimizer())
        for node in self.network.nodes:
            if node.id != self.DEST:
                self.env.process(self._node_server(node.id))

    # ------------------------------------------------------------------
    # API pública para la GUI
    # ------------------------------------------------------------------
    @property
    def now(self) -> float:
        return float(self.env.now)

    def step(self, dt: float) -> None:
        """Avanza la simulación `dt` segundos (llamado cada frame)."""
        if self.paused or self.finished:
            return
        target = self.env.now + max(dt, 1e-6) * self.config.sim_speed
        self.env.run(until=target)
        self._refresh_global_costs()
        self._update_transit_animation(dt * self.config.sim_speed)

    def set_lambda(self, value: float) -> None:
        self.config.lam = max(0.1, min(100.0, value))

    def adjust_lambda(self, delta: float) -> None:
        self.set_lambda(self.config.lam + delta)

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def fail_link(self) -> Optional[str]:
        link = self.network.fail_random_link(self.rng)
        if link is None:
            return None
        msg = f"Enlace caído: {link.src}↔{link.dst}"
        self._log_event(msg)
        # Forzar reoptimización inmediata
        self._run_assignment()
        return msg

    def repair_links(self) -> None:
        self.network.repair_all_links()
        self._log_event("Enlaces reparados")
        self._run_assignment()

    # ------------------------------------------------------------------
    # Procesos SimPy
    # ------------------------------------------------------------------
    def _traffic_generator(self):
        """Genera paquetes con llegadas Poisson(λ) en el nodo Fuente."""
        source = self.network.nodes[0]
        while True:
            inter = poisson_interarrival(self.rng, self.config.lam)
            yield self.env.timeout(inter)

            # Control de flujo: si el buffer de fuente está throttled
            if source.flow_throttled and source.pending_admit <= 0:
                # Esperar un poco y reintentar (canal restringido)
                continue

            pkt = Packet(
                id=f"P{self._packet_counter:05d}",
                created_at=self.env.now,
                source=0,
                destination=self.DEST,
                current_node=0,
                color=(
                    60 + int(self.rng.integers(0, 80)),
                    140 + int(self.rng.integers(0, 80)),
                    220 + int(self.rng.integers(0, 35)),
                ),
            )
            self._packet_counter += 1
            admitted = self._admit_packet(source, pkt)
            if admitted and source.flow_throttled:
                source.pending_admit = max(0, source.pending_admit - 1)
                if source.pending_admit == 0:
                    source.flow_throttled = False

    def _node_server(self, node_id: int):
        """Servidor con tiempo de atención Exp(μ) por nodo."""
        node = self.network.nodes[node_id]
        while True:
            if not node.queue:
                yield self.env.timeout(0.01)
                continue

            pkt = node.queue.pop(0)
            node.busy = True
            pkt.service_start = self.env.now
            if pkt.first_service_start <= 0:
                pkt.first_service_start = self.env.now
            wait = pkt.service_start - pkt.enqueue_at
            node.metrics.on_start_service(
                self.env.now, node.system_size, node.queue_size
            )
            # Extrae del inventario; si cruza el umbral s emite señal (s, Q)
            flow_signal = node.buffer.dequeue(self.env.now)

            service_time = exponential_service(self.rng, node.mu)
            yield self.env.timeout(service_time)

            sojourn = self.env.now - pkt.enqueue_at
            node.busy = False
            node.metrics.on_departure(
                self.env.now, wait, sojourn, node.system_size, node.queue_size
            )
            # Las métricas globales de salida se contabilizan solo en entrega final

            # Política de reabastecimiento / control de flujo (s, Q)
            if flow_signal == FlowSignal.REQUEST_BATCH:
                self.stats.flow_signals += 1
                admitted = node.buffer.apply_batch(self.env.now)
                node.flow_throttled = True
                node.pending_admit = admitted
                self._log_event(
                    f"{node.name}: control de flujo (nivel={node.buffer.level}<s), "
                    f"lote Q={admitted}"
                )

            # Reenviar o entregar
            if node_id == self.DEST or pkt.destination == node_id:
                self._deliver(pkt)
            else:
                self._forward(pkt, node_id)

    def _routing_optimizer(self):
        """Cada Δt recalcula la asignación óptima con el Algoritmo Húngaro."""
        while True:
            yield self.env.timeout(self.config.delta_t)
            self._run_assignment()

    # ------------------------------------------------------------------
    # Enrutamiento y admisión
    # ------------------------------------------------------------------
    def _admit_packet(self, node, pkt: Packet) -> bool:
        """Intenta encolar un paquete en el nodo (con política de inventario)."""
        now = self.env.now
        if not node.buffer.try_enqueue(now):
            node.metrics.on_loss(now)
            self.stats.metrics.on_loss(now)
            return False

        pkt.enqueue_at = now
        pkt.current_node = node.id
        node.queue.append(pkt)
        node.metrics.on_enqueue(now, node.system_size, node.queue_size)
        # Contar llegada global solo en el nodo fuente (proceso Poisson)
        if node.id == 0:
            self.stats.metrics.on_enqueue(now, self._total_system(), self._total_queue())
        else:
            self.stats.metrics.set_occupancy(now, self._total_system(), self._total_queue())
        return True

    def _forward(self, pkt: Packet, from_node: int) -> None:
        """Envía el paquete al siguiente salto según la tabla de ruteo."""
        nxt = self._choose_next_hop(from_node)
        if nxt is None:
            # Sin ruta: paquete perdido
            self.stats.metrics.on_loss(self.env.now)
            self._log_event(f"Paquete {pkt.id} perdido: sin ruta desde {from_node}")
            return

        link = self.network.link_between(from_node, nxt)
        if link is None or link.failed:
            self.stats.metrics.on_loss(self.env.now)
            return

        pkt.next_hop = nxt
        pkt.path.append(from_node)
        latency = max(link.current_latency, 0.05)
        pkt.in_transit = True
        pkt.progress = 0.0
        pkt.transit_start = self.env.now
        pkt.transit_duration = latency
        self.packets_in_flight.append(pkt)
        self.env.process(self._transit(pkt, from_node, nxt, latency))

    def _transit(self, pkt: Packet, src: int, dst: int, latency: float):
        """Simula el tiempo de transmisión por el enlace."""
        yield self.env.timeout(latency)
        pkt.in_transit = False
        pkt.progress = 1.0
        if pkt in self.packets_in_flight:
            self.packets_in_flight.remove(pkt)

        target = self.network.nodes[dst]
        pkt.current_node = dst
        pkt.next_hop = None
        if dst == self.DEST:
            # Entrega en destino: métricas extremo a extremo
            self._deliver(pkt)
            return

        if not self._admit_packet(target, pkt):
            self._log_event(f"Overflow en {target.name}: paquete {pkt.id} descartado")

    def _deliver(self, pkt: Packet) -> None:
        """Registra entrega exitosa y actualiza W / Wq globales (e2e)."""
        pkt.path.append(pkt.current_node)
        now = self.env.now
        first_wait = max(0.0, pkt.first_service_start - pkt.created_at) if pkt.first_service_start else 0.0
        sojourn = now - pkt.created_at
        self.stats.metrics.on_departure(
            now, first_wait, sojourn, self._total_system(), self._total_queue()
        )
    def _choose_next_hop(self, from_node: int) -> Optional[int]:
        """Consulta la tabla de ruteo; fallback a vecino activo hacia destino."""
        preferred = self.stats.routing_table.get(from_node)
        if preferred is not None:
            link = self.network.link_between(from_node, preferred)
            if link and not link.failed:
                return preferred

        # Fallback: vecino con menor saturación
        neighbors = self.network.neighbors(from_node, only_active=True)
        if not neighbors:
            return None
        # Preferir destino si es vecino
        if self.DEST in neighbors:
            return self.DEST
        return min(neighbors, key=lambda n: self.network.nodes[n].buffer.saturation)

    def _run_assignment(self) -> None:
        """
        Construye matriz de costos entre flujos (origenes lógicos) y
        enlaces/nodos de salida (routers intermedios), y aplica Húngaro.
        """
        # Flujos: pensamos 3 flujos virtuales desde la fuente hacia R1,R2,R3
        # Enlaces/nodos de salida: routers 1, 2, 3
        routers = [1, 2, 3]
        n_flows = len(routers)
        m_links = len(routers)

        latencies = np.zeros((n_flows, m_links))
        saturations = np.array(
            [self.network.nodes[r].buffer.saturation for r in routers]
        )

        for i, flow_target in enumerate(routers):
            for j, router in enumerate(routers):
                link = self.network.link_between(0, router)
                if link is None or link.failed:
                    latencies[i, j] = 1e6
                else:
                    # Costo base = latencia; se penaliza si el flujo "prefería" otro
                    latencies[i, j] = link.current_latency
                    if router != flow_target:
                        latencies[i, j] += 0.01  # pequeña preferencia de diversidad

        result = optimize_routing(
            latencies, saturations, alpha=self.config.alpha
        )
        self.stats.assignment_runs += 1
        self.stats.last_assignment_cost = result.total_cost

        # Actualizar tabla: fuente → router asignado al flujo 0 (principal)
        # y cada router → destino si el enlace está activo
        if result.pairs:
            # Tomar la asignación de menor costo hacia un router activo
            best = min(result.pairs, key=lambda p: p[2])
            chosen_router = routers[best[1]]
            self.stats.routing_table[0] = chosen_router

        for r in routers:
            link = self.network.link_between(r, self.DEST)
            if link and not link.failed:
                self.stats.routing_table[r] = self.DEST
            else:
                # reroute vía otro router
                alts = [
                    x for x in routers
                    if x != r and self.network.link_between(r, x)
                    and not self.network.link_between(r, x).failed
                ]
                if alts:
                    self.stats.routing_table[r] = min(
                        alts, key=lambda n: self.network.nodes[n].buffer.saturation
                    )

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _total_system(self) -> int:
        return sum(n.system_size for n in self.network.nodes) + len(self.packets_in_flight)

    def _total_queue(self) -> int:
        return sum(n.queue_size for n in self.network.nodes)

    def _refresh_global_costs(self) -> None:
        holding = 0.0
        shortage = 0.0
        for node in self.network.nodes:
            node.buffer.advance_holding(self.env.now)
            holding += node.buffer.holding_cost
            shortage += node.buffer.shortage_cost
        self.stats.holding_cost = holding
        self.stats.shortage_cost = shortage

    def _update_transit_animation(self, dt: float) -> None:
        """Sincroniza el progreso visual con el reloj de SimPy (no con dt arbitrario)."""
        now = self.env.now
        for pkt in self.packets_in_flight:
            pkt.update_progress(now)

    def _log_event(self, msg: str) -> None:
        entry = f"[{self.env.now:7.2f}s] {msg}"
        self._log.append(entry)
        if len(self._log) > 200:
            self._log = self._log[-100:]

    def recent_log(self, n: int = 5) -> list[str]:
        return self._log[-n:]
