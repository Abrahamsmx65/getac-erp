# GETAC ERP v1.1.2 — Stock FULL real

## Lógica definitiva

Stock considerado:

- Stock disponible FULL
- Más stock en transferencia dentro de la red de Mercado Libre

No se toma en cuenta ingreso planeado.

## Fórmula

Cantidad sugerida:

Objetivo para 30 días menos:

Disponible + Transferencia

## Incluye

- Transferencia automática desde `not_available_detail`
- Cobertura recalculada con stock considerado
- Excel usando disponible + transferencia
- Correo de las 3:00 AM con la misma lógica
- Prioridades ordenadas:
  - CRITICO
  - ALTO
  - MEDIO
  - OK

## No incluye

- Ingreso planeado
- Captura manual
- Tabla de planeados
