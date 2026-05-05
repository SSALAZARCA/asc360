# Reglas del Proyecto

## Workflow obligatorio después de cada cambio

Al terminar CUALQUIER modificación de código, sin excepción y sin esperar que el usuario lo pida:

1. `git add <archivos específicos modificados>` — nunca `git add -A` a ciegas
2. `git commit -m "tipo(scope): descripción"` — conventional commits
3. `git push`

**Por qué:** Coolify hace deploy automático desde el repositorio. Sin push, los cambios no llegan a producción.
