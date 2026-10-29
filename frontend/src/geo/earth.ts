import { COUNT, DOTS, IDS } from "./earth-data";
import { TLD_TO_ISO } from "./cc";

// The globe's dots: an even Fibonacci sphere, each dot tagged with the country it falls in (or ocean).
// Which country is precomputed by scripts/build-earth.mjs from Natural Earth (world-atlas), so the browser
// neither downloads the map nor draws it.

export interface Earth {
  positions: Float32Array;     // xyz per dot, unit sphere
  country: Int16Array;         // index into `ids` per dot, -1 = ocean
  ids: number[];               // ISO 3166-1 numeric per country index
  byCountry: Map<number, number[]>; // ISO numeric -> dot indexes on its land
  land: number[];              // all land dot indexes
}

export function latLonToXYZ(lat: number, lon: number, r = 1): [number, number, number] {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  return [-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)];
}

let cached: Earth | null = null;

export function buildEarth(): Earth {
  if (cached) return cached;
  const raw = Uint8Array.from(atob(DOTS), (c) => c.charCodeAt(0));
  const positions = new Float32Array(COUNT * 3);
  const country = new Int16Array(COUNT);
  const byCountry = new Map<number, number[]>();
  const land: number[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < COUNT; i++) {
    const y = 1 - (i / (COUNT - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    positions[i * 3] = Math.cos(golden * i) * r;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = Math.sin(golden * i) * r;
    const idx = raw[i];
    if (idx === 255) { country[i] = -1; continue; }
    country[i] = idx;
    land.push(i);
    const iso = IDS[idx];
    if (!byCountry.has(iso)) byCountry.set(iso, []);
    byCountry.get(iso)!.push(i);
  }
  cached = { positions, country, ids: IDS, byCountry, land };
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
