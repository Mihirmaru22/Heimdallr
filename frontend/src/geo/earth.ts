import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import type { Feature, MultiPolygon, Polygon } from "geojson";
import countries from "world-atlas/countries-110m.json";
import { TLD_TO_ISO } from "./cc";

// The globe's dots: an even Fibonacci sphere, each dot tagged with the country it falls in (or ocean).
// Countries come from Natural Earth via world-atlas (public domain data, ISC package), rasterised once into a
// small canvas where each country is painted in its own colour, so a dot's country is one pixel lookup.

export interface Earth {
  positions: Float32Array;     // xyz per dot, unit sphere
  country: Int16Array;         // index into `ids` per dot, -1 = ocean
  ids: number[];               // ISO 3166-1 numeric per country index
  byCountry: Map<number, number[]>; // ISO numeric -> dot indexes on its land
  land: number[];              // all land dot indexes
}

const W = 1024;
const H = 512;

export function latLonToXYZ(lat: number, lon: number, r = 1): [number, number, number] {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  return [-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)];
}

let cached: Earth | null = null;

export function buildEarth(count = 22000): Earth {
  if (cached) return cached;
  const topo = countries as unknown as Topology<{ countries: GeometryCollection }>;
  const fc = feature(topo, topo.objects.countries) as unknown as { features: Feature<Polygon | MultiPolygon>[] };
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, W, H);
  const ids: number[] = [];
  fc.features.forEach((f, i) => {
    ids.push(Number(f.id));
    // Colour = index + 1 in red/blue, green 255 as a marker: anti-aliased edge pixels lose the exact 255
    // and read as ocean, so no dot is ever given a neighbour's country.
    const n = i + 1;
    ctx.fillStyle = `rgb(${n & 255},255,${n >> 8})`;
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    ctx.beginPath();
    for (const poly of polys) {
      for (const ring of poly) {
        let prevLon: number | null = null;
        ring.forEach(([lon, lat], k) => {
          const x = ((lon + 180) / 360) * W;
          const y = ((90 - lat) / 180) * H;
          // A ring that crosses the antimeridian would smear across the map; start a new stroke instead.
          if (k === 0 || (prevLon !== null && Math.abs(lon - prevLon) > 180)) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
          prevLon = lon;
        });
        ctx.closePath();
      }
    }
    ctx.fill("evenodd");
  });
  const pixels = ctx.getImageData(0, 0, W, H).data;

  const positions = new Float32Array(count * 3);
  const country = new Int16Array(count);
  const byCountry = new Map<number, number[]>();
  const land: number[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const t = golden * i;
    const x = Math.cos(t) * r;
    const z = Math.sin(t) * r;
    positions.set([x, y, z], i * 3);
    const lat = (Math.asin(y) * 180) / Math.PI;
    // Inverse of latLonToXYZ: x = -sin(phi)cos(theta), z = sin(phi)sin(theta).
    let lon = (Math.atan2(z, -x) * 180) / Math.PI - 180;
    if (lon < -180) lon += 360;
    const px = Math.min(W - 1, Math.max(0, Math.floor(((lon + 180) / 360) * W)));
    const py = Math.min(H - 1, Math.max(0, Math.floor(((90 - lat) / 180) * H)));
    const o = (py * W + px) * 4;
    if (pixels[o + 1] === 255) {
      const idx = pixels[o] + (pixels[o + 2] << 8) - 1;
      country[i] = idx;
      land.push(i);
      const iso = ids[idx];
      if (!byCountry.has(iso)) byCountry.set(iso, []);
      byCountry.get(iso)!.push(i);
    } else {
      country[i] = -1;
    }
  }
  cached = { positions, country, ids, byCountry, land };
  return cached;
}

function hash(s: string, seed: number) {
  let h = 2166136261 ^ seed;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

// Where a site sits: on its country's land when the domain ends in a country code (.de, .co.in, .uk),
// otherwise on a dot picked from the name (within `pool` when given, e.g. the countries a run is limited to),
// so the same site always lands in the same place.
export function siteDot(earth: Earth, site: string, pool?: number[]): number {
  const tld = site.split(".").pop()?.toLowerCase() ?? "";
  const iso = TLD_TO_ISO[tld];
  const dots = (iso !== undefined && earth.byCountry.get(iso)) || (pool?.length ? pool : earth.land);
  return dots[hash(site, 7) % dots.length];
}

// Dots of the countries a run is limited to (two-letter codes as the plan stores them).
export function focusDots(earth: Earth, alpha2: string[]): Set<number> {
  const out = new Set<number>();
  for (const c of alpha2) {
    const iso = TLD_TO_ISO[c.toLowerCase()];
    for (const i of (iso !== undefined && earth.byCountry.get(iso)) || []) out.add(i);
  }
  return out;
}
