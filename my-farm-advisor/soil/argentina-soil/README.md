# argentina-soil

INTA **Cartas de Suelos de Entre Ríos, escala 1:100.000** provider for
My Farm Advisor. It is the Argentine SSURGO analog used when a field carries
`country=AR`.

## What it does

- Queries the INTA GeoNode WFS
  (`https://geo-nodo03.inta.gob.ar/geoserver/ows`, layer
  `geonode:carta_de_suelos_unocienmil_…`) for the soil map units intersecting
  each field, with an on-disk bbox cache under
  `shared/argentina/inta/`.
- Clips map units to field boundaries in EPSG:4326 and computes field-area
  shares in the field's local UTM CRS.
- Expands up to seven component series per map unit into SSURGO-schema
  horizon rows using analytical profiles transcribed from the INTA series
  fact sheets (`DATOS ANALYTICOS DEL PERFIL TIPICO`).
- Estimates available water capacity from the USDA texture class. The
  measured moisture equivalent from the PDFs is retained in the module for
  audit but is not substituted for AWC.
- Writes machine-readable provenance for the run.

Outputs carry:

| column | meaning |
|---|---|
| `soil_source` | `inta_entre_rios_100k` |
| `mukey` | namespaced `AR-ER-<ogc_fid>` |
| `muname` | INTA map-unit name |
| `compname` | soil series name |
| `comppct_r` | series percentage within the map unit |
| `soil_area_share` | series share of the field area (0-1) |
| horizon columns | `hzdept_r`, `hzdepb_r`, `om_r`, `ph1to1h2o_r`, `awc_r`, `claytotal_r`, `sandtotal_r`, `silttotal_r`, `cec7_r`, `dbthirdbar_r` |

## Scope and limits

- The INTA layer only covers **Entre Ríos province**. Fields elsewhere in
  Argentina return no rows and fall through to SoilGrids 250 m.
- The provider writes a survey analog, not a laboratory test. Confirm
  management decisions with field sampling.
- `field_polygon_intersections` returns clipped polygons with `soil_source`,
  `mukey`, `compname`, topsoil properties, and drainage class, so the same
  maps, cards, and texture triangles used for SSURGO work unchanged.

## Source documents

| Series | INTA document |
|---|---|
| La Monona | <https://geo-nodo03.inta.gob.ar/documents/201/download> |
| Estancia Retiro | <https://geo-nodo03.inta.gob.ar/documents/127/download> |
| Larroque | <https://geo-nodo03.inta.gob.ar/documents/215/download> |
| La Laura | <https://geo-nodo03.inta.gob.ar/documents/196/download> |
| San Simón | <https://geo-nodo03.inta.gob.ar/documents/304/download> |

Dataset: <https://geo-nodo03.inta.gob.ar/catalogue/#/dataset/347>

## Usage

```python
import argentina_soil

rows = argentina_soil.download_soil_argentina(fields_gdf, cache_dir=cache_dir)
polys = argentina_soil.field_polygon_intersections(fields_gdf, cache_dir=cache_dir)
argentina_soil.write_provenance(manifest_dir / "inta_soil_provenance.json")
```

See `../soil-routing.md` for the country decision table and
`../../data-pipeline/references/argentina-data-sources.md` for the full
runbook.
