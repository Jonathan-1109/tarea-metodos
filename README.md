# Simulador Dinámico de Redes de Computadoras

Simulador visual e interactivo (Pygame + SimPy) que integra tres pilares de métodos cuantitativos:

| Concepto | Elemento en la red | Modelado |
|---|---|---|
| **Teoría de colas** | Llegada de paquetes / buffers | Poisson(λ), Exp(μ) → L, Lq, W, Wq |
| **Inventario** | Capacidad de cola y control de flujo | Política (s, Q), holding + shortage |
| **Asignación** | Balanceo dinámico y enrutamiento | Cᵢⱼ = latencia + α·saturación → Húngaro |

Al finalizar (o con la tecla `E`), exporta `reporte_simulacion.txt` y solicita un diagnóstico a la **Gemini API**.

## Requisitos

- Python 3.10–3.12 (recomendado 3.12; pygame aún no publica wheels para 3.14)
- Dependencias en `requirements.txt`

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # y coloca tu GEMINI_API_KEY
```

## Ejecución

```bash
# Interfaz gráfica
python main.py

# Simulación sin GUI (útil para generar el reporte de entrega)
python main.py --headless --seconds 120

# Sin llamar a la API
python main.py --headless --seconds 60 --no-api
```

### Controles (GUI)

| Tecla | Acción |
|---|---|
| `SPACE` | Pausar / reanudar |
| `↑` / `↓` | Subir / bajar λ |
| `F` | Fallar un enlace al azar |
| `R` | Reparar todos los enlaces |
| `[` / `]` | Velocidad de simulación |
| `E` | Exportar reporte + análisis Gemini |
| `ESC` | Exportar, analizar y salir |

## Estructura

```
src/simulator/
  queueing.py      # Módulo A — colas y métricas
  inventory.py     # Módulo B — buffer / (s,Q) / costos
  assignment.py    # Módulo C — matriz C y Algoritmo Húngaro
  network.py       # Nodos, enlaces, paquetes, topología
  simulation.py    # Motor SimPy
  gui.py           # Interfaz Pygame
  report.py        # Exportación TXT
  api_client.py    # Integración Gemini
main.py            # Entrada
reporte_simulacion.txt
```

## Parámetros por defecto

- λ = 15.0 paquetes/s  
- μ = 18.0 paquetes/s  
- S = 50, s = 10, Q = 20  
- Δt (reoptimización Húngaro) = 1.0 s  
