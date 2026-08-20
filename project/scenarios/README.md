# Scenarios

Instancia de la misión que recibe el agente y el frontend.

El archivo de trabajo es `scenario.json`. Es la **fuente de verdad** de esta
demo; el profesor puede enviar otro JSON con las mismas reglas — el agente no
asume nada fijo de esta instancia en particular (ver `design.md`).

## Contenido del demo

- 5 zonas: Z1 CONTROL, Z2 STORAGE, Z3 WORKSHOP (con cargador), Z4 GENERATOR_BAY, Z5 COMMAND_DECK.
- 3 puertas cerradas (DOOR1/DOOR2/DOOR3) con sus llaves (KEY1/KEY2/KEY3) y un corredor sin puerta más caro (Z2↔Z5, costo 12) como ruta alternativa.
- 3 herramientas en Z3 (MULTITOOL, SOLDERING, WIRE_CUTTER) + materiales en Z2 (FUSE ×2, CHIP ×1, CABLE ×1).
- 3 paneles `DAMAGED` (PANEL_A en Z4, PANEL_B y PANEL_C en Z5) y 3 estaciones (GENERATOR, ARTILLERY, COMMAND — COMMAND depende de que GENERATOR esté `ONLINE`, para forzar orden entre estaciones).
- 1 cargador (`CHARGER_1`) en Z3.
- **Capacidad de carga 3.** Reparar los dos paneles de Z5 exige 4 objetos (2 herramientas + 2 materiales) para una capacidad de 3 — hay trasiego real de objetos, no es un problema trivial de recorrido de grafo.
- Batería inicial 55 / máxima 100 — alcanza sin recargar en el plan óptimo actual, pero el cargador está disponible si se cambian los costos.
- Grafo con costos distintos por corredor (apto para UCS: preferir más pasos y menos costo cuando corresponda — ver `design.md`, "Función de costo").

## Cómo leer este mapa

Cinco zonas no quieren decir «cinco estados». Cada objeto que el robot puede
soltar tiene una posición, y `DROP` en cualquier casilla combina esas
posiciones. El agente (`backend/src/simulator.py` + `backend/src/demo_plan.py`)
sólo genera `PICKUP`/`DROP` cuando son relevantes, funde `DROP`+`PICKUP` en un
solo sucesor (`SWAP`) cuando corresponde, y **olvida** la posición de
cualquier objeto ya muerto en vez de conservarla — sin esto último, esta
misma instancia no termina en tiempo razonable (medido: >5 min). Ver
`design.md`, "Olvido de objetos muertos en M" y "`SWAP`: por qué no pierde el
óptimo", con las mediciones reales.

Con las cuatro podas, la búsqueda del plan óptimo (costo 80, 35 pasos) tarda
**~50 s** — es tiempo de búsqueda UCS, no de red; el frontend muestra
`⏳ SEARCHING...` mientras tanto. No es instantáneo porque el dominio no lo
es: 9 identidades recogibles (3 llaves + 3 herramientas + 3 materiales) en 5
zonas con capacidad 3 tienen un espacio de estados genuinamente grande incluso
podado — ver `design.md`, "Formulación y tamaño del espacio".

Si al modificar el agente UCS deja de terminar, no suba la capacidad ni borre
objetos del escenario para "arreglarlo": eso resuelve esta instancia y falla
la siguiente que pruebe el profesor (CONTRATO.md §6). Revise en cambio
`get_successors` en `simulator.py`.
