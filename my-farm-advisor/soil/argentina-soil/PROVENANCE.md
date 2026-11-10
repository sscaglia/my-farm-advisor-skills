# Provenance

## Module

`src/argentina_soil.py` — INTA Entre Ríos soil survey provider.

## Upstream data

- **Dataset**: Suelos de Entre Ríos Escala 1:100000, dataset 347 on the INTA
  GeoNode node 03.
  <https://geo-nodo03.inta.gob.ar/catalogue/#/dataset/347>
- **WFS**: <https://geo-nodo03.inta.gob.ar/geoserver/ows>
- **Layer**: `geonode:carta_de_suelos_unocienmil_df05b067570a0dea80e67f5aa41aa5d6`
- **Citation**: Bedendo DJ, Schulz GA, Pausich GM, Tentor F. (2014). *Cartas
  de Suelos de Entre Ríos, Escala 1:100.000*. INTA.
- **License / access**: public domain, keyless WFS.
- **Accessed**: 2026-11-08.

## Series analytical profiles

Transcribed from the `DATOS ANALITICOS DEL PERFIL TIPICO` page of each INTA
series fact sheet (accessed 2026-11-08):

| Series | Document |
|---|---|
| La Monona | <https://geo-nodo03.inta.gob.ar/documents/201/download> |
| Estancia Retiro | <https://geo-nodo03.inta.gob.ar/documents/127/download> |
| Larroque | <https://geo-nodo03.inta.gob.ar/documents/215/download> |
| La Laura | <https://geo-nodo03.inta.gob.ar/documents/196/download> |
| San Simón | <https://geo-nodo03.inta.gob.ar/documents/304/download> |

Percentages are reported on a `< 2 µm` (clay), `2-50 µm` (silt), and
`50-2000 µm` (sand) basis and normalised to 100 %. Horizon depths, organic
matter, pH, CEC, and calcium carbonate are transcribed directly.

## Derived values

- **AWC** is a look-up by USDA texture class (`AWC_BY_TEXTURE`). This is a
  documented estimate; the measured moisture equivalent from the PDFs is kept
  in the module for audit.
- **Bulk density** is a texture-based placeholder (1.35 g/cm³ topsoil,
  1.45 g/cm³ subsoil) because the INTA fact sheets do not publish it.
- **`dbthirdbar_r`** and **`awc_r`** should be treated as estimates, not lab
  measurements.

## Fields covered (assignment run)

Three fields in Departamento Gualeguaychú, Entre Ríos, imported from a
grower-supplied `NewFields.gpkg` (layer `lote_simple_mariano`). Map-unit
composition at those fields:

| Field | Composition |
|---|---|
| `ar-r1` | 97.4 % La Monona + 2.6 % Asociación Estancia Retiro |
| `ar-r2` | 100 % La Monona |
| `ar-r3` | 68.8 % La Monona + 31.2 % Asociación La Monona |

## Unavailable endpoints

- `geointa.inta.gov.ar/geoparana/ows` — unreachable.
- `geo.inta.gob.ar/geoserver/ows` — HTTP 404.
- SISINTA download host does not resolve; the series PDFs above are the
  practical source for analytical profiles.
