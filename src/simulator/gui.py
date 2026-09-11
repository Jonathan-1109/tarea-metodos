"""
Interfaz gráfica Pygame: nodos coloreados por saturación, enlaces dinámicos,
paquetes animados y dashboard interactivo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pygame

from .api_client import analyze_with_gemini
from .report import append_analysis, build_report_body, save_report
from .simulation import NetworkSimulation, SimConfig

# --- Paleta ---
BG = (18, 24, 38)
PANEL = (28, 36, 54)
PANEL_BORDER = (55, 70, 100)
TEXT = (230, 235, 245)
MUTED = (140, 155, 180)
LINK_OK = (70, 110, 170)
LINK_FAIL = (180, 50, 50)
ACCENT = (90, 180, 255)
WHITE = (255, 255, 255)

WIDTH, HEIGHT = 1100, 700
FPS = 60
NODE_RADIUS = 32


class SimulatorApp:
    """Aplicación Pygame del simulador de red."""

    def __init__(self, config: SimConfig | None = None):
        pygame.init()
        pygame.display.set_caption("Simulador Dinámico de Redes — Métodos Cuantitativos")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)
        self.font_sm = pygame.font.SysFont("consolas", 13)
        self.font_lg = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_title = pygame.font.SysFont("consolas", 22, bold=True)

        self.sim = NetworkSimulation(config or SimConfig())
        self.status_msg = (
            "SPACE pausa | ↑↓ λ | F falla | R repara | [/] velocidad | E exporta+API | ESC salir"
        )
        self.running = True
        self._exporting = False

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._handle_events()
            self.sim.step(dt)
            self._draw()
        pygame.quit()

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._on_key(event.key)

    def _on_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_e:
            self._export_and_analyze()
        elif key == pygame.K_SPACE:
            self.sim.toggle_pause()
            self.status_msg = "PAUSADO" if self.sim.paused else "Simulación en curso"
        elif key in (pygame.K_UP, pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.sim.adjust_lambda(1.0)
            self.status_msg = f"λ = {self.sim.config.lam:.1f}"
        elif key in (pygame.K_DOWN, pygame.K_MINUS, pygame.K_KP_MINUS):
            self.sim.adjust_lambda(-1.0)
            self.status_msg = f"λ = {self.sim.config.lam:.1f}"
        elif key == pygame.K_f:
            msg = self.sim.fail_link()
            self.status_msg = msg or "No hay enlaces activos para fallar"
        elif key == pygame.K_r:
            self.sim.repair_links()
            self.status_msg = "Todos los enlaces reparados"
        elif key == pygame.K_LEFTBRACKET:
            self.sim.config.sim_speed = max(0.25, self.sim.config.sim_speed / 2)
            self.status_msg = f"Velocidad ×{self.sim.config.sim_speed:.2f}"
        elif key == pygame.K_RIGHTBRACKET:
            self.sim.config.sim_speed = min(16.0, self.sim.config.sim_speed * 2)
            self.status_msg = f"Velocidad ×{self.sim.config.sim_speed:.2f}"

    def _export_and_analyze(self) -> None:
        if self._exporting:
            return
        self._exporting = True
        self.status_msg = "Exportando reporte y consultando Gemini API..."
        # Redibujar para mostrar el mensaje
        self._draw()
        pygame.display.flip()

        path = save_report(self.sim)
        report_text = build_report_body(self.sim)
        print("\n" + report_text)

        print("Consultando Gemini API...")
        analysis = analyze_with_gemini(report_text)
        print("\n===== ANÁLISIS GEMINI =====\n")
        print(analysis)
        print("\n===========================\n")

        append_analysis(analysis, path)
        self.status_msg = f"Reporte guardado en {path.resolve()}"
        self._exporting = False

    # ------------------------------------------------------------------
    # Dibujo
    # ------------------------------------------------------------------
    def _draw(self) -> None:
        self.screen.fill(BG)
        self._draw_links()
        self._draw_packets()
        self._draw_nodes()
        self._draw_dashboard()
        self._draw_footer()
        pygame.display.flip()

    def _draw_links(self) -> None:
        for link in self.sim.network.links:
            a = self.sim.network.nodes[link.src]
            b = self.sim.network.nodes[link.dst]
            color = LINK_FAIL if link.failed else LINK_OK
            width = 2 if link.failed else 3
            pygame.draw.line(
                self.screen, color, (int(a.x), int(a.y)), (int(b.x), int(b.y)), width
            )
            if link.failed:
                mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
                pygame.draw.line(
                    self.screen, LINK_FAIL, (mx - 8, my - 8), (mx + 8, my + 8), 2
                )
                pygame.draw.line(
                    self.screen, LINK_FAIL, (mx - 8, my + 8), (mx + 8, my - 8), 2
                )

    def _draw_nodes(self) -> None:
        for node in self.sim.network.nodes:
            color = node.saturation_color()
            pos = (int(node.x), int(node.y))
            pygame.draw.circle(self.screen, color, pos, NODE_RADIUS)
            pygame.draw.circle(self.screen, WHITE, pos, NODE_RADIUS, 2)

            # Anillo interior si el servidor está ocupado
            if node.busy:
                pygame.draw.circle(self.screen, ACCENT, pos, NODE_RADIUS - 8, 2)

            label = self.font.render(node.name, True, TEXT)
            self.screen.blit(
                label, (pos[0] - label.get_width() // 2, pos[1] - NODE_RADIUS - 20)
            )
            q_txt = self.font_sm.render(
                f"q={node.queue_size}/{node.buffer.capacity_S}", True, MUTED
            )
            self.screen.blit(
                q_txt, (pos[0] - q_txt.get_width() // 2, pos[1] + NODE_RADIUS + 6)
            )

            # Paquetes en cola: apilados junto al nodo (máx. 12 visibles)
            self._draw_queue_stack(node)

            # Indicador de ruta preferida desde fuente
            if node.id == 0:
                nxt = self.sim.stats.routing_table.get(0)
                if nxt is not None:
                    route = self.font_sm.render(f"→ R{nxt}", True, ACCENT)
                    self.screen.blit(
                        route, (pos[0] - route.get_width() // 2, pos[1] - 8)
                    )

    def _draw_queue_stack(self, node) -> None:
        """Dibuja hasta 12 paquetes en cola como puntos apilados al lado del nodo."""
        n = min(len(node.queue), 12)
        if n == 0:
            return
        base_x = int(node.x + NODE_RADIUS + 14)
        base_y = int(node.y + 18)
        for i in range(n):
            col = i % 4
            row = i // 4
            x = base_x + col * 9
            y = base_y - row * 9
            pygame.draw.circle(self.screen, (100, 180, 255), (x, y), 4)
            pygame.draw.circle(self.screen, WHITE, (x, y), 4, 1)
        if len(node.queue) > 12:
            extra = self.font_sm.render(f"+{len(node.queue) - 12}", True, MUTED)
            self.screen.blit(extra, (base_x, base_y + 12))

    def _draw_packets(self) -> None:
        """Paquetes en tránsito: posición = interpolación lineal según progress sincronizado."""
        for pkt in self.sim.packets_in_flight:
            if pkt.next_hop is None:
                continue
            a = self.sim.network.nodes[pkt.current_node]
            b = self.sim.network.nodes[pkt.next_hop]
            # Suavizado ligero (ease-in-out) para que no se sienta a tirones
            t = pkt.progress
            t_smooth = t * t * (3.0 - 2.0 * t)
            x = a.x + (b.x - a.x) * t_smooth
            y = a.y + (b.y - a.y) * t_smooth
            # Estela corta hacia atrás
            if t > 0.05:
                tx = a.x + (b.x - a.x) * max(0.0, t_smooth - 0.08)
                ty = a.y + (b.y - a.y) * max(0.0, t_smooth - 0.08)
                pygame.draw.circle(self.screen, (40, 90, 160), (int(tx), int(ty)), 4)
            pygame.draw.circle(self.screen, pkt.color, (int(x), int(y)), 7)
            pygame.draw.circle(self.screen, WHITE, (int(x), int(y)), 7, 1)

    def _draw_dashboard(self) -> None:
        panel = pygame.Rect(820, 20, 260, 570)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, 1, border_radius=8)

        cfg = self.sim.config
        st = self.sim.stats
        m = st.metrics
        m.advance(self.sim.now)

        rows = [
            ("DASHBOARD", "title"),
            ("", "blank"),
            (f"Tiempo      {self.sim.now:7.1f} s", "text"),
            (f"Estado      {'PAUSA' if self.sim.paused else 'RUN'}", "text"),
            (f"Velocidad   ×{cfg.sim_speed:.2f}", "text"),
            ("", "blank"),
            (f"λ llegada   {cfg.lam:5.1f}", "text"),
            (f"μ servicio  {cfg.mu:5.1f}", "text"),
            (f"S capacidad {cfg.S}", "text"),
            (f"s umbral    {cfg.s}", "text"),
            (f"Q lote      {cfg.Q}", "text"),
            ("", "blank"),
            ("— COLAS —", "header"),
            (f"L  = {m.L:.3f}    W  = {m.W:.3f} s", "text"),
            (f"Lq = {m.Lq:.3f}    Wq = {m.Wq:.3f} s", "text"),
            ("", "blank"),
            ("— TRÁFICO —", "header"),
            (f"Procesados {m.departures}", "text"),
            (f"Perdidos   {m.lost}", "text"),
            (f"Pérdida    {m.loss_rate:.2f}%", "text"),
            ("", "blank"),
            ("— COSTOS —", "header"),
            (f"Holding  ${st.holding_cost:.2f}", "text"),
            (f"Shortage ${st.shortage_cost:.2f}", "text"),
            (f"Global   ${st.total_cost:.2f}", "text"),
            ("", "blank"),
            ("— ASIGNACIÓN —", "header"),
            (f"Húngaro {st.assignment_runs}", "text"),
            (f"Costo   {st.last_assignment_cost:.4f}", "text"),
            (f"Flujo   {st.flow_signals} señales", "text"),
            ("", "blank"),
            ("— COLAS POR NODO —", "header"),
        ]

        y = panel.y + 14
        for text, kind in rows:
            if kind == "blank":
                y += 5
            elif kind == "title":
                self.screen.blit(self.font_lg.render(text, True, ACCENT), (panel.x + 12, y))
                y += 23
            elif kind == "header":
                self.screen.blit(self.font_sm.render(text, True, ACCENT), (panel.x + 12, y))
                y += 17
            else:
                self.screen.blit(self.font_sm.render(text, True, TEXT), (panel.x + 12, y))
                y += 16

        for node in self.sim.network.nodes:
            sat = node.buffer.saturation * 100
            line = f"{node.name:7s} {node.queue_size:2d} ({sat:5.1f}%)"
            self.screen.blit(self.font_sm.render(line, True, MUTED), (panel.x + 12, y))
            y += 16

    def _draw_footer(self) -> None:
        bar = pygame.Rect(0, HEIGHT - 50, WIDTH, 50)
        pygame.draw.rect(self.screen, PANEL, bar)
        title = self.font_title.render(
            "Simulador Dinámico de Redes de Computadoras", True, TEXT
        )
        self.screen.blit(title, (16, HEIGHT - 42))
        msg = self.font_sm.render(self.status_msg, True, MUTED)
        self.screen.blit(msg, (16, HEIGHT - 20))

        # Log reciente a la izquierda bajo la topología
        log_y = 520
        for entry in self.sim.recent_log(4):
            self.screen.blit(self.font_sm.render(entry[:90], True, MUTED), (20, log_y))
            log_y += 16


def main() -> None:
    """Punto de entrada de la GUI."""
    # Permitir override de λ vía argv: python -m simulator.gui 20
    config = SimConfig()
    if len(sys.argv) > 1:
        try:
            config.lam = float(sys.argv[1])
        except ValueError:
            pass
    app = SimulatorApp(config)
    app.run()


if __name__ == "__main__":
    main()
