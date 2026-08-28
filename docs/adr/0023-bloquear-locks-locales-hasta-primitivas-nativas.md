---
tipo: adr
estado: accepted
fecha: "2026-08-28"
contexto: "Task 4 expone métodos de lock compartido y exclusivo en el adaptador de filesystem, pero Task 8 todavía no incorpora primitivas nativas por plataforma con build tags."
decision: "Los locks locales/nativos deben fallar cerrado con capacidad no soportada hasta que existan primitivas nativas verificables; solo el adaptador de memoria puede simular locks determinísticos en pruebas."
alternativas: "Abrir o crear un archivo .lock sin adquirir un lock del sistema operativo fue descartado porque reporta éxito falso. Implementar flock prematuramente fue descartado porque Task 8 debe introducir primitivas nativas por plataforma de forma coordinada."
consecuencias: "Los comandos que dependan de una instantánea consistente no deben emitir artefactos autoritativos cuando el lock compartido no esté disponible. En entornos locales, inventory falla con salida 3 hasta que Task 8 provea locks nativos reales."
pendientes: "Task 8 debe reemplazar este fallo cerrado con implementaciones nativas compartidas y exclusivas por plataforma, manteniendo las pruebas que impiden éxito falso."
---

## Contexto

Task 4 agregó la interfaz `filesystem.Adapter` con `LockShared` y `LockExclusive` para proteger lecturas de ledger y futuras mutaciones. La implementación local inicial abría o creaba un archivo de lock, pero no adquiría ningún lock compartido o exclusivo del sistema operativo. Ese comportamiento era observable como éxito aunque no protegiera la consistencia de la instantánea.

## Decisión

Hasta que Task 8 incorpore primitivas nativas verificables por plataforma, `NewLocalAdapter().LockShared` y `NewLocalAdapter().LockExclusive` deben devolver capacidad no soportada y no deben crear archivos ni directorios de lock. El adaptador de memoria conserva locks determinísticos para pruebas de servicios e inyección explícita en tests de comando.

Inventory no debe publicar ni escribir un artefacto autoritativo cuando el lock compartido de snapshot del ledger no está disponible. En ese caso devuelve error de capacidad no soportada y mapea el resultado a salida 3.

## Alternativas descartadas

- Abrir o crear un archivo `.lock` sin lock nativo: descartado porque produce una señal de éxito falsa y viola la consistencia fail-closed.
- Implementar `flock` o equivalentes de forma parcial en Task 4: descartado porque la decisión de primitivas nativas pertenece a Task 8 y debe cubrir plataformas mediante build tags.
- Emitir un inventario con blockers después de fallar el lock compartido: descartado porque podría interpretarse como una instantánea autoritativa aunque el ledger no haya estado protegido.

## Consecuencias

La ruta local de inventory falla cerrado hasta que existan locks nativos reales. Las pruebas de éxito de comando deben inyectar explícitamente un adaptador de test con locks determinísticos, mientras que las pruebas de servicio pueden usar `MemoryAdapter`. La frontera de Task 8 queda explícita y se evita que una futura implementación reintroduzca locks aparentes sin exclusión real.
