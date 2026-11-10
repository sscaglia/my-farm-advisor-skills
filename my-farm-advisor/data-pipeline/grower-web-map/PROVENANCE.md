# Provenance

## Origin

Original in-repository workflow created for the My Farm Advisor data pipeline.
It is not a vendored or imported Superior Byteworks skill.

## References

- Leaflet 1.9.4 — <https://leafletjs.com/>
- Esri World Imagery — <https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9>
- Esri World Street Map — <https://www.arcgis.com/home/item.html?id=3b93337983e9436f8db950e38a8629af>
- Existing interactive web-map guidance in this repository:
  `../../admin/interactive-web-map/GUIDE.md`

The Field Atlas layout, warm-paper palette, custom basemap toggle, combined
grower switcher, and hash-link behavior are original to this workflow. The
existing interactive web-map example was reviewed only as a Leaflet baseline;
its yellow-on-satellite styling is deliberately not reused.

## Data

Field boundaries, grower metadata, farm metadata, and field inventories are
read from the local data-pipeline runtime. They are not committed to this
repository.
