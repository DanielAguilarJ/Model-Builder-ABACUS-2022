# Model Builder 4.2 — Supervisor Q&A bank

Use the **English answer** during the presentation. The Spanish section explains exactly what you are saying. Answers follow a four-part pattern whenever possible:

1. answer directly;
2. state the evidence;
3. state the limitation;
4. state the next action if applicable.

If you do not know an answer, use this safe sentence:

> **EN:** I do not want to speculate. What the current evidence proves is ____. The open point is ____, and the correct next step is ____.
>
> **ES:** No quiero especular. Lo que demuestra la evidencia actual es ____. El punto abierto es ____ y el siguiente paso correcto es ____.

---

# 1. Purpose and value

## Q1. What problem does Model Builder solve?

**Answer in English**

It converts a controlled parameter set into derived DIN geometry, an Abaqus model and mesh, an audit trail, evidence artifacts and a report. Its demonstrated value is repeatability and traceability. I am not claiming a quantified financial return because the repository does not contain a time-saving or ROI study.

**En español**

Convierte parámetros controlados en geometría DIN, modelo/malla Abaqus, auditoría, evidencia e informe. El valor demostrado es repetibilidad y trazabilidad. No debes inventar ahorro de tiempo o ROI porque no hay estudio.

## Q2. Is it more than a parameter-entry GUI?

**Answer in English**

Yes. Validation occurs before Abaqus; the shared core selects exact DIN rows, derives dimensions and calculation records, and resolves mesh policy. The Abaqus kernel builds solids, mesh, optional analysis, audit and previews. The GUI is the control surface, not the calculation engine.

**En español**

Sí. La validación ocurre antes de Abaqus; el núcleo selecciona DIN, deriva y resuelve malla. Abaqus construye sólidos, malla, análisis opcional, auditoría y capturas. La GUI no es el motor.

## Q3. What is the business benefit?

**Answer in English**

The evidence-based benefit is controlled reproducibility: stable schemas, migrations, hashes, issue codes, isolated workspaces and plan-versus-realized records. I would not claim a percentage of time saved or defect reduction until that is measured in a separate study.

**En español**

El beneficio demostrado es reproducibilidad controlada. No afirmes “ahorra 60%” ni reducción de errores si no se ha medido.

## Q4. Is this production-ready?

**Answer in English**

The automation, analytical core, audit contract and packaging controls are mature enough for controlled engineering use within the documented scope. However, the current published executable predates two calculation corrections, equation 9 remains open, and there is no successful 4.2 solver-validation campaign. I would therefore rebuild, version and review before calling it a final engineering release.

**En español**

El flujo está maduro para uso controlado, pero el EXE está desactualizado, ecuación 9 abierta y no hay campaña solver 4.2. No digas “production-ready” sin esa condición.

## Q5. Is this DIN-certified or DIN-approved?

**Answer in English**

No. It implements supported DIN data and calculation workflows with explicit traceability. Certification and physical acceptance are outside the software's authority and remain engineering responsibilities.

**En español**

No. Implementa datos y métodos DIN dentro de alcance. No certifica ni aprueba físicamente la unión.

---

# 2. Architecture and runtimes

## Q6. Why are there two Python versions?

**Answer in English**

The desktop application uses Python 3, while Abaqus 2022 executes its kernel scripts under Python 2.7. The pure calculation modules are compatible with both so the DIN table and formulas are shared instead of duplicated.

**En español**

La aplicación usa Python 3 y el kernel Abaqus 2022 usa Python 2.7. El núcleo es compatible con ambos para evitar duplicación.

## Q7. Can the program open without Abaqus installed?

**Answer in English**

Yes. The desktop side imports no Abaqus modules, so the interface and pure calculations can run without Abaqus. Building CAE geometry, meshing or solving still requires a local licensed Abaqus installation.

**En español**

Sí para GUI y cálculo puro; no para construir CAE, mallar o resolver.

## Q8. Is the whole application Python 2.7-compatible?

**Answer in English**

No. Only the shared core and the modules intended to run inside Abaqus are Python 2.7-compatible. The GUI, report generator, CSV post-processor and MATLAB companion are Python 3.

**En español**

No. Sólo núcleo compartido y módulos kernel. GUI, informes, CSV y MATLAB son Python 3.

## Q9. What prevents formulas drifting between the GUI and Abaqus?

**Answer in English**

Both sides import `keyjoint_core.py` and `din6892_methods.py`. That removes code duplication. It reduces implementation drift, but it does not independently prove that every transcription from the licensed standard is correct; equation 9 is the clearest example of why source review is still required.

**En español**

Comparten los mismos módulos. Evita drift de código, pero no demuestra que toda transcripción del estándar sea correcta.

## Q10. Why use a subprocess instead of importing Abaqus from the GUI?

**Answer in English**

Abaqus owns a separate Python runtime and licensed kernel environment. The subprocess boundary keeps the desktop independent, lets the run use a controlled working directory, captures the full log and allows cancellation of the process tree.

**En español**

Abaqus tiene runtime propio. El subproceso separa entornos, controla cwd, log y cancelación.

---

# 3. DIN 6885 geometry

## Q11. What DIN 6885 scope is implemented?

**Answer in English**

The code has twenty-six explicit diameter bands over `6 < d1 <= 500 millimetres`, thirty-four standard key lengths, seven separate radius bands and key forms A, B and AB. The currently built groove geometry is N1. Forms C through J and DIN 6888 Woodruff geometry are not implemented.

**En español**

26 bandas, 34 longitudes, 7 bandas de radios, formas A/B/AB y ranura N1. C–J y DIN 6888 no implementados.

## Q12. Does the software interpolate between DIN rows?

**Answer in English**

No. It uses strict-lower and inclusive-upper diameter bands and raises outside the implemented range. It neither clamps nor extrapolates, because that could create a false normative claim.

**En español**

No interpola, no limita al extremo y no extrapola. Fuera del rango da error.

## Q13. Why is the D40 key 12 by 8 millimetres?

**Answer in English**

Forty millimetres falls in the explicit band `38 < d1 <= 44`. That row returns `b=12`, `h=8`, `t1=5.0`, `t2=3.3` and the related tolerances and radii.

**En español**

D40 cae en 38 < d1 ≤ 44 y esa fila da 12×8, t1=5, t2=3,3.

## Q14. Are all geometry values normative?

**Answer in English**

No. Table-derived dimensions within scope carry NORMATIVE evidence. Values such as the default key chamfer are user parameters. Overrides remain USER-OVERRIDE and do not become normative simply because the model builds.

**En español**

No. Dimensiones de tabla son normativas dentro de alcance; chaflán es dato de usuario. Override no se convierte en normativo.

## Q15. Why are forms C through J refused?

**Answer in English**

They require additional hole and chamfer dimensions that the current solid builder does not implement. Refusing them explicitly is safer than silently mapping them to a supported form.

**En español**

Necesitan cotas no implementadas. Se rechazan para no simular soporte falso.

## Q16. Is the radius table transcription completely settled?

**Answer in English**

No. The project documents ambiguity in some source-extraction group boundaries. The D40 case uses the current declared radius band, but the licensed printed table still has to settle any ambiguous grouping before a formal release claim.

**En español**

No del todo. Hay ambigüedad de agrupación en la fuente extraída; debe revisarse el texto impreso con licencia.

---

# 4. DIN 6892 methods and results

## Q17. Why do you say four methods when DIN uses A, B and C?

**Answer in English**

The four software identifiers are Method A, current Method B, the FVA 2025 proposed reformulation of Method B and preliminary Method C. The extra item is a research reformulation, not a fourth published DIN letter method.

**En español**

Son A, B vigente, B reformulado por FVA y C. El cuarto identificador es investigación, no otra letra DIN.

## Q18. What is current Method B doing?

**Answer in English**

It evaluates the equation chain per component. Shaft, hub and key each use their own material factors and effective bearing depth. The weakest allowable torque governs. For the default case the hub governs.

**En español**

Calcula por componente con sus factores y profundidad. Gobierna el par más débil; en D40, el cubo.

## Q19. Is 999.18 N·m the approved capacity?

**Answer in English**

No. It is a reproducible software golden for the bundled D40 inputs and current Method B implementation. The result is provisional because `K_lambda` is still a neutral placeholder and equation 9 remains unresolved. It is not a certification or released design allowable.

**En español**

No. Es golden reproducible del software, pero provisional por K_lambda y ecuación 9. No es capacidad aprobada.

## Q20. Why did the value change from about 1,302 to 999 N·m?

**Answer in English**

It combines two corrections. First, the hub had been credited with the shaft effective depth `t1tr` instead of its own shorter `t2tr`; correcting that while retaining the old reversal factor gives about 795.56 N·m. Second, equation 3 is driven by load-direction reversals, so the pulsating default has `f_W=1`, raising the current hub-governed result to 999.18 N·m. The complete old value reconstructs as `999.18 × t1tr/t2tr × f_W(10,000) = 1,302.0515 N·m`.

**En español**

Combina dos correcciones. Primero, el cubo usaba t1tr del eje en lugar de t2tr; corregir sólo eso manteniendo el factor antiguo da unos 795,56 N·m. Segundo, la ecuación 3 usa inversiones de dirección, por lo que el caso pulsante tiene f_W=1 y el resultado actual gobernado por el cubo sube a 999,18 N·m. El valor viejo completo se reconstruye como `999,18 × t1tr/t2tr × f_W(10.000) = 1302,0515 N·m`.

## Q21. Why is the hub checked on `t2tr`?

**Answer in English**

Because DIN 6892 evaluates the shaft pressure over the shaft flank area and the hub pressure over the hub flank area. Those effective depths are different. The key uses the smaller mating depth because it carries the same flank pressure.

**En español**

Cada componente usa su propio flanco. La chaveta usa el menor de los dos.

## Q22. Why is `f_W=1` even though the case has 10,000 cycles?

**Answer in English**

Equation 3 uses load-direction reversals, not total cycles. With a pulsating torque and non-negative load ratio, the load remains on one flank, so there are zero reversals and `f_W=1`. Under fully alternating loading, ten thousand reversals give approximately `f_W=0.796`.

**En español**

f_W cuenta inversiones de flanco, no ciclos. Carga pulsante queda en un flanco: f_W=1. Alternante: 0,796.

## Q23. What does the 2,464.87 N·m FVA value mean?

**Answer in English**

It is a research diagnostic from the FVA 2025 Method B reformulation. It is not a DIN acceptance value and it does not cover complete hub and key acceptance. I show it as a comparison, not as the design torque.

**En español**

Es diagnóstico de investigación FVA, no aceptación DIN ni par de diseño.

## Q24. What is Method C used for?

**Answer in English**

It is preliminary sizing based on constant allowable pressure. It can also invert the calculation to estimate the required bearing length and nominal key length. It remains subordinate to the more complete checks.

**En español**

C sirve para dimensionado preliminar e inversión de longitud requerida. No sustituye checks completos.

## Q25. Has equation 9 been corrected?

**Answer in English**

No. The software reports the literal transcription, the independent geometric result and a conservative choice. The default remains the literal equation policy, with a warning. The licensed standard and its datum must settle the sign.

**En español**

No. Se reportan literal, geométrico y conservador. El default sigue literal con warning. La norma licenciada debe cerrar el signo.

## Q26. Why not simply choose the conservative value?

**Answer in English**

The tool allows that policy, but silently replacing a transcribed standard equation would hide an interpretation decision. The traceable approach is to show both values, expose the spread and require an explicit policy or licensed-source decision.

**En español**

Se puede elegir conservador, pero no debe sustituirse silenciosamente la ecuación. Hay que mostrar ambos y decidir explícitamente.

---

# 5. Method A and evidence

## Q27. Does Model Builder solve Method A?

**Answer in English**

The tool can prepare guarded Method A setups and assess external evidence, but the analytical assessment does not manufacture a valid solved ODB. A conclusive Method A result needs externally solved, unloaded evidence that passes provenance and coverage checks.

**En español**

Puede preparar setups y evaluar evidencia, pero no fabrica un ODB válido. Necesita solución externa descargada y verificada.

## Q28. What does the Method A CSV contain?

**Answer in English**

It contains the canonical columns `x_mm`, `z_mm` and `opening_um`. The opening is obtained by pairing left and right keyway nodes using undeformed coordinates and subtracting their displacement components in the unloaded frame.

**En español**

CSV: x, z y apertura en micras. Se emparejan nodos por coordenadas sin deformar y se resta desplazamiento en frame descargado.

## Q29. Does importing a CSV prove Method A?

**Answer in English**

No. It proves only that the evidence satisfies the post-processing contract. A complete engineering claim also needs mesh convergence, equilibrium, contact, material-model and fatigue review. Those checks remain visible rather than being implied.

**En español**

No. Sólo prueba contrato de postproceso. Faltan convergencia, equilibrio, contacto, material y fatiga.

## Q30. Why is an unloaded frame required?

**Answer in English**

Method A evaluates permanent opening, not total elastic displacement under peak load. The unloaded frame separates residual opening from the reversible response.

**En español**

Método A mide apertura permanente, no desplazamiento elástico bajo carga. Por eso necesita descarga.

## Q31. Why at least ten cycles?

**Answer in English**

That is the declared research-method evidence gate in the implemented Method A workflow. Cases below ten cycles can be useful as pre-solve regressions, but they cannot be promoted to complete Method A evidence.

**En español**

Es la puerta de evidencia del método implementado. Menos de 10 ciclos sirve como regresión, no evidencia completa.

## Q32. What does the two-percent coverage check mean?

**Answer in English**

The sampled CSV grid must cover the expected bearing domain closely enough that missing edge regions cannot materially change the integrated volume. The current contract allows a two-percent coverage tolerance.

**En español**

La rejilla debe cubrir el dominio esperado; se permite 2% de tolerancia para no integrar un dominio incompleto.

---

# 6. MATLAB

## Q33. Why is MATLAB included?

**Answer in English**

It provides an optional second numerical implementation of the same CSV integration and criterion. Its purpose is to detect numerical or implementation disagreement, not to replace Python or validate the physical model independently.

**En español**

MATLAB es un segundo cálculo numérico para detectar discrepancias, no reemplazo de Python ni validación física.

## Q34. What are OFF, EXPORT and RUN?

**Answer in English**

OFF changes nothing. EXPORT writes a deterministic exchange bundle without invoking MATLAB. RUN writes the same bundle and invokes MATLAB with an argument list, `shell=False` and a finite timeout.

**En español**

OFF nada; EXPORT paquete sin ejecutar; RUN paquete y ejecución segura con timeout.

## Q35. What exactly is exported?

**Answer in English**

The bundle contains canonical `opening.csv`, `method_a_input.json`, the authoritative `python_result.json`, generated MATLAB source and `manifest.json` with file sizes and SHA-256 hashes. RUN additionally writes the MATLAB result and stdout log.

**En español**

CSV, entradas, resultado Python, código MATLAB y manifiesto con hashes; RUN añade resultado/log MATLAB.

## Q36. Which result is authoritative if MATLAB disagrees?

**Answer in English**

Python remains authoritative. The mismatch is recorded using absolute tolerance `1e-10` and relative tolerance `1e-9`. MATLAB never overwrites the Python value.

**En español**

Python manda siempre. La discrepancia se registra con tolerancias 1e-10 y 1e-9.

## Q37. Does MATLAB independently validate the physics?

**Answer in English**

No. It independently reproduces the numerical integration and criterion from the same evidence. It does not independently solve the ODB, validate constitutive models or prove mesh convergence.

**En español**

No. Repite integración/criterio con la misma evidencia; no resuelve ODB ni valida física.

## Q38. Is the MATLAB bundle auditable?

**Answer in English**

Yes, within its scope. Inputs, outputs and generated source have manifest records and SHA-256, and `verify_bundle` rechecks retained files. That detects change; it is not a digital-signature or identity system.

**En español**

Sí para integridad mediante hashes; no es firma digital ni identidad de firmante.

---

# 7. Abaqus, mesh and analysis

## Q39. What geometry is actually generated?

**Answer in English**

Independent shaft, key and hub solids; tapered mode adds a bushing. The assembly creates named instances, sets and surfaces, including a local `NOTCH_SHAFT` set around the keyway root.

**En español**

Sólidos de eje, chaveta y cubo; cónico añade casquillo. Se crean instancias, sets y superficies, incluido NOTCH_SHAFT.

## Q40. Does every model have an all-hexahedral mesh?

**Answer in English**

No. `HEX_CERTIFIED` requires one hundred percent hexahedra, but other templates allow mixed or hybrid topologies. The selected policy and realized topology are written in the audit.

**En español**

No. HEX_CERTIFIED sí; otras permiten mixta/híbrida. Se audita la topología real.

## Q41. Is every interface node-matched?

**Answer in English**

No blanket claim is justified. The specialized Method A backend can verify configured interfaces by comparing actual node coordinates after meshing. Equal seed sizes or an image are not accepted as proof.

**En español**

No se puede afirmar para todo. Método A especializado compara coordenadas reales después de mallar. Semilla igual o imagen no prueba.

## Q42. Does a good mesh score prove stress convergence?

**Answer in English**

No. It proves compliance with geometric and topology quality gates. Stress convergence requires a separate study of the engineering response across mesh refinements.

**En español**

No. Score prueba calidad geométrica/topológica. Convergencia de tensiones requiere estudio separado.

## Q43. Why is the global mesh score the worst part?

**Answer in English**

Because one unacceptable part must not be hidden by averaging it with three good parts. The worst-part rule makes the gate conservative and easy to audit.

**En español**

Para que una pieza mala no quede oculta por el promedio.

## Q44. Are the regular builder materials nonlinear?

**Answer in English**

No. In the regular builder path, the solids remain linear elastic; grade and yield values are documentation. The specialized Method A backend has the nonlinear material models shown in the FVA slide. Those claims must not be transferred to every model.

**En español**

No. El constructor regular es elástico lineal. Los modelos no lineales pertenecen al backend especializado de Método A.

## Q45. Is the default model solved?

**Answer in English**

No. Analysis is off by default, and the bundled FVA presets are intentionally NOJOB. Solving requires explicit job creation and submission.

**En español**

No. Análisis apagado y presets FVA NOJOB. Resolver requiere activación explícita.

## Q46. Has the complete 20-cycle Method A model been solved successfully?

**Answer in English**

No successful complete Method A evidence is claimed. Historical work includes partial or terminated runs, but no complete unloaded 20-cycle result that satisfies the full evidence contract.

**En español**

No se afirma solución completa de 20 ciclos descargada y válida. Hay históricos parciales, no evidencia completa.

---

# 8. Audit, report and security

## Q47. Is a zero return code enough to accept a build?

**Answer in English**

No. The process return, `BUILD_RESULT.ok`, audit verdict, required artifacts and realized mesh contract must all agree. A solved engineering result additionally requires ODB and physical review.

**En español**

No. Deben coincidir retorno, BUILD_RESULT, auditoría, artefactos y malla. Si se resolvió, además revisar ODB/física.

## Q48. What is the difference between requested, derived and realized?

**Answer in English**

Requested is what the user asked for. Derived is what the core calculated from those inputs. Realized is what the CAE backend actually built. Keeping them separate prevents a requested capability from being reported as accomplished without evidence.

**En español**

Solicitado, derivado y realizado. Separarlos evita afirmar que se construyó algo sólo porque se pidió.

## Q49. Are the audit files tamper-proof?

**Answer in English**

They are traceable, not tamper-proof or digitally signed. Hashes and atomic writes detect changes and prevent partial files when compared with trusted records, but they do not establish signer identity.

**En español**

Son trazables, no inviolables ni firmados. Hashes detectan cambios frente a registros confiables.

## Q50. Is the PDF digitally signed?

**Answer in English**

No. The tool generates a PDF for review and possible signature. It does not implement a digital-signature workflow.

**En español**

No. Genera PDF para revisión/firma, pero no firma digitalmente.

## Q51. What happens without LaTeX?

**Answer in English**

The report data and `.tex` source are still written, and a localized message records that no compiler was available. Missing LaTeX does not invalidate the model build.

**En español**

Se escriben JSON y TEX, se registra falta de compilador y el build del modelo no falla.

## Q52. Why `shell=False`?

**Answer in English**

It avoids shell interpretation and reduces command-injection and quoting risks. Arguments are passed explicitly, control characters are rejected and the working directory is controlled.

**En español**

Evita interpretación del shell, reduce riesgos y controla argumentos/cwd.

---

# 9. Testing and release

## Q53. What does the self-test prove?

**Answer in English**

It proves software identity, schema migration, catalogue parity, calculation goldens, current mesh-template catalogues, CSV and report behavior, and intended kernel-side syntax compatibility within its test scope.

**En español**

Prueba identidad, esquema, catálogos, goldens, plantillas, CSV, informes y sintaxis kernel dentro de su alcance.

## Q54. What does the self-test not prove?

**Answer in English**

It does not start Abaqus, build or mesh a real model, submit a solver job, validate contact or material physics, review an ODB, compile LaTeX or validate an exact FVA specimen.

**En español**

No arranca Abaqus, no construye/malla/resolve, no valida física/ODB/LaTeX/especimen.

## Q55. What real Abaqus evidence exists?

**Answer in English**

There is historical NOJOB geometry and mesh evidence from protected earlier work and generated preview images. That supports the inherited foundation, but it is not a successful 4.2 solver campaign or exact FVA validation.

**En español**

Hay evidencia histórica NOJOB de geometría/malla y previews. No equivale a campaña solver 4.2 ni FVA exacto.

## Q56. How is the release protected?

**Answer in English**

The build fingerprints thirty-one inputs, protects the historical 4.1 artifacts, runs the packaged self-test, publishes only a whitelist and writes manifest and ZIP checksums. This proves packaging integrity, not physical correctness.

**En español**

Hashea 31 entradas, protege 4.1, ejecuta self-test, lista blanca y checksums. Integridad del paquete, no física.

## Q57. Is the published 4.2 executable current?

**Answer in English**

No. It predates the `t2tr` and `f_W` corrections; seventeen of thirty-one manifest inputs differ from the current tree. It must be rebuilt before distribution.

**En español**

No. Es anterior a correcciones y 17/31 entradas cambiaron. Debe reconstruirse.

## Q58. Why recommend version 4.3?

**Answer in English**

Because two executables with the same 4.2 identity but different default torque are an audit collision. A new version makes the changed physics and evidence boundary explicit.

**En español**

Dos EXE 4.2 con par distinto son colisión. 4.3 hace explícito el cambio de física.

## Q59. Why did some old documentation say six mesh templates?

**Answer in English**

That wording was inherited before `HEX_CERTIFIED` and `FVA_METHOD_A_HYBRID` were added. The current code and current self-test catalogue contain eight. The deck now states eight and treats six as stale wording.

**En español**

La frase de seis quedó obsoleta antes de añadir dos plantillas. Código actual: ocho.

---

# 10. Open decisions and limitations

## Q60. What must be closed before a formal engineering release?

**Answer in English**

At minimum: settle equation 9 against the licensed text; verify any ambiguous radius grouping; supply and review case-specific licensed factors such as `K_lambda`; rebuild and version the executable; and perform case-specific solver, ODB, convergence, contact, material and fatigue review where a solved acceptance claim is required.

**En español**

Cerrar ecuación 9, radios ambiguos, factores licenciados, reconstruir/versionar y hacer revisión solver/ODB/convergencia/contacto/material/fatiga según el caso.

## Q61. Which related standards are not fully implemented?

**Answer in English**

DIN 743 fatigue remains external evidence. ISO 286 fits and DIN 7190 friction closure require user input. ISO 18265 is research/report data only. DIN 6888 geometry and unsupported key forms remain blocked or reference-only.

**En español**

DIN 743 externo; ISO 286 y DIN 7190 con inputs; ISO 18265 sólo reporte/investigación; DIN 6888 y formas no soportadas bloqueadas.

## Q62. Can user override make a case normative?

**Answer in English**

No. Override allows the case to remain visible and auditable. It does not promote the evidence class to NORMATIVE.

**En español**

No. Override permite ejecutar/registrar, pero no vuelve normativo el caso.

## Q63. Why trust the transcribed equations?

**Answer in English**

The implementation is centralized and pinned by calculation goldens and consistency tests, which proves reproducibility of the implementation. Independent validation against the licensed source is still required for disputed transcription or datum questions. Equation 9 is openly retained as an unresolved example.

**En español**

El código centralizado y los goldens prueban reproducibilidad, no validación independiente de la fuente. Las dudas licenciadas siguen abiertas.

## Q64. What is your strongest honest final claim?

**Answer in English**

Model Builder implements a traceable, reproducible workflow for supported DIN 6885 geometry, DIN 6892 analytical and research calculations, Abaqus model preparation, evidence capture and reporting, with explicit provenance and blocking rules. Physical acceptance, licensed-factor review and solved-model validation remain engineering responsibilities.

**En español**

Es el claim central: flujo trazable/reproducible dentro de alcance; aceptación física y validación siguen siendo responsabilidad de ingeniería.

---

# Questions about a failure during the live presentation

## Q65. What if the executable does not open?

**Answer in English**

I would not debug live for more than one minute. I would show the captured real interface and explain that the current deck is evidence-based. After the meeting I would collect the Windows error, executable hash and environment details and reproduce it against the release manifest.

**En español**

No depures en vivo más de un minuto. Usa capturas reales y luego recopila error/hash/entorno.

## Q66. What if Abaqus is not detected?

**Answer in English**

The launcher path can be selected explicitly. Detection is convenience, not a requirement. I would verify the local Abaqus command and licence outside the presentation rather than changing the model configuration.

**En español**

Se puede elegir ruta manual. Detectar es comodidad, no requisito.

## Q67. What if MATLAB is not installed?

**Answer in English**

Use OFF or EXPORT. MATLAB is optional; Python remains authoritative. EXPORT still creates the complete deterministic bundle for another machine.

**En español**

Usa OFF o EXPORT. MATLAB es opcional; Python manda. El paquete puede ejecutarse en otra máquina.

## Q68. What if LaTeX is not installed?

**Answer in English**

The tool still produces `report.tex` and `report_data.json` and records that the PDF compiler was unavailable. The model evidence remains intact.

**En español**

Produce TEX/JSON y registra que falta compilador. La evidencia del modelo sigue intacta.

## Q69. What if the supervisor asks for a live solver run?

**Answer in English**

I would explain that a solver run is not an appropriate live-demo step because it depends on licence, runtime and model size. I can demonstrate configuration and build controls live, while a solver claim should be based on archived ODB evidence and review, not on a rushed meeting run.

**En español**

Un solver no es adecuado en vivo por licencia/tiempo/tamaño. Demuestra configuración y controles; la evidencia solver debe ser ODB archivado y revisado.

---

# Phrases you must not say

| Do not say | Say instead |
|---|---|
| “It is DIN-certified.” | “It implements the supported DIN workflow; certification is outside the software.” |
| “999.18 N·m is the approved torque.” | “999.18 N·m is the reproducible current-Method-B golden, with provisional factors and equation 9 open.” |
| “2,464.87 N·m is the design capacity.” | “It is an FVA-RESEARCH diagnostic for comparison.” |
| “Method A is solved by Model Builder.” | “Model Builder prepares guarded setups and assesses external solved evidence.” |
| “MATLAB validates the physics.” | “MATLAB independently cross-checks the numerical post-processing.” |
| “All meshes are hexahedral and matching.” | “Topology depends on policy; exact Method-A matching must be verified from node coordinates.” |
| “The mesh is converged.” | “The mesh passes quality gates; stress convergence is a separate study.” |
| “The report is digitally signed.” | “The report is generated for review and possible signature.” |
| “A zero return code proves success.” | “Return code, audit, build result, artifacts and realized mesh must all agree.” |
| “All fifteen presets were solver-tested.” | “All presets re-enter validation; bundled FVA presets are intentionally NOJOB.” |
| “Equation 9 is fixed.” | “Both interpretations are reported; licensed clarification is still open.” |
| “The current published EXE contains the corrections.” | “The published EXE predates the corrections and must be rebuilt.” |
| “Every value is normative.” | “Each value retains its evidence badge.” |
| “Every number comes from a new run.” | “Calculations are code-traceable; historical screenshots and renders are identified as source evidence.” |
