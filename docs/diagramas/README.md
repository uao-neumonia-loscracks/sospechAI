# Diagramas (A31)

Fuentes JSON de los diagramas generados con [Archify](https://skills.sh/tt-a1i/archify) v2.17.
El HTML generado vive en `docs/` y no se edita a mano: se regenera desde estas fuentes.

| Fuente | Salida | Tipo |
|---|---|---|
| `arquitectura.architecture.json` | `docs/arquitectura.html` | Servicios, contrato gRPC, Inference API, SQLite y MLflow |
| `secuencia-impostor.sequence.json` | `docs/arquitectura-secuencia.html` | Ruta de una respuesta del impostor hasta el chunk final con trailing metadata |

Regenerar (con la skill instalada: `npx skills add tt-a1i/archify -g`):

```bash
A=~/.agents/skills/archify
node $A/bin/archify.mjs deliver architecture docs/diagramas/arquitectura.architecture.json \
  docs/arquitectura.html --quality showcase --repo-root .
node $A/bin/archify.mjs deliver sequence docs/diagramas/secuencia-impostor.sequence.json \
  docs/arquitectura-secuencia.html --quality showcase
```

Ambos pasan la validación `showcase` (9/9 comprobaciones) y `visual-check` a
1440×900, 1600×1000, 1920×1080 y 2048×1320. La interfaz del visor (botones,
leyenda) queda en inglés porque Archify no traduce su propia interfaz al
español; el contenido del diagrama está en español.
