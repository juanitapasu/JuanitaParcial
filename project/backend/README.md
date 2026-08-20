# Backend — Planificador Autónomo

Implementación del agente (ver [`../design.md`](../design.md) para el diseño formal y [`../CONTRATO.md`](../CONTRATO.md) para el contrato exacto del plan).

## Estructura

```
backend/
├── src/
│   ├── simulator.py   # Validador de referencia (CONTRATO.md §4) + modelo de
│   │                   búsqueda: State, ScenarioIndex, Applicable(s)/Result(s,a),
│   │                   poda de objetos muertos, macro-acción SWAP
│   ├── demo_plan.py    # Node, uniform_cost_search (UCS), traducción al contrato
│   └── main.py          # FastAPI: POST /api/solve, validación de entrada
├── tests/
│   ├── test_demo_plan.py  # 5 casos obligatorios + verificaciones de poda DROP/PICKUP
│   ├── test_pruning.py     # olvido de objetos muertos + macro-acción SWAP
│   └── test_api.py          # contrato HTTP real (TestClient), entrada malformada
├── requirements.txt
└── .gitignore
```

`simulator.py` responde "¿cómo es el mundo y qué le pasa cuando el robot actúa?" — trae dos capas: el validador imperativo de referencia (`apply_step`/`simulate`, mismas reglas que usará el banco de pruebas del frontend) y el modelo inmutable para la búsqueda (`State`, `get_successors`, `prune_dead_ground`). `demo_plan.py` responde "¿cuál es el mejor plan?": ahí vive UCS y todo lo que es historial de búsqueda (`g`, padre, acción), que nunca se mezcla con el estado físico (design.md, "Nodo vs. Estado"); también traduce la macro-acción interna `SWAP` a su `DROP`+`PICKUP` real antes de responder. Antes de devolver un plan, `build_plan()` lo vuelve a ejecutar contra `simulate()` como red de seguridad.

## Instalar

```bash
cd backend
pip install -r requirements.txt
```

## Levantar el servidor

```bash
cd backend
uvicorn main:app --app-dir src --port 8000
```

```bash
curl http://localhost:8000/api/health
curl -X POST http://localhost:8000/api/solve -H "Content-Type: application/json" -d '{}'
```

Sin `scenario` en el body, usa por defecto `../scenarios/scenario.json`.

Respuesta (formato de `CONTRATO.md` §2):

```json
{
  "solution_found": true,
  "total_cost": 80,
  "steps": [
    {"op": "PICKUP", "item": "KEY1", "cost": 1},
    {"op": "INTERACT", "target": "DOOR1", "action": "OPEN_DOOR", "cost": 2},
    {"op": "MOVE", "from": "Z1", "to": "Z2", "cost": 4}
  ],
  "message": "Plan óptimo (UCS): 35 pasos, costo 80."
}
```

La primera resolución del `scenario.json` real tarda **~50 s** (tiempo de búsqueda UCS, no de red): con 3 puertas+llaves, 3 herramientas y 3 tipos de material hay trasiego real de objetos (ver `SWAP` abajo, y `../scenarios/README.md`). Un escenario propio más chico enviado por body a `/api/solve` (ver `tests/test_api.py`) resuelve en milisegundos.

## Correr los tests

```bash
cd backend
python -m pytest tests/ -v
```

(21 tests, corren en ~1 s — ninguno resuelve el `scenario.json` grande dentro del test; ese se prueba aparte con `python src/demo_plan.py` o levantando el servidor)

## Probar el agente sin levantar el servidor

```bash
cd backend/src
python demo_plan.py
```

Imprime el JSON del plan (mismo formato que devuelve `/api/solve`) para `scenarios/scenario.json`.
