# Verificación pública de Inference Providers

**Consulta:** 2026-09-09 (UTC) · **Alcance:** metadatos y documentación pública, sin autenticación ni inferencia.

## Disponibilidad publicada

La [API pública del modelo Qwen2.5-1.5B-Instruct](https://huggingface.co/api/models/Qwen/Qwen2.5-1.5B-Instruct?expand%5B%5D=inferenceProviderMapping) devolvió esta selección de datos:

```json
{
  "id": "Qwen/Qwen2.5-1.5B-Instruct",
  "inferenceProviderMapping": {
    "featherless-ai": {
      "status": "live",
      "providerId": "Qwen/Qwen2.5-1.5B-Instruct",
      "task": "conversational",
      "isModelAuthor": false
    }
  }
}
```

**Interpretación:** hay un proveedor anunciado en los metadatos consultados. No permite concluir que el token del equipo tenga acceso, que el precio sea adecuado o que p95 esté dentro de la ventana de juego. R1 debe repetir la consulta y hacer el spike autorizado con su cuenta.

Reproducción sin token ni generación:

```bash
curl --globoff --fail --silent --show-error 'https://huggingface.co/api/models/Qwen/Qwen2.5-1.5B-Instruct?expand[]=inferenceProviderMapping' | python3 -m json.tool
```

## Créditos publicados

La [tabla oficial de precios](https://huggingface.co/docs/inference-providers/pricing) muestra USD 0,10 de créditos mensuales para Free y USD 2,00 para PRO, sujetos a cambio. Por tanto, “inferior a 0,10” no coincide con esta consulta. Esta cifra no es una tarifa por llamada ni demuestra que los experimentos quepan en el saldo.

## Datos que siguen sin medir

- Inferencias realizadas en esta revisión: **0**.
- Acceso autenticado del equipo y selección efectiva del proveedor: pendiente.
- Latencia p50/p95, TTFT, tasa de error y consumo por llamada: pendientes.
- Licencia del modelo finalmente elegido y calidad sobre el set: pendientes de R1/R3.
- Tamaño y costo del Droplet sin modelo: pendientes de R4; requieren considerar UI, MLflow, base de datos y Runner.

No se debe presentar esta consulta como un benchmark aprobado ni completar con números supuestos ADR-001 o A2.
