// Builds the globe's country map from Natural Earth's India point-of-view countries file, so India is drawn
// with its official borders (all of Jammu and Kashmir and Ladakh, including Aksai Chin, and Arunachal Pradesh).
// world-atlas only ships Natural Earth's default de facto borders, which cut those areas off.
//
//   1. Download ne_10m_admin_0_countries_ind.geojson (public domain) from
//      https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
//   2. npm i --no-save topojson-server@3.0.1 topojson-simplify@3.0.3
//   3. node scripts/build-countries.mjs path/to/ne_10m_admin_0_countries_ind.geojson
//
// Writes src/geo/countries-110m.json and src/geo/countries-50m.json in the same shape as world-atlas
// (objects.countries, id = ISO 3166-1 numeric as a zero-padded string, properties.name).
import { readFileSync, writeFileSync } from "node:fs";
import { topology } from "topojson-server";
import { presimplify, simplify, quantile, filter, filterWeight } from "topojson-simplify";
import { quantize } from "topojson-client";

const src = JSON.parse(readFileSync(process.argv[2], "utf8"));
const features = src.features.map((f) => {
  const p = f.properties;
  const n = [p.ISO_N3, p.ISO_N3_EH].map(Number).find((v) => v > 0);
  return { type: "Feature", id: n ? String(n).padStart(3, "0") : undefined, properties: { name: p.NAME }, geometry: f.geometry };
});

// Keep a share of the points (by triangle area) close to world-atlas's 50m and 110m files, and drop
// islands too small to matter at that scale.
for (const [name, keep, minArea] of [["50m", 0.1, 0], ["110m", 0.012, 1e-4]]) {
  let topo = presimplify(topology({ countries: { type: "FeatureCollection", features } }));
  topo = simplify(topo, quantile(topo, keep));
  if (minArea) topo = filter(topo, filterWeight(topo, minArea));
  topo = quantize(topo, 1e5);
  const out = JSON.stringify(topo);
  writeFileSync(new URL(`../src/geo/countries-${name}.json`, import.meta.url), out);
  console.log(`countries-${name}.json: ${(out.length / 1024).toFixed(0)} KB, ${topo.objects.countries.geometries.length} countries`);
}
