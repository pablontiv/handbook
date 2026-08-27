---
tipo: adr
estado: accepted
fecha: "2026-08-21"
contexto: >-
  La ronda final de Task 3 exigió cerrar brechas de verificabilidad en dos
  superficies críticas: (1) atestación de sandbox basada en probes y (2)
  evidencia de inventario de bytes en límites de runtime. El diseño previo
  permitía aceptar observaciones con validación incompleta de argv/resultado y
  reportar host unchanged incluso cuando ambos inventarios host eran
  INCONCLUSIVE.
decision: >-
  Endurecer el contrato de evidencia: derivar status de ProbeObservation desde
  resultados observados, validar atestación contra probes semánticos exactos
  (argv, identidad ejecutable absoluta, perfil, returncode, timeout,
  truncación, digests, expected_outcome) y reescribir byte_inventory con
  recorrido incremental os.scandir + lectura en chunks con límites previos de
  paths/files/bytes/path-length. Cuando inventarios host son inconclusos,
  registrar host_change_assessment como null en lugar de unchanged=true.
consecuencias: >-
  Se elimina aceptación implícita de evidencia parcial y se evita sobredeclarar
  invariancia del host sin prueba concluyente. Aumenta la rigurosidad
  fail-closed y la cobertura de tests de borde (Git, limpieza, status matrix),
  con costo de mayor sensibilidad a desalineaciones de paths canónicos y mayor
  complejidad en fixtures de prueba.
---

## Contexto

La validación de seguridad del task depende de hechos observables, no de
suposiciones del caller. En la ronda 5 quedaban vacíos en:

- puente de razones esenciales Pi hacia ABSTAIN;
- derivación semántica de probes y robustez de SandboxAttestation;
- rechazo recursivo de symlinks en helpers confinados;
- matriz completa de mismatches de CapabilityAttestation;
- fronteras reales de Git porcelain y status matrices de adapters;
- preservación simultánea de razones primarias y de cleanup;
- inventario de bytes realmente acotado, incremental y seguro.

## Decisión

Se adoptó una política estricta de evidencia estructural:

1. **Probes sandbox**
   - `ProbeObservation.status` se deriva del resultado observado y del
     `expected_outcome`.
   - `validate_role_eval_request` valida cada probe requerido con contrato
     exacto (argv y semántica), no solo presencia.
2. **Inventario de bytes**
   - `byte_inventory` migra a `os.scandir` incremental + lectura en chunks.
   - Límites de paths/files/bytes/path-length se aplican antes de leer.
   - Errores stat/read/walk son INCONCLUSIVE fail-closed.
3. **Evidencia host**
   - Si before/after host son INCONCLUSIVE, no se informa `unchanged=true`;
     se usa `host_change_assessment: null`.

## Alternativas descartadas

1. **Mantener validación parcial de probes (solo status/probe_id).**
   - Rechazada: permite tampering estructural sin detección temprana.
2. **Seguir usando rglob/read_bytes para inventario.**
   - Rechazada: no acota asignación previa y oculta límites operativos.
3. **Inferir unchanged cuando before==after aun siendo INCONCLUSIVE.**
   - Rechazada: comunica una certeza no demostrada.

## Consecuencias

- Seguridad: mejora trazabilidad y reduce riesgo de aceptar evidencia falsificada.
- Operación: más escenarios degradan a INCONCLUSIVE de forma explícita.
- Mantenibilidad: mayor complejidad de fixtures, pero contratos más claros y
  testeables.
- Gobernanza: evidencia en vivo y TDD quedan alineadas con principios fail-closed.
