---
tipo: adr
estado: accepted
fecha: "2026-08-28"
contexto: "Task 4 introduce salida de artefactos read-only para inventory con confinamiento de destino, staging en el mismo padre, fsync y publicación sin reemplazo."
decision: "Usar un archivo staging creado con semántica create-new en el mismo directorio padre y publicar el destino mediante hard link no-replace, eliminando después el staging."
alternativas: "Usar rename fue descartado porque puede reemplazar destinos existentes según plataforma. Escribir directamente el destino con O_EXCL fue descartado porque no mantiene el patrón staging requerido y puede dejar un destino parcial ante fallos de escritura."
consecuencias: "La implementación evita reemplazos ciegos y mantiene confinamiento antes de publicar. Plataformas donde hard link no provea una prueba suficiente deben fallar cerrado como capacidad no soportada hasta que primitivas nativas más específicas sean incorporadas."
pendientes: "Task 8 debe ampliar las primitivas nativas de publicación y locks para cubrir mutaciones completas por plataforma."
---

## Contexto

Task 4 habilita `inventory --out <file>` como la única escritura persistente permitida para un comando read-only. La especificación exige que el destino sea absoluto, esté fuera de raíces prohibidas, use staging en el mismo padre, fsync, publicación no-replace y sincronización del directorio padre.

## Decisión

Waywarden crea un archivo staging privado en el mismo directorio padre con `O_CREATE|O_EXCL`, escribe los bytes canónicos completos, sincroniza el archivo y publica el destino mediante un hard link. Si el destino existe, la publicación falla sin reemplazarlo. Después de la publicación se sincroniza el directorio padre y se elimina el staging.

## Alternativas descartadas

- `os.Rename`: descartado porque puede reemplazar el destino y el brief prohíbe depender de semánticas de reemplazo ciegas.
- Escritura directa al destino con `O_EXCL`: descartada porque no proporciona el patrón de staging requerido y un error de escritura podría dejar un destino parcial.
- Copia best-effort con verificación posterior: descartada porque no prueba publicación atómica no-replace.

## Consecuencias

La publicación mantiene una frontera clara entre bytes canónicos ya construidos y el destino autoritativo. En plataformas donde el hard link no sea una prueba suficiente o no esté disponible, la operación debe fallar cerrado como capacidad no soportada hasta que Task 8 introduzca primitivas nativas completas.
