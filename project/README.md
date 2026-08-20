# Proyecto — Emergency Control

El diseño interno de la IA lo escribe usted en [`design.md`](design.md) **antes**
de implementar. Ese archivo ya trae las subsecciones que debe completar
(estado, acciones, `DROP`, batería, tamaño del espacio). El enunciado está en
el `README.MD` de la raíz; las reglas del mundo, en [`CONTRATO.md`](CONTRATO.md).

## Estructura

```text
project/
├── frontend/          # React + R3F — simulación 3D voxel
├── backend/           # FastAPI — POST /api/solve (plan demo)
├── scenarios/         # scenario.json — fuente de verdad
├── design.md
└── README.md
```

## Cómo levantar (tú)

Abre **dos terminales**.

### Terminal 1 — Backend

```bash
cd project/backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --app-dir src --port 8000
```

Comprobar: http://127.0.0.1:8000/api/health

### Terminal 2 — Frontend

```bash
cd project/frontend
npm install
npm run dev
```

Abrir: http://localhost:5173

Pulsa **EXECUTE PLAN**. El frontend llama a `/api/solve` (proxy Vite → puerto 8000) y reproduce el plan casilla a casilla. La primera búsqueda tarda **~50 s** (el botón muestra `⏳ SEARCHING...` mientras UCS resuelve; es tiempo de cómputo, no de red — ver `design.md`, "Evidencia empírica").

`/api/solve` corre `uniform_cost_search` (`backend/src/demo_plan.py`) sobre `scenarios/scenario.json` y devuelve el plan **óptimo** ya traducido al contrato — no es un plan artesanal ni hardcodeado.

### Tests del plan

```bash
cd project/backend
.\.venv\Scripts\activate
python -m pytest tests/ -v
```

21 tests (agente, poda de objetos muertos + `SWAP`, contrato HTTP real vía `TestClient`), corren en ~1 s.

## Contrato visual vs agente (importante)

La versión oficial y completa de este contrato (esquema JSON, acciones de `INTERACT`, reglas del mundo y costos) está en [`CONTRATO.md`](CONTRATO.md), que forma parte del enunciado.

El enunciado fija **4 operaciones visuales** que el frontend entiende:

```text
MOVE | PICKUP | DROP | INTERACT
```

`REPAIR`, `ACTIVATE`, `OPEN_DOOR`, `RECHARGE` **no son ops del plan de alto nivel**: son el campo `action` dentro de un paso `INTERACT`.

Ejemplo de lo que devuelve `/api/solve`:

```json
{ "op": "INTERACT", "target": "PANEL_A", "action": "REPAIR", "consumes": "FUSE", "cost": 2 }
```

- **Agente (estudiante):** modela acciones internas propias (`MOVE`, `PICKUP`, `DROP`, `INTERACT` genérico) sobre un estado `<P,B,C,E,M>` (ver `design.md`) y luego **traduce** cada paso del plan óptimo a este formato exacto.
- **Frontend / banco de pruebas:** solo ejecuta esas 4 ops. El log muestra `INTERACT REPAIR ...` para dejar claro el `op` + el `action`.

Así no hay contradicción: la capa visual no define la IA; solo anima el plan ya traducido.
