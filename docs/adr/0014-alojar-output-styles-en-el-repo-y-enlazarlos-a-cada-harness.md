---
tipo: adr
estado: accepted
fecha: "2026-08-22"
contexto: "El output style mentor-telemetria se propaga por copia manual entre harnesses: existen tres copias vivas del mismo esquema ADR, dos fuera de control de versiones, y la que Claude Code carga divergió hasta invalidar todo bootstrap de ADR."
decision: "Alojar los output styles en este repositorio bajo output-styles/ como fuente única de verdad, y que cada harness los consuma por symlink en lugar de copia."
consecuencias: "Un arreglo se propaga a todos los harnesses y queda auditable en git, pero el repositorio pasa a publicar un artefacto que no es una skill y el enlazado queda fuera de la garantía de portabilidad multiplataforma."
---

# Alojar output styles en el repo y enlazarlos a cada harness

## Contexto

El output style `mentor-telemetria` define comportamiento operativo del agente:
protocolo de ADR, formato de telemetría, modos operativos y criterios de
decisión. Es configuración ejecutable, no documentación.

Hoy se propaga por copia manual. Un relevamiento del 2026-08-22 encontró tres
copias vivas de su esquema ADR:

| Ubicación | Esquema | Versionado |
|---|---|---|
| `docs/adr/.stem` de este repositorio | correcto | sí |
| `~/.pi/agent/mentor-telemetria.assets/adr.stem` | correcto | no |
| `~/.claude/output-styles/mentor-telemetria.assets/adr.stem` | inválido | no |

La copia que Claude Code carga declara los enums con `enum:`, mientras que
rootline v2 lee los valores admitidos de `values:`, y omite `root: true`. El
efecto es que ningún documento puede validar: el bootstrap de ADR que el propio
output style ordena queda roto de origen. El defecto se detectó al inicializar
`docs/adr/` en otro repositorio siguiendo el protocolo al pie de la letra.

El archivo `mentor-telemetria.md` agrava el cuadro: existe únicamente en
`~/.claude/output-styles/`, sin repositorio ni gestión por chezmoi, pese a que
`dot_claude/` sí gestiona `agents`, `hooks` y `skills`.

El modo de falla no es la ignorancia sino la deriva silenciosa. El esquema
correcto existía en dos lugares y aun así el harness principal cargaba el roto,
sin señal de que las copias hubieran divergido.

## Decisión

Los output styles viven en este repositorio bajo `output-styles/`, con la misma
estructura que consumen los harnesses: el documento y su directorio de assets
adyacente.

Cada harness consume esa fuente por symlink, no por copia. El repositorio es la
única ruta donde se edita; los harnesses sólo apuntan.

## Alternativas descartadas

**Gestionar los output styles con chezmoi en `dotfiles/dot_claude/`.** Es donde
ya viven `agents`, `hooks` y `skills`, y chezmoi sabe desplegar. Se descarta
porque `dot_claude/` es específico de Claude Code: Pi volvería a quedar fuera y
la duplicación reaparecería con otro nombre.

**Arreglar sólo el `.stem` divergente.** Son tres líneas y resuelve el síntoma
de hoy. Se descarta porque sin origen único el mismo arreglo debe repetirse en
cada harness, cada vez, sin forma de saber cuántos son ni cuáles derivaron.

**Copiar desde el repositorio mediante un paso de instalación.** Conserva la
portabilidad multiplataforma, pero reintroduce copias que pueden divergir entre
sincronizaciones: es el problema que se busca eliminar.

**Distribuir el repositorio como plugin de Claude Code.** El runtime reconoce
como contenido de plugin cualquier directorio con `output-styles/`, `skills/` o
`commands/` en la raíz, y este repositorio ya tiene esa forma; el usuario ya
consume repositorios ajenos de skills por esa vía. Resolvería la portabilidad
sin symlinks y encuadraría `output-styles/` como ciudadano de primera del
formato. Se descarta por costo: exige manifiesto, versionado de plugin y
registro de marketplace, y Pi no tiene un mecanismo equivalente, de modo que el
symlink haría falta igual. Queda como evolución natural si el mantenimiento del
enlazado se vuelve molesto.

## Consecuencias

Un arreglo se aplica una vez y alcanza a todos los harnesses enlazados. El
historial de git vuelve auditable un artefacto que hoy cambia sin registro, y
la divergencia entre harnesses deja de ser posible por construcción.

El repositorio pasa a publicar un artefacto que no es una skill, lo que amplía
su propósito declarado —«publishes independent, portable Agent Skills»— más
allá de `skills/<name>/`. `output-styles/` se mantiene como zona separada para
que la distinción quede explícita.

El enlazado queda fuera de la garantía de portabilidad del repositorio. Los
symlinks a rutas del home son específicos del host, y en Windows requerirían
junctions o copia. El repositorio conserva únicamente contenido portable; el
enlace es una operación de instalación en el host, no código de skill.

La política de seguridad de este repositorio exige respaldar y verificar
archivos gobernados antes de mutarlos. Reemplazar archivos reales por symlinks
es una mutación destructiva: cada archivo sustituido debe respaldarse y
verificarse antes, y la fuente que se conserve debe ser la correcta —el `.md`
sólo existe en Claude Code, el `.stem` válido sólo en Pi y en este repositorio.

La resolución de symlinks quedó verificada en ambos harnesses antes de aceptar
esta decisión. Claude Code enumera los output styles con ripgrep bajo
`--files --hidden --follow --no-ignore --glob "*.md"` y valida cada candidato
con `fs.stat`, no `lstat`: ambos puntos siguen el enlace deliberadamente. Pi no
aloja el documento, sólo consume el directorio de assets por ruta absoluta, que
el sistema operativo resuelve de forma transparente.

Subsiste una incertidumbre acotada: la ruta primaria de Claude Code usa un
servicio de listado indexado sobre `userConfigDir`, y el escaneo con ripgrep es
su fallback. Si ese índice no siguiera enlaces, el síntoma sería que el output
style deja de aparecer en la lista tras enlazarlo, y la mitigación es copiar el
documento y conservar el symlink sólo para los assets.
