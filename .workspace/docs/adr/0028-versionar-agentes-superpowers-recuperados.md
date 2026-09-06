---
tipo: adr
estado: accepted
fecha: '2026-09-04'
contexto: 'La migración global a pi-subagents eliminó seis definiciones locales Superpowers sin respaldo de archivos; posteriormente se recuperaron sus bytes exactos desde una captura de sesión corroborada por el SQLite legado, y el propietario confirmó autoría y publicación bajo MIT.'
decision: 'Crear una familia top-level agents propiedad del Handbook y versionar allí los seis archivos recuperados sin modificarlos, junto con documentación y procedencia portable; esta entrega no registra, instala, enlaza, adapta ni activa agentes en ningún runtime.'
alternativas: 'Adaptarlos ahora se descarta porque mezclaría preservación con comportamiento nuevo. Activarlos globalmente se descarta porque requiere un gate runtime independiente. Mantenerlos solo en un backup privado se descarta porque el propietario decidió convertir el Handbook en su fuente pública canónica.'
consecuencias: 'El contenido histórico queda preservado y auditable bajo la licencia MIT del repositorio; la familia agents declara su frontera Pi y su estado inactivo; cualquier adaptación, distribución o reemplazo de builtins requerirá una decisión y entrega posteriores.'
---
# 0028. Versionar agentes superpowers recuperados

## Contexto
La migración global a pi-subagents eliminó seis definiciones locales Superpowers sin respaldo de archivos; posteriormente se recuperaron sus bytes exactos desde una captura de sesión corroborada por el SQLite legado, y el propietario confirmó autoría y publicación bajo MIT.

## Decisión
Crear una familia top-level agents propiedad del Handbook y versionar allí los seis archivos recuperados sin modificarlos, junto con documentación y procedencia portable; esta entrega no registra, instala, enlaza, adapta ni activa agentes en ningún runtime.

## Alternativas descartadas
Adaptarlos ahora se descarta porque mezclaría preservación con comportamiento nuevo. Activarlos globalmente se descarta porque requiere un gate runtime independiente. Mantenerlos solo en un backup privado se descarta porque el propietario decidió convertir el Handbook en su fuente pública canónica.

## Consecuencias
El contenido histórico queda preservado y auditable bajo la licencia MIT del repositorio; la familia agents declara su frontera Pi y su estado inactivo; cualquier adaptación, distribución o reemplazo de builtins requerirá una decisión y entrega posteriores.
