# Model Builder 4.2 — Rehearsal cheat sheet

Print this document or keep it on your phone. It is the **minimum you should know without reading**.

---

# 1. The 30-second answer

> **EN:** Model Builder is a traceable workflow for supported DIN 6885 key-joint geometry, DIN 6892 analytical and research calculations, Abaqus model preparation, evidence capture and reporting. Its purpose is repeatability and auditability. It is not DIN certification, and physical acceptance remains an engineering responsibility.
>
> **ES:** Model Builder es un flujo trazable para geometría de chavetas DIN 6885 soportada, cálculos DIN 6892 analíticos y de investigación, preparación de Abaqus, evidencia e informes. Su objetivo es repetibilidad y auditabilidad. No es certificación DIN y la aceptación física sigue siendo responsabilidad de ingeniería.

# 2. Opening and closing — memorize verbatim

## Opening

> **Good morning. I will present Model Builder 4.2, a traceable workflow for shaft–hub key joints in Abaqus 2022. The central idea is not only to create a model, but to preserve enough evidence to explain exactly how it was created.**

## Closing

> **The value is not only the model. The value is being able to show how it was made, which assumptions were used, which evidence is normative, which is research, and which decisions remain open. Thank you. I am ready for your questions.**

---

# 3. The story in ten sentences

Memorize this sequence. It lets you recover if you lose your place.

1. **The problem was repeatability, not drawing one model.**  
   El problema era repetibilidad, no dibujar un modelo.
2. **Two runtimes share one calculation core.**  
   Dos runtimes comparten un solo núcleo de cálculo.
3. **DIN geometry is selected from explicit rows, with no extrapolation.**  
   La geometría DIN sale de filas explícitas, sin extrapolar.
4. **Errors block before Abaqus; warnings remain in the audit.**  
   Los errores bloquean antes de Abaqus; los warnings quedan auditados.
5. **Mesh policy is explicit, per part, and the worst part governs.**  
   La política de malla es explícita, por pieza, y gobierna la peor.
6. **Requested, derived and realized are kept separate.**  
   Solicitado, derivado y realizado quedan separados.
7. **Method B now checks the hub on its own `t2tr`.**  
   Método B comprueba el cubo con su propio t2tr.
8. **`f_W` counts load reversals, not total cycles.**  
   f_W cuenta inversiones de carga, no ciclos totales.
9. **MATLAB is a cross-check; Python remains authoritative.**  
   MATLAB es contraste; Python sigue siendo autoridad.
10. **The remaining engineering decisions are visible, not hidden.**  
    Las decisiones pendientes están visibles, no ocultas.

---

# 4. Numbers you must know

| Number | Meaning | How to say it in English |
|---:|---|---|
| 14 | Python modules compiled by the release build | fourteen modules |
| 26 | DIN 6885 diameter rows | twenty-six rows |
| 34 | standard key lengths | thirty-four lengths |
| 7 | radius bands | seven radius bands |
| 8 | current mesh templates | eight mesh templates |
| 15 | presets | fifteen presets |
| 4 | calculation method identifiers | four methods |
| 3 | languages | three languages |
| 650 | translation keys per language | six hundred and fifty keys |
| 31 | fingerprinted build inputs | thirty-one build inputs |
| 17/31 | inputs changed since the published EXE | seventeen of thirty-one |
| 999.18 N·m | current Method B D40 golden | nine hundred and ninety-nine point one eight newton-metres |
| 1,302.05 N·m | reconstructed pre-correction value | one thousand three hundred and two point zero five newton-metres |
| 572.51 N·m | Method C default | five hundred and seventy-two point five one newton-metres |
| 2,464.87 N·m | FVA research diagnostic | two thousand four hundred and sixty-four point eight seven newton-metres |
| 795.56 N·m | fully alternating current-B result | seven hundred and ninety-five point five six newton-metres |
| 5.141 mm | literal equation-9 shaft depth | five point one four one millimetres |
| 3.141 mm | hub effective depth | three point one four one millimetres |
| 2.759 mm | geometric shaft depth | two point seven five nine millimetres |
| 63.7% | hub area previously over-credited | sixty-three point seven percent |
| 46.35% | equation-9 spread | forty-six point three five percent |
| 0.796 | `f_W` at 10,000 reversals | zero point seven nine six |
| 2% | Method A coverage tolerance | two percent |
| 0.5 | Method A `v_crit` | zero point five |
| 1e-10 / 1e-9 | MATLAB comparison tolerances | one e minus ten / one e minus nine |

---

# 5. The three most important limitations

Say these confidently. They make the presentation stronger, not weaker.

1. **Equation 9 remains open.**  
   > The tool reports the literal, geometric and conservative policies. The licensed text must settle the sign and datum.
2. **The published EXE is not current.**  
   > It predates the `t2tr` and `f_W` corrections and must be rebuilt and versioned.
3. **No complete 4.2 solver-validation campaign is claimed.**  
   > The self-test validates software behavior, not a solved physical specimen.

---

# 6. The five answers you are most likely to need

## “Is it DIN-certified?”

> **No. It implements the supported DIN workflow with traceability. Certification and physical acceptance remain engineering responsibilities.**

## “Is 999.18 N·m the approved torque?”

> **No. It is the reproducible Method B golden for the bundled D40 inputs. `K_lambda` is provisional and equation 9 remains open.**

## “Why is MATLAB there?”

> **To independently repeat the numerical post-processing. Python remains authoritative; MATLAB never replaces the result.**

## “Has Method A been solved?”

> **No complete Method A evidence is claimed. The tool assesses an externally solved and unloaded ODB that passes the evidence contract.**

## “What is the next step?”

> **Rebuild the executable, settle equation 9 against the licensed text, and assign a new release identity. My recommendation is 4.3.**

---

# 7. Pronunciation for a Spanish speaker

The pronunciation hints are approximate; stressed syllables are in **CAPITALS**.

| English term | Approximate pronunciation | Meaning |
|---|---|---|
| traceable | **TREI**-sa-bol | trazable |
| workflow | **UORK**-flou | flujo de trabajo |
| shaft | shaft | eje |
| hub | hab | cubo |
| key | kii | chaveta |
| keyway | **KII**-uei | chavetero/ranura |
| bearing depth | **BEA**-ring depth | profundidad portante |
| allowable torque | a-**LAU**-a-bol tork | par admisible |
| governed by the hub | **GA**-vernd bai de hab | gobernado por el cubo |
| evidence | **E**-vi-dens | evidencia |
| provenance | **PRO**-ve-nans | procedencia |
| audit | **O**-dit | auditoría |
| reproducible | rii-pro-**DU**-sa-bol | reproducible |
| hexahedral | hek-sa-**HII**-dral | hexaédrico |
| tetrahedral | te-tra-**HII**-dral | tetraédrico |
| mesh | mesh | malla |
| matching mesh | **MA**-ching mesh | malla coincidente |
| fillet | **FI**-let | radio/redondeo |
| notch | noch | entalla |
| aspect ratio | **AS**-pekt **REI**-shio | relación de aspecto |
| load reversal | loud rii-**VER**-sal | inversión de carga |
| pulsating torque | **PAL**-sei-ting tork | par pulsante |
| alternating torque | **OL**-ter-nei-ting tork | par alternante |
| unloaded frame | an-**LOU**-did freim | fotograma descargado |
| residual opening | rii-**SI**-diu-al **OU**-pe-ning | apertura residual |
| cross-check | kros-chek | contraste/verificación cruzada |
| authoritative | o-**THO**-ri-tei-tiv | autoritativo |
| whitelist | **UAIT**-list | lista blanca |
| checksum | **CHEK**-sam | suma de comprobación |
| timeout | **TAIM**-aut | tiempo límite |
| bushing | **BU**-shing | casquillo |
| tapered | **TEI**-perd | cónico |
| compliance | com-**PLAI**-ans | cumplimiento |
| override | ou-ver-**RAID** | anulación explícita |
| solver | **SOL**-ver | solucionador |
| finite element | **FAI**-nait **E**-le-ment | elemento finito |

## Symbols and variables

| Symbol | Say |
|---|---|
| `t1tr` | “tee one tee ar” |
| `t2tr` | “tee two tee ar” |
| `f_W` | “eff sub W” |
| `N_W` | “en sub W” |
| `K_lambda` | “kay lambda” |
| `l_tr` | “ell sub tee ar” |
| `d_w` | “dee sub W” |
| `Q_A` | “cue sub A” |
| `v_crit` | “vee crit” |
| `ΔV` | “delta V” |
| `R=-1` | “R equals minus one” |

---

# 8. Presentation behavior

## If you forget a word

Do not stop. Replace it with simpler English:

- “provenance” → “source record”
- “allowable torque” → “maximum calculated torque under this method”
- “constitutive model” → “material model”
- “interoperability” → “the two tools working together”
- “deterministic” → “the same input produces the same output”

## If you do not understand the question

> **Could you please rephrase the question? I want to make sure I answer the right point.**

## If you need time

> **That is an important distinction. Let me separate what is implemented from what is validated.**

## If the answer is not known

> **I do not want to speculate. The current evidence proves ____. The open point is ____, and I would close it by ____.**

## If someone challenges a number

> **That value is either calculated live from the current core or identified as historical source evidence. I can show the exact function and audit record after the presentation.**

---

# 9. Suggested timing

| Section | Slides | Time |
|---|---:|---:|
| Problem and architecture | 1–5 | 3 min |
| Real interface | 6–12 | 5 min |
| Pipeline, workspace, presets, design space | 13–16 | 3 min |
| Model, mesh and analysis | 17–21 | 4 min |
| Traceability, DIN data, audit and report | 22–25 | 3 min |
| Methods and corrections | 26–30 | 5 min |
| Method A, MATLAB and FVA | 31–33 | 4 min |
| Verification, robustness, release and close | 34–39 | 4 min |
| **Total** | **39** | **31 min** |

For the canonical **20-minute version**, present slides 1, 2, 4, 5, 7, 8, 13, 17, 19, 22, 23, 26–32, 34 and 37–39; keep the remaining slides as backup.

---

# 10. Final pre-meeting checklist

- [ ] English PPTX downloaded locally and opened once.
- [ ] Spanish PPTX available as study backup.
- [ ] PDF export available in case PowerPoint fonts or media fail.
- [ ] No live solver run planned.
- [ ] Abaqus and MATLAB paths are not changed during the meeting.
- [ ] Opening and closing memorized verbatim.
- [ ] The five likely answers memorized.
- [ ] Numbers 999.18, 3.141, 5.141, 2.759, 46.35%, 63.7% and 795.56 rehearsed.
- [ ] You can say: “not certification,” “provisional,” “research diagnostic,” and “open decision” without hesitation.
