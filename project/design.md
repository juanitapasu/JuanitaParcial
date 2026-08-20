# Diseño del agente

Este documento debe completarse **antes** de la implementación principal del agente.

Use sus propias palabras y notación. No reemplace este archivo por una transcripción
del enunciado. Las subsecciones existen para que no se le olvide una decisión;
usted decide el contenido.

El entorno, según las propiedades vistas en clase, es totalmente observable,
determinista, secuencial, estático, discreto y de agente único. Bajo esas
condiciones la solución es un **plan completo** y el marco correcto es la
búsqueda clásica. Justifique cada componente con ese marco (AIMA, cap. 3).

---

## Estado

### Definición formal

```text
s = ⟨ P, B, C, E, M ⟩
```

- **P (posición):** la zona donde está el robot en este momento. Es un solo valor, por ejemplo `"Z2"`.
- **B (batería):** un número entero entre 0 y la batería máxima del escenario.
- **C (carga / cargo):** lo que el robot lleva encima en este momento, contado por tipo de ítem (no por objeto individual). Por ejemplo `{wrench: 1, fuse_box: 1}`.
- **E (entorno):** el estado de todo lo que es "permanente" en la instalación: puertas (`CLOSED`/`OPEN`), paneles (`DAMAGED`/`OK`), estaciones (`OFFLINE`/`ONLINE`), etc.
- **M (mapa de ítems en el piso):** cuántas unidades de cada tipo de ítem quedan tiradas en cada zona en este momento. Por ejemplo `{(Z2, fuse_box): 1}`.

Este estado es lo que el robot necesita mirar para saber, en cualquier instante, qué puede hacer a continuación. No incluye nada de "cómo llegó hasta aquí" — eso vive en el Nodo (ver más abajo).

### Por qué cada variable es necesaria

El criterio que usamos es el mismo que da la guía: **una variable pertenece al estado si y solo si dos configuraciones que difieran solo en ella pueden diferir en las acciones legales futuras o en su resultado.**

- **P** es necesaria porque `MOVE` y `INTERACT` solo son legales desde ciertas zonas. Sin P no sabríamos ni siquiera qué acciones están al alcance del robot.
- **B** es necesaria porque una `MOVE` cara puede volverse ilegal si no queda batería suficiente. Dos estados iguales en todo lo demás pero con distinta batería pueden tener distinto futuro: uno puede llegar a la próxima zona y el otro no. Por eso la batería es parte de la *situación física* del robot, tal como dice el enunciado en 2.1, y no solo un dato de historial.
- **C** es necesaria porque las operaciones (`INTERACT`) exigen tener ciertas herramientas o materiales encima. Sin C no sabríamos si el robot puede instalar un fusible o reparar el sistema de enfriamiento. También determina cuánto espacio libre queda para recoger algo nuevo.
- **E** es necesaria porque ahí viven las dependencias entre operaciones (por ejemplo, no se puede instalar el fusible si la puerta sigue cerrada) y porque la meta de la misión se verifica sobre E.
- **M** es necesaria porque, si el robot puede soltar objetos (`DROP`, sección 2.2 del enunciado), la posición de los ítems **no** se puede deducir del escenario inicial: un ítem puede terminar en una zona distinta a la que empezó. Sin M el agente no sabría qué hay disponible para recoger en cada zona.

### Qué información se deriva y NO se almacena

Todo lo que es una **constante del escenario** (no cambia mientras el robot actúa) se queda fuera del estado y se consulta directamente del archivo `scenario.json`:

- el peso y tipo (herramienta/material) de cada ítem,
- el grafo de corredores y sus costos,
- la capacidad máxima de carga,
- la batería máxima,
- las precondiciones y efectos de cada operación.

Si un dato se puede calcular a partir del estado actual más estas constantes (por ejemplo, "cuánto peso llevo encima" se calcula sumando pesos según C), tampoco se guarda por separado.

### Qué pertenece al historial de búsqueda y no al estado físico

El **costo acumulado** `g(n)`, el **puntero al nodo padre** y la **acción que trajo hasta aquí** describen *cómo llegó el robot a esta situación*, no *en qué situación está*. Esa información vive en el **Nodo de búsqueda**, no en el estado:

```text
Nodo = ⟨ estado, padre, acción, g ⟩
```

Esto importa porque dos caminos de acciones completamente distintos pueden terminar exactamente en el mismo mundo físico (mismo P, C, E, M). Si mezcláramos `g` o el padre dentro del estado, esos dos caminos nunca se reconocerían como "el mismo lugar" y CLOSED no podría fusionarlos — la búsqueda trataría el grafo como si fuera un árbol y reexploraría el mismo mundo una y otra vez.

### Cuándo dos configuraciones son el mismo estado

Dos configuraciones son el mismo estado si tienen el mismo P, el mismo C, el mismo E y el mismo M.

Dos detalles de implementación son clave para que esta igualdad funcione bien:

1. **Los ítems del mismo tipo no llevan identificador individual** (sección 2.2 del enunciado). C y M se representan como *contadores por tipo* (por ejemplo, "2 fusibles", no "fusible #1" y "fusible #2"). Así, dos formas distintas de llegar a "tengo 2 fusibles" son el mismo estado, en vez de ser tratadas como situaciones distintas.
2. **Las estructuras se guardan en una forma canónica** (tuplas ordenadas, no diccionarios con orden arbitrario), para que dos estados físicamente iguales produzcan siempre el mismo `hash` y pasen la comparación `==`, sin importar en qué orden se insertaron los datos. Sin esto, Graph Search no reconoce estados repetidos y el espacio de búsqueda se dispara.

**Sobre la batería:** aunque B sí forma parte de la tupla física (ver arriba), **no se usa para decidir si dos estados son "el mismo"**. La igualdad (`==`/`hash`) que usa CLOSED se calcula solo sobre `⟨P, C, E, M⟩`. La batería se trata aparte, con una regla de **dominancia**, explicada en la sección "Batería como recurso" más abajo. Esto no es un descuido: es necesario para que CLOSED pueda fusionar caminos que llegan al mismo mundo con distinta batería, sin perder la posibilidad de que la batería extra sea justo lo que permite terminar la misión.

### Relevancia: objetos que ya no cambian el futuro

Los cambios en E son **monótonos**: una puerta que ya se abrió no se vuelve a cerrar, un panel reparado no vuelve a `DAMAGED`. Esto tiene una consecuencia directa sobre los objetos: **una vez que un ítem cumplió la función para la que servía, ya no puede habilitar ninguna acción futura**.

Ejemplo: una tarjeta de acceso (`keycard`) que ya abrió la puerta que tenía que abrir. Da igual si esa tarjeta queda en el inventario del robot o tirada en cualquier zona — ninguna operación pendiente la necesita, así que su ubicación exacta ya no distingue estados relevantes para el plan. Si el agente sigue generando `PICKUP`/`DROP` para ese tipo de ítem, lo único que logra es multiplicar el número de estados con permutaciones de "dónde quedó el objeto muerto", sin acercarse nunca a la meta (que se define solo sobre E, nunca sobre C o M).

Por eso el agente clasifica cada ítem como **relevante** o **irrelevante** en cada estado:

```text
un ítem i es relevante en el estado s
  si y solo si
existe una operación pendiente (no cumplida todavía en E)
que necesita ese ítem como herramienta o como material
```

Un ítem que deja de ser relevante nunca se vuelve a generar como `PICKUP`, y es el primer candidato para `DROP` cuando hace falta liberar espacio (ver sección de Acciones). Ignorarlo no pierde el plan óptimo: cualquier plan que cargue o suelte un ítem irrelevante se puede acortar quitando esas dos acciones, sin romper ninguna precondición futura, y el plan resultante cuesta menos o igual. Es decir, esas acciones nunca pueden ser parte de un plan de costo mínimo.

---

## Acciones

| Acción | Precondiciones | Efectos | Costo |
|---|---|---|---|
| `MOVE(p → p')` | robot en `p`; existe corredor `(p,p')`; entorno cumple los requisitos del corredor (si los hay, p. ej. una puerta abierta); batería ≥ costo | posición pasa a `p'`; batería −= costo del corredor | costo del corredor `(p,p')` (fijo en el escenario) |
| `PICKUP(i)` | hay al menos 1 unidad de `i` en la zona actual; cabe en la capacidad restante; `i` es relevante; batería ≥ costo | +1 unidad de `i` en la carga; −1 unidad de `i` en el piso; batería −= costo | costo fijo de `PICKUP` (constante del escenario) |
| `DROP(i)` | el robot carga al menos 1 unidad de `i`; batería ≥ costo; se cumple la regla de poda (ver abajo) | −1 unidad de `i` en la carga; +1 unidad de `i` en el piso; batería −= costo | costo fijo de `DROP` (constante del escenario) |
| `INTERACT(op)` | robot en la zona de la operación; tiene las herramientas requeridas (no se consumen); tiene los materiales requeridos (sí se consumen); se cumplen las dependencias de entorno; la operación aún no está hecha; batería ≥ costo | el entorno cambia según lo que defina la operación; se descuentan los materiales consumidos de la carga; batería −= costo | costo fijo de `INTERACT` (mismo valor para abrir puerta/reparar/activar; `RECHARGE` usa su propio costo) |
| `SWAP(x↓, y↑)` *(interna, ver abajo)* | igual que `DROP(x)` seguido de `PICKUP(y)`, evaluadas en ese orden | `DROP(x)` + `PICKUP(y)` en un solo paso de búsqueda | `costo(DROP) + costo(PICKUP)` |

`INTERACT(op)` es una acción genérica que representa cualquier operación concreta del escenario: abrir una puerta, reparar un panel, activar una estación o recargar batería. Cada operación trae su propia lista de herramientas, materiales, dependencias de entorno y efectos.

`SWAP` no es una operación del contrato: es una **macro-acción interna** que el traductor (`build_plan`) siempre expande a su `DROP` real seguido de su `PICKUP` real antes de emitir el plan — el frontend nunca ve un `SWAP`. Existe únicamente para que la búsqueda no tenga que registrar en CLOSED, como nodo aparte, el estado intermedio "recién soltado, todavía no recogido" (ver "SWAP: por qué no pierde el óptimo" más abajo).

**Sobre el costo:** en este dominio el costo de cada acción **no es un número libre que el agente inventa** — viene fijado por el escenario: el `MOVE` cuesta lo que cueste el corredor usado, y `PICKUP`/`DROP`/`INTERACT` cuestan un valor constante por tipo de acción (por ejemplo, todo `PICKUP` cuesta lo mismo, sin importar qué se recoja). Ese mismo número es, además, lo que se descuenta de la batería: **toda** acción gasta batería igual a su costo, no solo `MOVE`. Por eso una precondición implícita de cualquier acción es `batería ≥ costo(a)` — el robot no puede ejecutar un paso que lo dejaría con batería negativa.

### `Applicable` interno vs legalidad del contrato

El simulador (contrato) dice cuándo un paso es **legal**: por ejemplo, permite hacer `DROP` de cualquier ítem cargado en cualquier zona, en cualquier momento. Pero el generador de sucesores del agente no tiene que ofrecer todas las acciones legales — solo las que un plan **óptimo** podría llegar a necesitar. Esa es la diferencia entre "legal" y "relevante para buscar".

**Por qué no se genera `DROP` en cada estado con carga.** Si el agente generara un `DROP` por cada ítem cargado en cada estado, el problema dejaría de ser "5 zonas y unas tareas" para convertirse en "en cuál de las 5 zonas quedó cada unidad de cada objeto en cada momento posible". Eso es una explosión combinatoria del número de sucesores por estado (el factor de ramificación `b`), y además crea ciclos inútiles del tipo `DROP → PICKUP → DROP → …` que la búsqueda tendría que detectar en tiempo de ejecución en vez de evitar por diseño.

**La regla que sí se usa:**

1. `PICKUP(i)` solo se genera si `i` es relevante en ese estado (sección anterior) y si cabe en la capacidad libre. Recoger algo que ninguna operación pendiente necesita no puede ayudar a llegar a la meta.
2. `DROP(i)` solo se genera cuando la capacidad está llena **y** hay en la zona actual un ítem relevante que el robot necesita recoger pero no le cabe. Es decir, `DROP` siempre es un paso para habilitar un `PICKUP` importante, nunca un fin en sí mismo. Entre los ítems cargados, primero se ofrece soltar los que ya son irrelevantes (ya cumplieron su función); solo si todos los ítems cargados siguen siendo relevantes se ofrece `DROP` para cada uno de ellos como última opción, y ahí el número de alternativas está acotado por la capacidad máxima, no por la cantidad de zonas ni de tipos de ítem.

**Por qué esta restricción no pierde el plan óptimo.** Cualquier plan que use un `PICKUP`/`DROP` de un ítem irrelevante en ese momento se puede acortar quitando ese par de acciones: como ninguna operación pendiente lo necesita, quitar esas acciones no rompe ninguna precondición futura, y el plan resultante cuesta al menos 2 unidades menos. Así que un plan que use acciones irrelevantes nunca puede ser el de menor costo — el agente puede ignorarlas con total seguridad.

### Olvido de objetos muertos en M (necesario en la práctica, no sólo en teoría)

La poda de PICKUP/DROP de la sección anterior no basta por sí sola. Sigue quedando un problema: un objeto que ya es irrelevante, pero que en algún momento estuvo cargado y tuvo que soltarse para hacer espacio, puede caer en *cualquiera* de las zonas por las que pasó el robot antes de ese `DROP` forzado. M sigue registrando esa posición exacta aunque el objeto nunca vuelva a usarse — y como distintas ejecuciones del mismo plan parcial pueden forzar ese `DROP` en zonas distintas, CLOSED ve mundos "distintos" que son, para todo efecto práctico, el mismo.

Por eso, cada vez que una transición puede *crear* una entrada muerta nueva en M — se abre una puerta (su llave puede morir), se repara un panel (su herramienta o su material pueden morir), o se suelta al suelo un objeto que ya era irrelevante — el agente vuelve a aplicar la definición de `vivo(k)`/`vivo(t)`/`vivo(m)` de la sección "Relevancia" y **borra de M la posición de cualquier objeto que ya no la cumpla**, en vez de conservarla. La zona exacta donde cayó un objeto muerto deja de existir como dato: dos caminos que sólo difieren en dónde quedó tirado algo que nadie va a volver a recoger colapsan al mismo estado.

Esto es distinto de `vivo(m)` para materiales (que sí depende de la carga, porque `falta(m,s)` sube y baja al soltar y recoger). El olvido de posición sólo mira **E** (puertas y paneles, ambos monótonos): una vez que una llave o herramienta muere por esa vía, nunca puede revivir, así que borrar su posición nunca pierde información que la búsqueda vaya a necesitar después.

### `SWAP`: por qué no pierde el óptimo

Aun con el olvido de objetos muertos, cada `DROP` forzado seguía registrando en CLOSED, como nodo propio de la búsqueda, el estado intermedio "recién solté X, todavía no recogí Y" — y ese nodo hay que expandirlo por completo (recalcular `MOVE`, `RECHARGE`, `INTERACT`, …) sólo para, casi siempre, terminar generando el `PICKUP(Y)` que ya se veía venir. `SWAP(x↓, y↑)` fusiona ese `DROP(x)` con el `PICKUP(y)` que lo motivó en un único sucesor, sin pasar por ese nodo intermedio.

Es *sound* por el mismo argumento que ya justifica la poda de DROP: en cualquier plan óptimo, un `DROP` que sólo existe para liberar espacio se puede reordenar para quedar inmediatamente antes del `PICKUP` que lo necesita, sin cambiar el costo total ni violar ninguna precondición (la capacidad nunca se excede en ese punto porque, por construcción, `DROP` libera exactamente el espacio que `PICKUP` va a ocupar). Fusionar los dos pasos en un solo sucesor de búsqueda no es más que explotar ese reordenamiento: se llega al mismo estado, con el mismo costo acumulado, sin necesidad de que el estado intermedio pase por OPEN/CLOSED. Cuando un único `DROP` no libera suficiente capacidad para el `PICKUP` deseado (posible si algún ítem pesa más de 1), `SWAP` no se genera y el agente cae de vuelta al `DROP` suelto como reserva, preservando completitud.

**Evidencia empírica de por qué hacía falta.** Con el `scenario.json` de este proyecto (5 zonas, 3 puertas+llaves, 3 herramientas, 3 tipos de material, capacidad 3) UCS con sólo la poda de relevancia de PICKUP/DROP **no termina en más de 5 minutos**: aunque cada `DROP` forzado prioriza soltar lo ya irrelevante, esa posición nunca se olvida, así que las 5 zonas posibles donde pudo caer cada objeto muerto siguen multiplicando el número de mundos distintos en CLOSED. Añadiendo el olvido de M, la misma instancia resuelve en **~3 min, 1 213 413 nodos expandidos**; añadiendo además `SWAP`, en **~52 s, 355 566 nodos expandidos** — mismo plan óptimo, costo **80** en **35 pasos**. Ninguna de las dos técnicas cambia el costo encontrado, sólo cuánto tarda en encontrarse: es la diferencia entre un examen que no termina y uno que sí.

---

## Modelo de transición

```text
s  --a-->  s'     solo si a ∈ Applicable(s)
```

`Result(s, a)` es una función determinista y parcial: dado un estado y una acción aplicable, produce exactamente un estado nuevo (nunca modifica el estado recibido, siempre construye uno nuevo).

Lo que puede cambiar según el tipo de acción:

- **MOVE:** cambia P (nueva zona) y B (se descuenta el costo del corredor). C, E, M quedan igual.
- **PICKUP:** cambia C (+1 del ítem) y M (-1 del ítem en esa zona). P, B, E quedan igual.
- **DROP:** cambia C (-1 del ítem) y M (+1 del ítem en esa zona). P, B, E quedan igual.
- **INTERACT:** cambia E (según los efectos de la operación) y, si la operación consume materiales, también cambia C. Si la operación tiene costo de energía, también cambia B. P y M quedan igual.

Todo lo que una acción no menciona explícitamente se conserva sin cambios (nada se pierde "por accidente"). Después de cada transición, el estado nuevo se vuelve a poner en su forma canónica (tuplas ordenadas, sin ceros) para que la comparación de igualdad y el hash sigan funcionando correctamente contra CLOSED.

---

## Prueba de meta

```text
Goal(s) ⟺ todas las estaciones listadas en goal.stations_online están en "ONLINE"
```

La meta se revisa **únicamente sobre E** (el entorno) — concretamente, sobre el subconjunto de estaciones que el escenario marca como misión. No exige nada sobre en qué zona terminó el robot, cuánta batería le queda, ni qué lleva o dejó de llevar cargado. Las puertas y los paneles son **medios** para llegar a la meta (una puerta debe abrirse porque bloquea el camino; un panel debe repararse porque una estación lo exige como precondición para activarse), no fines en sí mismos — por eso `Goal(s)` no los menciona directamente, solo importa que las estaciones objetivo terminen `ONLINE`.

Esto es intencional: la misión se verifica contra el estado final del mundo, no contra si se ejecutó una lista de pasos predefinida. Dos planes con secuencias de acciones completamente distintas son igual de válidos si ambos dejan a E cumpliendo la condición anterior.

---

## Función de costo

```text
g(n) = Σ costo(acción_k)   para cada acción en el camino desde la raíz hasta n
```

El costo de un plan es la suma de los costos **oficiales** de cada acción tal como los define el escenario (el `cost` de cada corredor para `MOVE`, y las constantes `action_costs.pickup / drop / interact / recharge` para el resto) — no el número de pasos. Ese mismo número es, en este dominio, lo que la acción gasta de batería (ver sección de Acciones), así que `g(n)` termina siendo también el total de energía consumida a lo largo del camino, más allá de las veces que el robot recargó.

Minimizar pasos **no** es lo mismo que minimizar costo en este mundo: los corredores tienen costos distintos, así que una ruta con más saltos puede terminar siendo más barata que un atajo de un solo salto caro. `g(n)` captura eso; contar pasos no. Como todo costo es un entero positivo fijo por el escenario (nunca 0 ni negativo), dos planes solo pueden empatar en costo total si por casualidad suman lo mismo — el agente no fuerza una preferencia adicional por menos pasos en ese caso, porque el contrato no la pide: "mejor plan" aquí significa estrictamente costo mínimo.

---

## Estrategia de búsqueda

Se elige **Uniform Cost Search (UCS) con Graph Search** (lista CLOSED), vista en clase.

**Por qué no BFS.** BFS encuentra la solución con menos aristas (menos acciones), no la de menor costo. Como los corredores tienen costos distintos, la solución con menos pasos puede no ser la más barata en energía — BFS solo es óptimo cuando todas las acciones cuestan lo mismo, y aquí no es el caso.

**Por qué no DFS.** DFS no garantiza ni completitud (puede quedarse dando vueltas en un ciclo de corredores de ida y vuelta si no se controla explícitamente) ni optimalidad (se compromete con la primera solución que encuentra, sin comparar costos entre ramas).

**Por qué UCS funciona aquí:**

- **Completitud:** sí, porque el factor de ramificación es finito y todo costo de acción es no negativo (§2.6 del enunciado). En el escenario de ejemplo además es siempre ≥ 1 (los `action_costs` y los costos de corredor son enteros positivos), lo que da un margen `ε ≥ 1` y descarta que UCS se quede intentando acciones de costo 0 indefinidamente.
- **Optimalidad:** sí, porque UCS siempre expande el nodo de frontera con menor `g` (usando una cola de prioridad) y **comprueba la meta al extraer el nodo de la frontera, no al generarlo**. Si se comprobara al generar, se podría aceptar un camino a la meta que no es el más barato, porque en ese momento todavía podría haber otro nodo en la frontera con menor `g` que también llegue a la meta.
- **Costo de camino:** garantizado óptimo por la razón anterior.
- **Tiempo y espacio:** en el peor caso son exponenciales en la profundidad de la solución, pero el factor de ramificación real `b` **no depende del tamaño del mapa** — depende de cuántos sucesores genera `Applicable(s)` en cada estado. El peligro real no es el número de zonas, es cuántos `PICKUP`/`DROP` se generan por estado. Con la poda descrita en la sección de Acciones, `b` queda acotado por: los corredores que salen de la zona actual, las operaciones aplicables en esa zona, y como mucho la capacidad de carga (para el caso límite de `DROP`) — nunca por la cantidad de objetos del escenario multiplicada por la cantidad de zonas.
- **Cuándo se rompen las garantías:** si apareciera algún costo 0 o negativo, UCS podría dejar de ser óptimo o incluso no terminar (necesitaría un algoritmo tipo Bellman-Ford); si los estados no se canonicalizan bien (por ejemplo, si el orden de inserción de un diccionario cambiara el hash), CLOSED no reconocería estados repetidos y la búsqueda podría no terminar nunca en la práctica; si la frontera (OPEN) no se vaciara correctamente o se dejaran nodos sin marcar como cerrados, se podría reexpandir indefinidamente el mismo estado.

Graph Search exige comparar cada nodo nuevo contra una lista CLOSED de estados ya resueltos, usando la forma **canónica** del estado (la firma `⟨P,C,E,M⟩` descrita arriba). Así, si dos caminos distintos llegan exactamente al mismo mundo físico, el segundo se descarta en vez de volver a expandirse — es lo que evita reexplorar la misma situación una y otra vez, incluso si el mapa tiene ciclos (ida y vuelta entre zonas).

### Batería como recurso

La batería sí es parte del estado físico (sección 2.1 del enunciado), pero eso **no** obliga a tratar cada nivel de batería como si fuera un mundo distinto — si se hiciera así, UCS podría intentar explorar todos los "paseos" posibles que solo gastan y recargan batería sin llegar a ningún lado nuevo, hasta agotar memoria.

La solución es una regla de **dominancia**: si dos caminos llegan a la **misma** configuración del mundo (misma zona, misma carga, mismo entorno, mismo mapa de ítems en el piso) y uno de ellos lo logra con **costo acumulado menor o igual** y **batería restante mayor o igual**, el segundo camino nunca puede producir una continuación mejor que el primero — está dominado y se puede descartar sin riesgo de perder el plan óptimo.

```text
camino 1 domina a camino 2 (misma configuración del mundo)
  si y solo si
g1 ≤ g2   y   batería1 ≥ batería2
```

Si ninguno domina al otro (por ejemplo, un camino es más barato pero deja menos batería que el otro), **se conservan los dos**, porque el más caro podría ser el único que deja batería suficiente para terminar la misión. Por eso CLOSED no guarda un solo "mejor" registro por configuración del mundo, sino la lista de puntos (costo, batería) que no están dominados entre sí para esa configuración, y cualquier nodo nuevo se compara contra esa lista antes de decidir si se descarta o se explora.

---

## Formulación y tamaño del espacio (obligatorio)

**1. ¿Por qué «5 zonas, ~10 objetos, capacidad 3» puede generar millones de nodos en un UCS ingenuo?**

Porque el tamaño del espacio de estados no depende solo del número de zonas, sino de todas las combinaciones posibles de "quién lleva qué" y "qué quedó tirado dónde". Si el agente permite `DROP` de cualquier objeto en cualquier momento, cada uno de los ~10 objetos puede terminar en cualquiera de las 5 zonas o dentro de la carga del robot — eso son del orden de 6 posiciones posibles por objeto (5 zonas + "cargado"), elevado a la cantidad de objetos. Con 10 objetos eso ya son del orden de 6¹⁰ (más de 60 millones) combinaciones de "dónde está cada cosa", multiplicado además por las combinaciones de posición del robot, batería y entorno. El mapa sigue siendo pequeño; el espacio de estados que un agente mal formulado terminaría explorando no lo es.

**2. ¿Qué papel tiene `DROP` en esa explosión?**

`DROP` es la acción que introduce esa combinatoria: es la única forma en que un objeto puede "moverse" a una zona distinta de donde empezó o de donde lo llevó el robot. Si se genera sin restricciones, por cada estado con carga se abren tantas ramas como objetos cargados, y como `PICKUP` puede deshacer un `DROP` (y viceversa), también aparecen ciclos `DROP ↔ PICKUP` que obligan a Graph Search a hacer trabajo extra solo para descartarlos, en vez de que esas ramas nunca se generen.

**3. ¿Qué podas o abstracciones aplicó y por qué no pierden el óptimo (sound)?**

Se aplicaron cuatro, las cuatro descritas en la sección de Acciones y en "Olvido de objetos muertos en M" más arriba:

- `PICKUP(i)` solo se genera si `i` es relevante (alguna operación pendiente lo necesita).
- `DROP(i)` solo se genera cuando la capacidad está llena y hace falta espacio para recoger algo relevante; entre los cargados, se prioriza soltar los que ya son irrelevantes.
- La posición en M de un objeto que acaba de morir (puerta que abrió, panel que se reparó, objeto irrelevante recién soltado) se olvida de inmediato, en vez de conservarse.
- `SWAP(x↓, y↑)` fusiona el `DROP` forzado con el `PICKUP` que lo motivó en un solo sucesor de búsqueda, para no registrar en CLOSED el estado intermedio.

Las cuatro son *sound* (no pierden el óptimo) por el mismo argumento: cualquier plan que use un `PICKUP`/`DROP` de un ítem irrelevante, o que cargue con la posición de algo que ya murió, o que separe un `DROP` de rescate del `PICKUP` que lo justifica, se puede reescribir sin esas acciones o con ellas fusionadas sin romper ninguna precondición futura y sin aumentar el costo — así que un plan de costo mínimo nunca las necesita tal cual, y el agente puede podarlas/fusionarlas sin arriesgar la optimalidad.

**4. ¿Por qué no es solución subir la capacidad, bajar las estaciones o ignorar la batería?**

Porque esos valores son **parámetros del escenario** (`scenario.json`), no parte del diseño del agente. Subir la capacidad de carga solo pospone el problema a una instancia con más objetos o menos capacidad; bajar el número de estaciones de recarga o quitar restricciones de batería cambia las reglas del mundo, no la formulación de la búsqueda. El profesor probará el agente con **otras instancias** del mismo tipo de escenario, con distintos mapas, capacidades y niveles de batería — si la solución dependiera de los números concretos de `scenario.json` en vez de depender de cómo se define `Applicable(s)`, dejaría de funcionar apenas cambiara la instancia. Las podas anteriores, en cambio, funcionan igual sin importar cuántas zonas, objetos o cuánta batería tenga el escenario, porque no dependen de esos números: dependen de si un ítem todavía puede habilitar alguna operación pendiente.

**Evidencia empírica (no solo teoría).** Con el `scenario.json` real de este proyecto (5 zonas, 3 puertas+llaves, 3 herramientas, 3 tipos de material, capacidad 3 — 9 identidades recogibles en total) se midieron las tres formulaciones sucesivas:

| Formulación | Nodos expandidos | Tiempo | Costo |
|---|---|---|---|
| Sólo relevancia de `PICKUP`/`DROP` (sin olvidar M) | — | no termina en 5 min | — |
| + olvido de posición de objetos muertos en M | 1 213 413 | ~3 min | **80** |
| + `SWAP` | 355 566 | ~52 s | **80** |

El costo óptimo no cambia entre la segunda y la tercera fila — ninguna de las dos podas adicionales sacrifica optimalidad, tal como se demuestra arriba — sólo cambia cuánto tarda la búsqueda en encontrarlo. La primera fila es la prueba de que la relevancia de `PICKUP`/`DROP` sola **no alcanza** en este dominio: el cuello de botella real (CONTRATO.md §6) es dónde queda cada objeto ya inútil, no cuántos objetos hay para recoger.
