# Model Builder 4.2 — Bilingual presentation script

This is the spoken script for the **39-slide English deck**. The English text is what to say; the Spanish text gives its meaning so you can study it. Do not try to memorize every word. Memorize the **anchor** on each slide and use the script to practise the complete explanation.

**Recommended duration:** 28–32 minutes plus questions. For the canonical 20-minute version, present slides 1, 2, 4, 5, 7, 8, 13, 17, 19, 22, 23, 26–32, 34 and 37–39; keep the remaining slides as backup.

**Core claim for the entire presentation:**

> **EN:** Model Builder implements a traceable and reproducible workflow for supported DIN 6885 geometry, DIN 6892 analytical and research calculations, Abaqus model preparation, evidence capture and reporting. It is not DIN certification, and physical acceptance remains an engineering responsibility.
>
> **ES:** Model Builder implementa un flujo trazable y reproducible para la geometría DIN 6885 soportada, cálculos analíticos y de investigación DIN 6892, preparación del modelo Abaqus, captura de evidencia e informes. No es una certificación DIN y la aceptación física sigue siendo una responsabilidad de ingeniería.

---

## Slide 1 — Model Builder 4.2

**Time:** 25 seconds  
**Anchor:** Traceable automation, not just geometry.

**Say in English**

Good morning. I will present Model Builder 4.2, a traceable workflow for shaft–hub key joints in Abaqus 2022. The system connects DIN 6885 geometry, DIN 6892 evaluation methods, FVA research workflows, model generation, evidence capture and reporting. The central idea is not only to create a model, but to preserve enough evidence to explain exactly how it was created.

**Significado en español**

Buenos días. Voy a presentar Model Builder 4.2, un flujo trazable para uniones eje–cubo con chaveta en Abaqus 2022. Conecta geometría DIN 6885, métodos DIN 6892, investigación FVA, generación del modelo, evidencia e informes. La idea central no es sólo crear un modelo, sino conservar evidencia suficiente para explicar exactamente cómo se creó.

**Transition**

> To understand why that matters, I will start with the problem the tool was designed to solve.

---

## Slide 2 — The problem

**Time:** 35 seconds  
**Anchor:** Repeatability was the real problem.

**Say in English**

The difficult part was not drawing one keyway model. The difficult part was repeating the same engineering decisions consistently. The DIN row could be entered differently, the mesh could depend on the author, and the final result might not record the software version or assumptions. Model Builder addresses those three risks: manual repetition, subjective meshing and missing audit evidence.

**Significado en español**

Lo difícil no era dibujar un modelo. Lo difícil era repetir las mismas decisiones de ingeniería de manera consistente. La fila DIN podía introducirse diferente, la malla dependía del autor y el resultado podía no registrar versión o hipótesis. Model Builder aborda esos tres riesgos: repetición manual, malla subjetiva y falta de evidencia.

**Transition**

> The result is one controlled toolchain rather than a collection of disconnected scripts.

---

## Slide 3 — What it is

**Time:** 40 seconds  
**Anchor:** One tool from standard data to report.

**Say in English**

The project contains fourteen Python modules, twenty-six explicit DIN 6885 diameter rows, eight mesh policies and four DIN 6892 evaluation paths. It also supports Spanish, English and German through catalogues with six hundred and fifty keys at parity. These numbers are not marketing estimates: they are counts from the current code. The objective is one workflow from normative input to model, audit and report.

**Significado en español**

El proyecto tiene catorce módulos Python, veintiséis filas DIN 6885, ocho políticas de malla y cuatro rutas DIN 6892. Soporta español, inglés y alemán con 650 claves iguales. No son estimaciones comerciales, sino conteos del código actual. El objetivo es un flujo desde el dato normativo hasta modelo, auditoría e informe.

**Transition**

> That workflow is split across two Python runtimes because Abaqus 2022 has its own kernel environment.

---

## Slide 4 — Architecture

**Time:** 55 seconds  
**Anchor:** Two runtimes, one shared calculation core.

**Say in English**

The desktop side runs in Python 3 and owns the interface, project workspace, reporting, CSV post-processing and MATLAB integration. Abaqus 2022 executes the kernel-side builder under Python 2.7. Between them, `keyjoint_core.py` and `din6892_methods.py` are shared, dual-compatible modules. This is important because geometry tables and formulas are not copied into two implementations. Both sides use the same source of truth. The desktop can open and perform pure calculations without Abaqus, while actual CAE construction requires the local Abaqus installation and licence.

**Significado en español**

El escritorio usa Python 3 para interfaz, proyecto, informes, CSV y MATLAB. Abaqus 2022 ejecuta el constructor con Python 2.7. Entre ambos, `keyjoint_core.py` y `din6892_methods.py` son compartidos y compatibles con los dos. Así no se duplican tablas ni fórmulas. La interfaz puede abrirse sin Abaqus, pero construir el CAE necesita Abaqus y su licencia.

**Transition**

> From the user's point of view, this architecture is presented as six tabs in the order decisions are made.

---

## Slide 5 — How it is used

**Time:** 25 seconds  
**Anchor:** Decisions happen in a controlled order.

**Say in English**

The interface follows the engineering sequence: define the project, define DIN geometry, choose mesh and materials, choose whether analysis is required, configure DIN 6892 or FVA evidence, and only then run and review the evidence. This order prevents execution from becoming the first step.

**Significado en español**

La interfaz sigue el orden de ingeniería: proyecto, geometría DIN, malla y materiales, análisis, DIN 6892/FVA y finalmente ejecución y evidencia. El objetivo es evitar que ejecutar sea el primer paso.

**Transition**

> I will now walk through those six tabs using captures of the real application.

---

## Slide 6 — Tab 1: Project

**Time:** 35 seconds  
**Anchor:** Identity and environment are part of the result.

**Say in English**

The Project tab records the project name, model name, author and language. That language is persisted, so the report is generated in the project's language rather than the language of the next user. The Abaqus launcher can be detected without being executed, and the project root is chosen before any run starts. These values become part of `project.json`.

**Significado en español**

La pestaña Proyecto registra nombre, modelo, autor e idioma. El idioma persiste y controla el informe. El lanzador de Abaqus puede detectarse sin ejecutarse y la raíz se elige antes de correr. Todo queda en `project.json`.

**Transition**

> Once the project identity is fixed, the next step is the normative geometry.

---

## Slide 7 — Tab 2: DIN geometry

**Time:** 45 seconds  
**Anchor:** Few inputs, many derived values.

**Say in English**

The left side contains the independent choices. The right side is derived live from the shared core: the exact DIN row, key dimensions, standard length, hub geometry, radii, mesh plan and validation issues. For the D40 default, the applicable band is thirty-eight less than `d1`, up to and including forty-four millimetres, giving a twelve by eight millimetre key. A green NORMATIVE badge means the geometry is inside the implemented DIN envelope; it does not mean the complete joint is certified.

**Significado en español**

A la izquierda están las decisiones independientes. A la derecha se deriva en vivo la fila DIN, dimensiones, longitud, cubo, radios, plan de malla y avisos. Para D40 la banda es 38 < d1 ≤ 44 y la chaveta es 12×8. NORMATIVE significa dentro del sobre implementado, no unión certificada.

**Transition**

> The geometry determines the local scale, but the mesh policy remains an explicit engineering choice.

---

## Slide 8 — Tab 3: Mesh and materials

**Time:** 50 seconds  
**Anchor:** Automatic does not mean undocumented.

**Say in English**

The mesh template is selected by name, and AUTO mode compares complete candidates per part. A seed of zero means automatic, but the rule depends on notch refinement. With the notch band active, which is the default, the shaft uses `D/16`, the hub uses `d_a/40`, and the key always uses `b/20`. Without notch refinement the shaft and hub rules become `D/32` and `d_a/80`. The quick pressure result on this tab is deliberately labelled CORE-SCREENING. It is a plausibility check, not DIN 6892 Method B.

**Significado en español**

La plantilla se elige explícitamente y AUTO compara candidatos por pieza. Semilla cero significa automática, pero la regla depende del refinamiento: por defecto D/16 en eje, d_a/40 en cubo y b/20 en chaveta; sin refinamiento D/32 y d_a/80. La presión rápida es CORE-SCREENING, no Método B.

**Transition**

> Mesh preparation and solver analysis are intentionally separated.

---

## Slide 9 — Tab 4: Analysis

**Time:** 35 seconds  
**Anchor:** Build, create job and submit are separate decisions.

**Say in English**

Analysis is optional and disabled by default. The tool can build, mesh, audit and document a model without solving it. If analysis is enabled, it creates contact, a static TORSION step and a moment at the shaft reference point. Creating the Abaqus job and submitting it are two separate controls. The convergence study is also separate and writes its own CSV; it is mesh-quality evidence, not automatically a stress-convergence proof.

**Significado en español**

El análisis es opcional. Se puede construir, mallar, auditar y documentar sin resolver. Si se activa, crea contacto, paso TORSION y momento. Crear el job y enviarlo son decisiones distintas. El estudio de malla da evidencia de calidad, no prueba automáticamente convergencia de tensiones.

**Transition**

> The fifth tab contains the analytical methods and the research evidence settings.

---

## Slide 10 — Tab 5: DIN 6892 / FVA

**Time:** 55 seconds  
**Anchor:** Method, factors and evidence status are explicit.

**Say in English**

The requested method is explicit. Licensed or case-specific factors that cannot be resolved from the available context are not silently invented. In particular, a neutral `K_lambda` remains visible and the result is labelled PROVISIONAL_FACTORS. `N_W` means load-direction reversals, not total cycles. For a pulsating load with non-negative load ratio, the same flank remains loaded, so `N_W` is zero and `f_W` is one. Method A is different: it assesses external evidence from a solved and unloaded ODB; it does not create that solution in the analytical tab.

**Significado en español**

El método es explícito. Los factores con licencia o específicos del caso no se inventan. `K_lambda` queda visible como neutro y el resultado es provisional. `N_W` son inversiones de dirección, no ciclos. En carga pulsante vale cero y `f_W=1`. Método A evalúa evidencia externa de un ODB resuelto y descargado.

**Transition**

> The last tab turns execution into an observable process rather than a black box.

---

## Slide 11 — Tab 6: Run and evidence

**Time:** 40 seconds  
**Anchor:** The run is observable and contained.

**Say in English**

The Abaqus output is streamed both to the interface and to `logs/abaqus.log`, with the command and working directory recorded. Artifacts are listed with size and evidence badge. The subprocess runs inside `jobs/`, so solver scratch files do not appear next to the executable. If the user cancels, the process tree is terminated and the project is marked CANCELLED, not completed.

**Significado en español**

La salida de Abaqus va a la interfaz y al log, con comando y directorio. Los artefactos muestran tamaño y badge. El solver trabaja dentro de `jobs/`. Si se cancela, se mata el árbol de procesos y el proyecto queda CANCELLED.

**Transition**

> Before the run can start, validation has the authority to block it.

---

## Slide 12 — Quality control

**Time:** 40 seconds  
**Anchor:** Errors block; warnings remain visible.

**Say in English**

Every issue has a stable code, a canonical message and a translated presentation. Errors block the build before Abaqus is touched. Warnings remain in the audit. The default form currently has zero errors and three warnings: a licensed factor is still neutral, equation 9 may be optimistic, and a high axial aspect ratio is expected near the notch. The dialog reports the count; the detailed codes remain in the audit.

**Significado en español**

Cada issue tiene código estable, mensaje canónico y traducción. Los errores bloquean antes de Abaqus; las advertencias quedan en auditoría. Por defecto hay cero errores y tres advertencias: factor neutro, ecuación 9 optimista y relación de aspecto axial alta en la entalla.

**Transition**

> With those controls in place, this is the complete path from a click to archived evidence.

---

## Slide 13 — Execution flow

**Time:** 50 seconds  
**Anchor:** Ten stages and two hard gates.

**Say in English**

The form is converted to parameters, normalized, derived and validated. A workspace is created and Abaqus is launched with the parameter file. Inside the kernel, the tool creates geometry, mesh and optional analysis, then writes the audit, screenshots, CAE model and build result. Back in Python 3, the report is generated. There are two hard gates: invalid input never reaches Abaqus, and a project is not declared sound if required artifacts or mesh-quality evidence are missing.

**Significado en español**

Formulario → parámetros → normalización → derivación → validación → proyecto → Abaqus → geometría/malla/análisis → auditoría/evidencia → informe. Hay dos puertas: un error no llega a Abaqus y un proyecto incompleto no se declara correcto.

**Transition**

> The directory structure is part of that contract.

---

## Slide 14 — What stays on disk

**Time:** 45 seconds  
**Anchor:** Seven folders separate intention, realization and evidence.

**Say in English**

Each run receives seven folders. `input` stores what was requested. `generated` stores the audit and build result. `model` stores the CAE database. `jobs` contains solver output. `screenshots` contains visual evidence, `reports` contains the human- and machine-readable report, and `logs` contains the complete run log. `project.json` records identity, schema, status and registered artifacts. This separation prevents old or unrelated files from being mistaken for the current result.

**Significado en español**

Cada ejecución tiene siete carpetas: entrada solicitada, resultados generados, CAE, solver, capturas, informes y logs. `project.json` registra identidad, esquema, estado y artefactos. Así no se mezclan archivos viejos con el resultado actual.

**Transition**

> The user does not always start from a blank configuration; the tool provides controlled presets.

---

## Slide 15 — Starting points

**Time:** 40 seconds  
**Anchor:** A preset is a starting point, not a bypass.

**Say in English**

There are fifteen presets: geometry and analysis cases, one entry for each mesh policy and two FVA research setups. Applying a preset only changes parameters. The complete result is normalized, derived and validated again, so the preset cannot bypass the same gates as manual input. Configurations can also be saved and loaded as JSON for reproducibility.

**Significado en español**

Hay quince presets de geometría, análisis, malla e investigación FVA. Un preset sólo modifica parámetros: después se normaliza, deriva y valida igual. No salta controles. Las configuraciones se guardan y cargan en JSON.

**Transition**

> Those presets operate inside a clearly declared design space.

---

## Slide 16 — Design space

**Time:** 55 seconds  
**Anchor:** Supported, refused and overridden are different states.

**Say in English**

The implemented key forms are A, B and AB. Forms C through J are explicitly refused because required hole or chamfer dimensions are not implemented. The hub may be cylindrical or tapered; tapered mode adds a bushing. The normative diameter range is `6 < d1 <= 500 millimetres`, with no table extrapolation. Linear and quadratic element families are supported. `C3D8R` is accepted only as an explicit legacy choice and raises a warning. Finally, user override can keep a non-normative choice visible, but it does not convert that choice into normative evidence.

**Significado en español**

Se soportan formas A, B y AB; C–J se rechazan explícitamente. El cubo puede ser cilíndrico o cónico con casquillo. Rango 6 < d1 ≤ 500 sin extrapolar. Elementos lineales o cuadráticos; C3D8R sólo heredado explícito y con warning. Un override no se vuelve normativo.

**Transition**

> This is what the resulting solid model looks like.

---

## Slide 17 — The result

**Time:** 35 seconds  
**Anchor:** Solid geometry and evidence, without overclaiming matching.

**Say in English**

The regular builder creates independent solid parts for shaft, key and hub; tapered mode can add a bushing. This evidence shows a hexahedral mesh. Exact interface matching is not inferred from an image. In the specialized Method A workflow it must be verified after meshing by comparing actual node coordinates. The screenshot itself is generated by the engine and stored as evidence.

**Significado en español**

El constructor crea sólidos independientes para eje, chaveta y cubo, y puede añadir casquillo. La imagen muestra malla hexaédrica, pero no prueba coincidencia exacta. Método A la comprueba comparando coordenadas reales. La captura la guarda el motor como evidencia.

**Transition**

> The mesh is refined where the stress gradient is expected to be highest.

---

## Slide 18 — The detail that matters

**Time:** 40 seconds  
**Anchor:** Local refinement at the keyway root.

**Say in English**

The keyway root is a critical stress-concentration area. Rather than making the entire model uniformly fine, the builder partitions a refinement band around the notch and controls the fillet arc resolution. The audit records whether the requested arc and band conditions were achieved. A named `NOTCH_SHAFT` element set keeps later stress queries focused on the relevant region instead of an unrelated hot spot.

**Significado en español**

El fondo del chavetero concentra tensiones. En vez de refinar todo, se crea una banda local y se controla el arco del radio. La auditoría registra el cumplimiento y el set `NOTCH_SHAFT` limita la consulta a la zona relevante.

**Transition**

> Local refinement is one part of a broader mesh policy.

---

## Slide 19 — Mesh policy

**Time:** 50 seconds  
**Anchor:** Eight policies with explicit gates.

**Say in English**

The current code defines eight mesh templates. They differ in topology requirement, element order, number of attempts, minimum quality score, minimum hex percentage, maximum aspect ratio and element budget. `HEX_CERTIFIED`, the default, requires quadratic `C3D20R`, one hundred percent hexahedra, zero repairs and zero warnings. If it cannot satisfy those gates, the build fails rather than silently falling back to tetrahedra. Older documentation that says six templates is stale; the current implementation has eight.

**Significado en español**

El código actual define ocho plantillas con requisitos diferentes. `HEX_CERTIFIED` exige C3D20R, 100% hexaedros, cero reparaciones y cero warnings. Si no cumple, falla. La referencia antigua a seis está obsoleta.

**Transition**

> A template defines the policy; the next step is choosing the best candidate for each part.

---

## Slide 20 — Mesh selection

**Time:** 45 seconds  
**Anchor:** Candidate order is part-specific; the global result is the worst part.

**Say in English**

Candidate order is part-specific. Shaft and key begin with structured hex, while hub and bushing begin with medial sweep. Each candidate follows the same loop: partition, seed the fillet, apply controls, mesh, repair where allowed, measure and score. Hard gates are applied before deterministic ranking. The global verdict is the worst part, never the average, because one unacceptable component cannot be hidden by three good ones.

**Significado en español**

El orden de candidatos depende de la pieza. Todos pasan por partición, siembra, controles, malla, reparación permitida y puntuación. Las puertas duras van antes del ranking. El veredicto global es la peor pieza, no la media.

**Transition**

> When the user requests analysis, the builder adds a controlled mechanical setup.

---

## Slide 21 — Analysis setup

**Time:** 50 seconds  
**Anchor:** The regular analysis is explicit and optional.

**Say in English**

The optional regular analysis creates general contact with hard normal behavior and optional penalty friction. A reference point and kinematic coupling apply the torque at the shaft end. The user chooses whether the hub is held at its outer diameter or at its end faces. The step is static TORSION with optional geometric nonlinearity and stabilization. Requested field output includes stress, displacement, strain, reaction force and contact variables, while the reference-point history stores rotation and reaction moment. Job creation and solver submission remain separate.

**Significado en español**

El análisis opcional crea contacto general, punto de referencia, acoplamiento y par. El usuario elige la sujeción del cubo. El paso TORSION puede usar no linealidad y estabilización. Se guardan campos y la historia de giro/momento. Crear job y resolver siguen separados.

**Transition**

> Every value produced by these stages carries an evidence classification.

---

## Slide 22 — Traceability badges

**Time:** 45 seconds  
**Anchor:** Evidence classes prevent promotion by appearance.

**Say in English**

The badges distinguish where a value comes from. NORMATIVE means transcribed standard data within implemented scope. DIN-METHOD identifies a calculation method. FVA-RESEARCH and LITERATURE are not promoted to normative status. CORE-SCREENING is a plausibility check. USER-INPUT and USER-OVERRIDE remain visible, and NOT-IMPLEMENTED prevents a visible option from being mistaken for a supported one. Successful execution never changes the evidence class.

**Significado en español**

Los badges distinguen procedencia: normativo, método DIN, investigación FVA, literatura, screening, dato de usuario, override o no implementado. Ejecutar con éxito nunca cambia la clase de evidencia.

**Transition**

> The first normative data source is the explicit DIN 6885 table.

---

## Slide 23 — The normative datum

**Time:** 55 seconds  
**Anchor:** Exact row or error; no extrapolation.

**Say in English**

DIN 6885 geometry is represented by twenty-six explicit diameter rows, thirty-four standard lengths and seven radius bands. The interval convention is strict lower bound and inclusive upper bound. The function never clamps or extrapolates. For D40, it selects the thirty-eight-to-forty-four band and returns a twelve by eight key, `t1=5.0`, `t2=3.3` and the stated radius ranges. The key chamfer is not from that table; it is a user parameter and is reported as such.

**Significado en español**

DIN 6885 se representa con 26 filas, 34 longitudes y 7 bandas de radios. El intervalo tiene límite inferior estricto y superior incluido. No interpola. Para D40 devuelve 12×8, t1=5, t2=3,3 y radios. El chaflán es dato de usuario.

**Transition**

> After construction, the audit records both the plan and what Abaqus actually produced.

---

## Slide 24 — The audit

**Time:** 50 seconds  
**Anchor:** Requested, derived and realized are kept separate.

**Say in English**

`PARAM_BUILD_AUDIT` is written in text for review and JSON for automation. It records the software and schema identity, hashes of runtime inputs, derived geometry, validation issues, mesh plan, per-part realized metrics, sets, surfaces and analysis state. It returns an OK or CHECK verdict, and that verdict is mirrored into the build result. Most importantly, it allows requested, derived and realized states to be compared rather than assumed to be equal.

**Significado en español**

La auditoría existe en texto y JSON. Registra versión, esquema, hashes, geometría, issues, plan y malla real por pieza, sets, superficies y análisis. Devuelve OK o CHECK y compara solicitado, derivado y realizado.

**Transition**

> That evidence is transformed into the final deliverable.

---

## Slide 25 — The deliverable

**Time:** 45 seconds  
**Anchor:** The report is part of the engineering product.

**Say in English**

The report has ten sections covering provenance, scope, geometry, DIN 6892, standards, validation, mesh policy, checks, evidence, deliverables and limitations. It produces `report.tex`, optional `report.pdf`, machine-readable `report_data.json` and a LaTeX build log. If LaTeX is not installed, the source and data are still written and the model build does not fail for that environmental reason. The report is generated for review and signature; the software does not implement a digital-signature workflow.

**Significado en español**

El informe cubre procedencia, alcance, geometría, DIN 6892, normas, validación, malla, checks, evidencia, entregables y limitaciones. Genera TEX, PDF opcional, JSON y log. Sin LaTeX conserva TEX/JSON. El PDF es para revisión y firma; el programa no firma digitalmente.

**Transition**

> The load-capacity section compares four paths with different evidence status.

---

## Slide 26 — Load capacity methods

**Time:** 60 seconds  
**Anchor:** Four IDs, but not four equivalent authorities.

**Say in English**

The four method identifiers are preliminary Method C, current DIN Method B, the FVA 2025 Method B reformulation and Method A by finite-element opening volume. Current B is the analytical DIN reference in this implementation. Method C is preliminary sizing and can solve the inverse length problem. The FVA B reformulation is always marked research diagnostic. Method A evaluates external solved evidence and requires at least ten cycles plus an unloaded frame and provenance checks. These outputs must not be presented as equivalent authorities.

**Significado en español**

Hay cuatro identificadores: C preliminar, B vigente, B FVA 2025 y A por volumen de apertura. B vigente es la referencia analítica. C dimensiona preliminarmente. B FVA es diagnóstico de investigación. A evalúa evidencia externa con mínimo diez ciclos, descarga y procedencia. No tienen la misma autoridad.

**Transition**

> The default D40 case illustrates how different those roles are.

---

## Slide 27 — Results

**Time:** 55 seconds  
**Anchor:** 999.18 is reproducible but provisional, not approved capacity.

**Say in English**

For the bundled D40 case, Method C gives 572.51 newton-metres, current Method B gives 999.18, and the FVA research reformulation gives 2,464.87. A fully alternating loading case reduces current B to 795.56. The governing current-B component is the hub. The 999.18 value is a software golden and a reproducible analytical result, but it is not an approved capacity: `K_lambda` remains provisional and equation 9 is still open.

**Significado en español**

Para D40, C da 572,51 N·m, B vigente 999,18, B FVA 2464,87 y el alternante 795,56. Gobierna el cubo. 999,18 es un resultado reproducible y golden del software, pero no capacidad aprobada: K_lambda es provisional y la ecuación 9 sigue abierta.

**Transition**

> The first correction explains why the hub now governs.

---

## Slide 28 — Correction 1: hub bearing depth

**Time:** 60 seconds  
**Anchor:** Each component must use its own flank depth.

**Say in English**

The earlier calculation credited every component with the shaft effective depth `t1tr`. DIN 6892 requires the shaft pressure over `l_tr times t1tr` and the hub pressure over `l_tr times t2tr`. In the D40 case, `t1tr` is 5.141 millimetres while `t2tr` is 3.141. Using the larger shaft depth on the hub overstated the credited hub bearing area by 63.7 percent. This is one of two corrections: applying the hub-depth fix while retaining the old reversal factor gives 795.56 newton-metres; correcting the reversal interpretation then raises the current hub-governed result to 999.18. Therefore, 1,302.05 to 999.18 is the combined net effect of both corrections. The key uses the smaller mating depth.

**Significado en español**

Antes todos usaban t1tr del eje. DIN 6892 exige t1tr para eje y t2tr para cubo. En D40 son 5,141 y 3,141 mm; usar el mayor sobrestimaba el área del cubo 63,7%. Es una de dos correcciones: corregir sólo la profundidad manteniendo el f_W antiguo da 795,56 N·m; corregir después la interpretación de inversiones eleva el resultado actual, gobernado por el cubo, a 999,18. Por tanto, 1302,05→999,18 es el efecto neto conjunto. La chaveta usa el menor.

**Transition**

> The second correction is about what equation 3 counts.

---

## Slide 29 — Correction 2: load reversals

**Time:** 55 seconds  
**Anchor:** `N_W` is reversals, not cycles.

**Say in English**

The load-reversal factor was previously driven by total cycle count. Equation 3 uses `N_W`, the number of load-direction reversals: the additional damage from alternating between both flanks. A pulsating torque with non-negative load ratio stays on one flank, so `N_W=0` and `f_W=1`. For ten thousand fully alternating reversals, `f_W` is approximately 0.796 and the allowable drops to 795.56 newton-metres. The derivation from load ratio is now explicit and reported.

**Significado en español**

Antes f_W usaba ciclos totales. La ecuación 3 usa inversiones de dirección entre flancos. En carga pulsante N_W=0 y f_W=1. En 10.000 inversiones alternantes f_W≈0,796 y el par baja a 795,56. La deducción desde R ahora se reporta.

**Transition**

> One independent question remains unresolved: the sign convention in equation 9.

---

## Slide 30 — Open finding: equation 9

**Time:** 65 seconds  
**Anchor:** Report both values; do not overrule the licensed standard.

**Say in English**

As transcribed, equation 9 adds the chord correction and returns `t1tr=5.141 millimetres`, larger than the nominal shaft flank depth `t1=5.0`. Independent convex-shaft geometry subtracts that correction and gives 2.759 millimetres. That is a 46.35 percent spread. The code therefore reports the literal, geometric and conservative policies and raises a warning. I have not declared one sign to be the DIN answer because the licensed text and its datum must settle that question. This is an open engineering decision, not a hidden correction.

**Significado en español**

La transcripción suma la corrección y da t1tr=5,141, mayor que t1=5. La geometría convexa la resta y da 2,759: diferencia 46,35%. El código ofrece política literal, geométrica y conservadora y avisa. No se declara cuál es DIN sin revisar texto y datum con licencia.

**Transition**

> Method A follows a completely different evidence path and does not resolve this by itself.

---

## Slide 31 — Method A evidence chain

**Time:** 65 seconds  
**Anchor:** Model Builder assesses evidence; it does not manufacture a valid ODB.

**Say in English**

Method A begins with an externally solved ODB containing at least ten cycles and an identified unloaded frame. The extractor pairs left and right keyway nodes using undeformed coordinates and calculates permanent opening. It writes the canonical columns `x_mm`, `z_mm` and `opening_um`. The Python post-processor integrates that grid, checks coverage within two percent, verifies provenance and evaluates relative opening volume against `v_crit=0.5`. There are eleven visible checks; six can prevent the result from being declared complete. A CSV import alone is not proof of convergence, equilibrium, contact quality or fatigue acceptance.

**Significado en español**

Método A parte de un ODB externo resuelto con mínimo diez ciclos y frame descargado. Empareja nodos por coordenadas sin deformar, calcula apertura y escribe CSV. Python integra, comprueba cobertura 2%, procedencia y criterio v_crit=0,5. Hay 11 checks, 6 con veto. Un CSV solo no prueba convergencia, equilibrio, contacto ni fatiga.

**Transition**

> MATLAB is optional and sits after that authoritative Python assessment.

---

## Slide 32 — MATLAB numerical cross-check

**Time:** 65 seconds  
**Anchor:** Python is authoritative; MATLAB checks numerical agreement.

**Say in English**

The MATLAB companion has three modes. OFF changes nothing. EXPORT creates a deterministic bundle without running MATLAB. RUN exports and then invokes MATLAB using an argument list, `shell=False` and a finite timeout. The bundle contains the canonical CSV, calculation inputs, the authoritative Python result, generated MATLAB source and a manifest with SHA-256 for each file. MATLAB repeats the numerical integration and criterion. Results are compared with absolute tolerance `1e-10` and relative tolerance `1e-9`. If MATLAB disagrees, the discrepancy is reported; Python is never overwritten. This is a numerical cross-check, not independent physical validation.

**Significado en español**

MATLAB tiene OFF, EXPORT y RUN. EXPORT crea paquete determinista sin ejecutar. RUN exporta y llama MATLAB sin shell y con timeout. Incluye CSV, entradas, resultado Python, código `.m` y manifiesto SHA-256. MATLAB repite integración y criterio con tolerancias 1e-10 y 1e-9. Si discrepa, se reporta; Python no se reemplaza. Es contraste numérico, no validación física independiente.

**Transition**

> The FVA catalogue defines the discrete research configurations around that workflow.

---

## Slide 33 — FVA 600 III catalogue

**Time:** 55 seconds  
**Anchor:** Eight discrete research points, not an interpolated domain.

**Say in English**

The catalogue contains variants VB1 through VB8. Each fixes geometry ratio, interference, load ratio and key form. They are documented as discrete research configurations, not as a continuous domain for interpolation. The connected setup uses the declared nonlinear material models: Chaboche–Lemaitre for the shaft, UML Ramberg–Osgood for the hub and elastic-ideal-plastic for the key. Five load-carrying interfaces are configured for matching verification. MATCHED is earned only after actual node coordinates are compared after meshing; equal seed size is not proof.

**Significado en español**

VB1–VB8 son configuraciones discretas, no dominio interpolable. El setup conectado declara Chaboche–Lemaitre en eje, UML Ramberg–Osgood en cubo y plástico ideal en chaveta. Cinco interfaces se configuran para verificar coincidencia. MATCHED sólo se gana comparando coordenadas reales.

**Transition**

> I will now separate what has actually been verified from what remains outside the current evidence.

---

## Slide 34 — Verification

**Time:** 65 seconds  
**Anchor:** Software verification has a defined scope.

**Say in English**

The packaged self-test checks the 4.2 identity, schema 6, migration, catalogues, golden calculations, all eight current mesh templates and report rendering. The three language catalogues have six hundred and fifty keys each. The defaults and two packaged FVA companions are guarded under schema 6; the repository's ten-cycle setup validates separately and is not packaged. The intended kernel-side modules were audited for Python 2.7-compatible syntax. The artifact contract checks that expected outputs and the realized mesh match the plan. What this does not test is equally important: it does not start Abaqus, solve a model, review an ODB, compile LaTeX or validate an exact FVA specimen.

**Significado en español**

El self-test comprueba identidad, esquema, migración, catálogos, goldens, ocho plantillas e informes. Los tres idiomas tienen 650 claves. Los valores por defecto y dos compañeros FVA empaquetados quedan vigilados bajo esquema 6; la configuración de diez ciclos del repositorio se valida por separado y no se empaqueta. Se auditó sintaxis Python 2.7. El contrato compara artefactos y malla real. No arranca Abaqus, no resuelve, no revisa ODB, no compila LaTeX ni valida especimen FVA.

**Transition**

> Beyond numerical checks, several design choices reduce operational failure modes.

---

## Slide 35 — Robustness

**Time:** 50 seconds  
**Anchor:** Safety through explicit process boundaries.

**Say in English**

The Abaqus command is built as an argument list and never uses `shell=True`; control characters are rejected. The subprocess is contained in `jobs/`, and artifact routes must be absolute. NOJOB workflows have layered guards against job objects, solver files and conflicting configuration. Cancelling terminates the process tree and records CANCELLED. JSON writes are atomic through a temporary file and rename. Licensed DIN and FVA documents are excluded from the release by whitelist.

**Significado en español**

El comando usa lista de argumentos, nunca shell, y rechaza caracteres de control. El solver queda en `jobs/`; rutas absolutas. NOJOB tiene tres guardas. Cancelar mata el árbol y registra CANCELLED. Los JSON son atómicos. Documentos con licencia quedan fuera por lista blanca.

**Transition**

> The same controlled approach is used when creating the executable release.

---

## Slide 36 — Distribution

**Time:** 50 seconds  
**Anchor:** The executable is published only after identity and self-test checks.

**Say in English**

The release build creates a fresh local environment, pins PyInstaller 6.22.2 and hooks 2026.7, checks isolation, compiles fourteen modules and fingerprints thirty-one build inputs. It protects the historical 4.1 release, packages one executable, runs the self-test on that executable, enforces an output whitelist and writes checksums for the directory and ZIP. This protects packaging integrity and reproducibility; it does not prove physical engineering correctness.

**Significado en español**

El build crea entorno limpio, fija PyInstaller y hooks, verifica aislamiento, compila 14 módulos y hashea 31 entradas. Protege 4.1, empaqueta, ejecuta self-test sobre el EXE, aplica lista blanca y checksums. Protege integridad de empaquetado, no corrección física.

**Transition**

> This brings us to the honest current status of the project.

---

## Slide 37 — Status

**Time:** 60 seconds  
**Anchor:** Verified, pending decision and out of scope are not mixed.

**Say in English**

Verified today are the software identity, schema, default files, calculation goldens, catalogue parity and kernel compatibility checks. Decisions still open are the sign of equation 9, the release number, the GUI mesh-template override and whether to distribute the solver-enabled preset. Outside today's evidence are a successful 4.2 solver campaign and exact FVA specimen validation. Method A still needs external solved evidence. `K_lambda` remains a neutral placeholder, and case-specific external factors require review against the licensed source.

**Significado en español**

Verificado: identidad, esquema, defaults, goldens, catálogos y compatibilidad. Pendiente: signo ecuación 9, versión, override de malla GUI y preset solver. Fuera de evidencia: campaña solver 4.2 y especimen FVA exacto. Método A necesita evidencia externa. K_lambda sigue neutro y los factores externos requieren revisión licenciada.

**Transition**

> Those boundaries lead to three concrete next actions.

---

## Slide 38 — Next steps

**Time:** 45 seconds  
**Anchor:** Rebuild, settle equation 9, number the release.

**Say in English**

First, rebuild the executable from the complete project tree; the published 4.2 binary predates the two calculation corrections and seventeen of its thirty-one manifest inputs differ from the current tree. Second, settle the sign and datum of equation 9 against the licensed DIN text. That decision changes the shaft component by 46.35 percent, but the bundled D40 joint remains hub-governed at 999.18 newton-metres under all three current depth policies. Third, assign a release identity. My recommendation is 4.3, because two executables that both identify as 4.2 but return different default torque are an audit collision.

**Significado en español**

Primero reconstruir EXE: el publicado es anterior a las correcciones y 17/31 entradas cambiaron. Segundo cerrar signo/datum de ecuación 9 con DIN licenciado: eso cambia 46,35% el componente del eje, pero el D40 del paquete sigue gobernado por el cubo a 999,18 N·m con las tres políticas actuales. Tercero asignar versión; recomiendo 4.3 porque dos EXE 4.2 con pares distintos son colisión de auditoría.

**Transition**

> I will close with the principle that guided the implementation.

---

## Slide 39 — Closing

**Time:** 25 seconds  
**Anchor:** Traceability is the product.

**Say in English**

The value is not only the model. The value is being able to show how it was made, which assumptions were used, which evidence is normative, which is research, and which decisions remain open. Every calculation shown here can be traced to the code. Historical screenshots and renders are identified as source evidence rather than presented as new solver validation. Thank you. I am ready for your questions.

**Significado en español**

El valor no es sólo el modelo. Es poder demostrar cómo se hizo, qué hipótesis se usaron, qué es normativo, qué es investigación y qué queda abierto. Cada cálculo se rastrea al código; las capturas históricas se identifican como evidencia, no como validación solver nueva.

---

# How to practise this script

1. **First pass — Spanish only:** explain each anchor without looking at the English.
2. **Second pass — English in blocks:** practise slides 1–5, 6–12, 13–21, 22–30 and 31–39 separately.
3. **Third pass — transitions:** practise only the final transition sentence of each slide. This makes the presentation sound continuous rather than memorized.
4. **Fourth pass — numbers:** say the numerical facts without slides: 26 rows, 34 lengths, 7 radius bands, 8 templates, 15 presets, 4 methods, 3 languages, 650 keys, 14 modules, 31 build inputs, 17 changed, 999.18 N·m, 3.141 mm, 5.141 mm, 2.759 mm, 46.35%, 63.7%, 795.56 N·m.
5. **Fifth pass — limitations:** practise saying clearly: “This is traceable implementation evidence, not DIN certification.”
