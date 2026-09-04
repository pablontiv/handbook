---
tipo: adr
estado: accepted
fecha: '2026-09-04'
contexto: 'Los tests de contrato del perfil deben interpretar .workspace/config.yaml como YAML real; el scanner textual anterior dependía de indentación y líneas exactas, mientras la restricción vigente favorece exclusivamente la biblioteca estándar para nuevos tests.'
decision: 'Autorizar PyYAML 6.0.3 como dependencia fijada y exclusiva de tests para cargar configuración con yaml.safe_load; instalarla explícitamente con --no-deps en CI antes de ejecutar tests; prohibir su importación desde código runtime y mantener la biblioteca estándar como opción preferida fuera de esta excepción acotada.'
alternativas: 'Extender el scanner textual se descarta porque conservaría un subconjunto artesanal y frágil de YAML. Cambiar el formato de configuración se descarta porque rediseñaría el contrato aprobado. Usar un parser de otro runtime se descarta porque reduciría portabilidad y añadiría una dependencia implícita mayor.'
consecuencias: 'Los contratos toleran comentarios e indentación YAML válida y detectan campos prohibidos estructuralmente; CI realiza una descarga externa fijada que falla cerrado si el paquete no está disponible; el runtime del handbook no adquiere dependencias Python; futuras excepciones a la biblioteca estándar requieren su propia decisión gobernada.'
---
# 0023. Adoptar PyYAML fijado para contratos YAML

## Contexto
Los tests de contrato del perfil deben interpretar .workspace/config.yaml como YAML real; el scanner textual anterior dependía de indentación y líneas exactas, mientras la restricción vigente favorece exclusivamente la biblioteca estándar para nuevos tests.

## Decisión
Autorizar PyYAML 6.0.3 como dependencia fijada y exclusiva de tests para cargar configuración con yaml.safe_load; instalarla explícitamente con --no-deps en CI antes de ejecutar tests; prohibir su importación desde código runtime y mantener la biblioteca estándar como opción preferida fuera de esta excepción acotada.

## Alternativas descartadas
Extender el scanner textual se descarta porque conservaría un subconjunto artesanal y frágil de YAML. Cambiar el formato de configuración se descarta porque rediseñaría el contrato aprobado. Usar un parser de otro runtime se descarta porque reduciría portabilidad y añadiría una dependencia implícita mayor.

## Consecuencias
Los contratos toleran comentarios e indentación YAML válida y detectan campos prohibidos estructuralmente; CI realiza una descarga externa fijada que falla cerrado si el paquete no está disponible; el runtime del handbook no adquiere dependencias Python; futuras excepciones a la biblioteca estándar requieren su propia decisión gobernada.
