# 🏛️ Monitor Legislativo Uruguay

Portal interactivo para seguimiento de la actividad parlamentaria uruguaya: leyes promulgadas, proyectos de ley, decretos, venias y resoluciones.

## Características

- **289 items legislativos** del período 2025-2026
- **Dos pestañas**: Universo Completo e Impacto Económico/Empresarial
- **Panel de detalle** con resumen, datos de votación por partido y link a fuente oficial
- **Filtros** por tipo, categoría, fuente y búsqueda de texto
- **Modo oscuro** automático
- **Responsive** — funciona en celular, tablet y desktop
- **Actualización automática** vía GitHub Actions (lunes a viernes, 8:00 AM UY)

## Estructura

```
├── index.html                          # Portal (archivo único autocontenido)
├── data/
│   └── legislative_data.json           # Datos legislativos (fuente de verdad)
├── scripts/
│   └── update.py                       # Script de actualización automática
├── .github/
│   └── workflows/
│       └── update.yml                  # GitHub Actions — cron diario
└── README.md
```

## Actualización automática

El workflow de GitHub Actions corre de lunes a viernes a las 8:00 AM (hora de Uruguay):

1. Consulta `parlamento.gub.uy/documentosyleyes/leyes` para detectar nuevas leyes promulgadas
2. Clasifica cada ley nueva por categoría e impacto económico
3. Genera un resumen breve y URL específica
4. Actualiza `data/legislative_data.json` y `index.html`
5. Hace commit automático con los cambios

### Ejecutar manualmente

Desde la pestaña **Actions** del repositorio, seleccionar "Actualización Diaria Monitor Legislativo" → "Run workflow".

También se puede ejecutar localmente:

```bash
python scripts/update.py
```

## Hosting con GitHub Pages

El portal se sirve automáticamente desde GitHub Pages. El link público es:

```
https://TU_USUARIO.github.io/monitor-legislativo/
```

## Fuentes de datos

- [Parlamento del Uruguay](https://parlamento.gub.uy) — Leyes promulgadas, fichas de asunto
- [IMPO](https://impo.com.uy) — Textos actualizados de decretos
- [Presidencia](https://gub.uy/presidencia) — Resoluciones del ejecutivo

## Licencia

Datos de dominio público. Código bajo MIT.
