---
name: subir-al-git
description: Guía y asiste al desarrollador en el flujo de publicación en Git, renombrando la rama asignada de origin y subiendo el robot a GitHub con enlace a Pull Request.
---

# 🚀 Skill: Subir Robot al Repositorio Git

Esta skill guía y automatiza el proceso de publicación del robot desarrollado en `data-processing-modules` cuando todas las pruebas (`validate_robot.py` y `test_conversion.py`) hayan pasado con éxito.

---

## 📌 Contexto del Flujo de Ramas en DATAX
1. En GitHub ya existe una rama remota creada para el reporte asignado con el formato `<CODIGO_REPORTE>` (ejemplo: `origin/D_BO_000000270_01`).
2. El estándar de DATAX exige que la rama de trabajo de cada desarrollador lleve su nombre como prefijo:
   `<nombre_desarrollador>/<CODIGO_REPORTE>` (ejemplo: `nicolas/D_BO_000000270_01`, `cristhian/D_BO_000000418_02`, `andresrevollo/D_BO_000000485_01`).
3. Por lo tanto, el flujo consiste en **renombrar la rama de origen** y publicar únicamente los archivos del robot.

---

## 🛠️ Procedimiento Paso a Paso

### Paso 1: Confirmar Nombre y Código de Reporte
Confirmar con el desarrollador:
- Nombre o identificador personal (ej. `nicolas`, `cristhian`, `andres`).
- Código del reporte asignado (ej. `D_BO_000000270_01`).

### Paso 2: Crear y Cambiar a la Rama Renombrada
Si aún no estás en la rama renombrada, crearla a partir de la rama remota base:
```bash
git fetch origin
git checkout -b <nombre>/<CODIGO_REPORTE> origin/<CODIGO_REPORTE>
```

### Paso 3: Verificar Estado y Agregar Archivos
Solo agregar los archivos necesarios para el robot (evitar datos o archivos temporales no requeridos):
```bash
git status

# Si es robot de CONVERSIÓN:
git add robot.py test_conversion.py

# Si es robot de DESCARGA (según el tipo):
git add robot.py test_download_type_*.py
```

### Paso 4: Realizar el Commit
Hacer commit con mensaje estandarizado:
```bash
# Para conversión:
git commit -m "feat(conversion): implement robot for <CODIGO_REPORTE>"

# Para descarga:
git commit -m "feat(download): implement robot for <CODIGO_REPORTE>"
```

### Paso 5: Publicar la Rama en GitHub
Hacer push de la nueva rama configurando el upstream (`-u`):
```bash
git push -u origin <nombre>/<CODIGO_REPORTE>
```

### Paso 6: Crear el Pull Request Automáticamente (para Datax-Migration)
La herramienta `Datax-Migration` busca **Pull Requests abiertos** en GitHub API. Para que aparezca de inmediato en la herramienta, crear el PR vía script o API usando el token de `Datax-Migration/.env`:
```python
import os, requests

# Leer token de Datax-Migration/.env
env_path = r"C:\Users\DATAX\Documents\Nicolas\Datax-Migration\.env"
token = ""
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("GITHUB_TOKEN="):
                token = line.strip().split("=", 1)[1]

headers = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"Bearer {token}",
    "User-Agent": "Datax-Migration-Studio"
}

data = {
    "title": "feat(conversion): implement robot for <CODIGO_REPORTE>",
    "head": "<nombre>/<CODIGO_REPORTE>",
    "base": "main",
    "body": "Implementación del robot para <CODIGO_REPORTE>."
}

resp = requests.post("https://api.github.com/repos/datax-platform/data-processing-modules/pulls", headers=headers, json=data)
if resp.status_code == 201:
    pr_url = resp.json().get("html_url")
    pr_num = resp.json().get("number")
    print(f"PR #{pr_num} creado exitosamente: {pr_url}")
```

### Paso 7: Eliminar la Rama Remota Anterior si Existía (Completar Renombre)
Si existía la rama genérica de `origin`, eliminarla:
```bash
git push origin --delete <CODIGO_REPORTE> 2>$null
```

### Paso 8: Regresar a la Rama `main` y Dejar Workspace en Blanco
Para que el contenedor quede limpio y listo para el siguiente robot o reporte:
1. Regresar a la rama principal:
   ```bash
   git checkout main
   git pull origin main
   ```
2. Verificar que `robot.py` esté en blanco (plantilla base de `main`):
   ```python
   class Robot():
       pass
   ```
3. Limpiar archivos residuales en `attachtments/` y `output/`:
   ```bash
   # Opcional / si el pasante lo solicita
   Remove-Item attachtments/* -Exclude .gitkeep -Force
   Remove-Item output/* -Force
   ```
