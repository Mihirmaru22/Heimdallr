import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { buildEarth, focusDots, siteDot, type Earth } from "./earth";

// The research globe (see DESIGN.md). Everything the worker does lands on it:
//   search  -> the source's satellite flashes and fires beams at the ground, a scan ring sweeps the globe
//   read    -> the crawler hops from the last site it read to this one, the site lights up
//   kept    -> a ripple and a pillar at the site, a beam carries it up to "your sheet", a label pops
//   found   -> a burst of sparks at the site
//   dropped -> the site dims and a grey ripple; blocked / failed -> a red ripple
// One requestAnimationFrame loop drives all of it; it pauses off screen and when the tab is hidden.

export interface GlobeSignal { id: number; kind: string; site?: string | null; source?: string | null; at?: string }

type SiteState = "seen" | "kept" | "dropped" | "bad";
const STATE_OF: Record<string, SiteState | undefined> = {
  queued: "seen", read: "seen", links: "seen", kept: "kept", found: "kept", records: undefined,
  dropped: "dropped", skipped: "dropped", blocked: "bad", failed: "bad",
};
const RANK: Record<SiteState, number> = { seen: 0, dropped: 1, bad: 2, kept: 3 };

export const STAGE = {
  bg: 0x06070a, core: 0x0a0c11, land: 0xc9d1dd, ocean: 0x1c222b, focus: 0xff7a45, seen: 0xeaf1fb, kept: 0xff7a45,
  found: 0xffc56b, dropped: 0x4a515c, bad: 0xff5b57, search: 0x69b0ff, glow: 0x5d9cff, hop: 0xb8c7dd,
};

const MAX_SITES = 900;
const ARCS = 56;
const SEG = 64;
const RIPPLES = 40;
const BURSTS = 14;
const SPARKS = 22;

const POINT_VERT = /* glsl */ `
attribute vec3 aColor;
attribute float aSize;
attribute float aBorn;
uniform float uTime;
uniform float uBeam;
uniform float uPulse;
uniform float uPixel;
uniform float uHeight;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vec3 n = normalize(world.xyz);
  float ang = atan(world.x, world.z);
  float d = abs(mod(ang - uBeam + 3.14159, 6.28318) - 3.14159);
  float beam = smoothstep(0.5, 0.0, d);
  float age = aBorn < 0.0 ? 1.0 : clamp((uTime - aBorn) / 0.6, 0.0, 1.0);
  float pop = age * (1.0 + 2.2 * (1.0 - age));
  float pt = uTime - uPulse;
  float lat = asin(clamp(n.y, -1.0, 1.0));
  float ring = (pt > 0.0 && pt < 1.8) ? smoothstep(0.1, 0.0, abs(lat - (1.7 - pt * 1.95))) * (1.0 - pt / 1.8) : 0.0;
  vec3 toCam = normalize(cameraPosition - world.xyz);
  float facing = clamp(dot(n, toCam), 0.0, 1.0);
  vColor = aColor + vec3(0.45, 0.65, 1.0) * ring * 0.9 + vec3(0.15) * beam;
  vAlpha = (0.25 + 0.75 * facing) * (0.75 + 0.25 * beam + ring);
  vec4 mv = viewMatrix * world;
  gl_PointSize = aSize * pop * uPixel * (uHeight / 820.0) * (4.2 / -mv.z) * (1.0 + 0.8 * ring);
  gl_Position = projectionMatrix * mv;
}`;

const POINT_FRAG = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;
void main() {
  float r = length(gl_PointCoord - 0.5);
  if (r > 0.5) discard;
  gl_FragColor = vec4(vColor, smoothstep(0.5, 0.28, r) * vAlpha);
}`;

const GLOW_VERT = /* glsl */ `
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;
// The outer halo is drawn from its back faces: there the view ray meets the normal head-on near the globe and
// side-on at the halo's own edge, so the glow is brightest at the planet and fades out into space.
const HALO_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uPower;
uniform float uStrength;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  float t = clamp(-dot(vNormal, vView) / 0.57, 0.0, 1.0);
  gl_FragColor = vec4(uColor, pow(t, uPower) * uStrength);
}`;
const GLOW_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uPower;
uniform float uStrength;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  float rim = 1.0 - abs(dot(vNormal, vView));
  gl_FragColor = vec4(uColor, pow(rim, uPower) * uStrength);
}`;

interface Arc {
  line: THREE.Line; mat: THREE.LineBasicMaterial; pts: THREE.Vector3[]; t: number; dur: number; tail: number;
  live: boolean; color: THREE.Color; onDone?: () => void;
}
interface Ripple { mesh: THREE.Mesh; mat: THREE.MeshBasicMaterial; t: number; dur: number; size: number; live: boolean }
interface Burst { origin: THREE.Vector3; vel: THREE.Vector3[]; t: number; live: boolean }
interface Satellite {
  name: string; pivot: THREE.Group; node: THREE.Mesh; halo: THREE.Mesh; speed: number; flash: number; label: HTMLDivElement;
}
interface Label { el: HTMLDivElement; local: THREE.Vector3; born: number; ttl: number }

function hashOf(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967296;
}

export class GlobeScene {
  private host: HTMLElement;
  private labelsLayer: HTMLDivElement;
  private renderer: THREE.WebGLRenderer;
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  private earthGroup = new THREE.Group();
  private earth: Earth;
  private uniforms = { uTime: { value: 0 }, uBeam: { value: 0 }, uPulse: { value: -10 }, uPixel: { value: 1 }, uHeight: { value: 800 } };
  private dotColor: THREE.BufferAttribute;
  private sitePos: THREE.BufferAttribute;
  private siteColor: THREE.BufferAttribute;
  private siteSize: THREE.BufferAttribute;
  private siteBorn: THREE.BufferAttribute;
  private siteGeo: THREE.BufferGeometry;
  private pillarPos: THREE.BufferAttribute;
  private pillarGeo: THREE.BufferGeometry;
  private pillars = 0;
  private sites = new Map<string, { i: number; state: SiteState; dot: number }>();
  private arcs: Arc[] = [];
  private headPos: THREE.BufferAttribute;
  private headColor: THREE.BufferAttribute;
  private ripples: Ripple[] = [];
  private bursts: Burst[] = [];
  private sparkPos: THREE.BufferAttribute;
  private sparkGeo: THREE.BufferGeometry;
  private satellites = new Map<string, Satellite>();
  private vault: THREE.Group;
  private vaultLabel: HTMLDivElement;
  private vaultCount = 0;
  private vaultFlash = 0;
  private labels: Label[] = [];
  private lastRead: number | null = null;
  private focus = new Set<number>();
  private frame = 0;
  private last = 0;
  private visible = true;
  private reduced: boolean;
  private demo: boolean;
  private demoAt = 0;
  private intro = 0;
  private distance = 4.6;
  private drag = { on: false, x: 0, y: 0, vx: 0, vy: 0, rx: 0.35, ry: 0 };
  private cleanup: (() => void)[] = [];
  private tmp = new THREE.Vector3();

  constructor(host: HTMLElement, opts: { demo?: boolean; labels?: boolean } = {}) {
    this.host = host;
    this.demo = !!opts.demo;
    this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    // The composer's targets skip colour management on clear, so hand it the linear value.
    this.renderer.setClearColor(new THREE.Color(STAGE.bg).convertSRGBToLinear(), 1);
    this.renderer.domElement.setAttribute("aria-hidden", "true");
    host.appendChild(this.renderer.domElement);
    this.labelsLayer = document.createElement("div");
    this.labelsLayer.className = "globe-labels";
    this.labelsLayer.setAttribute("aria-hidden", "true");
    if (opts.labels === false) this.labelsLayer.style.display = "none";
    host.appendChild(this.labelsLayer);
    this.uniforms.uPixel.value = this.renderer.getPixelRatio();

    this.scene.add(this.earthGroup);
    this.earthGroup.rotation.set(0.35, 0, 0);
    this.earth = buildEarth();

    // Stars far behind.
    const starGeo = new THREE.BufferGeometry();
    const stars = new Float32Array(1800 * 3);
    for (let i = 0; i < 1800; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(18 + Math.random() * 14);
      stars.set([v.x, v.y, v.z], i * 3);
    }
    starGeo.setAttribute("position", new THREE.BufferAttribute(stars, 3));
    this.scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0x8a96aa, size: 0.045, transparent: true, opacity: 0.55, depthWrite: false })));

    // The solid core hides the far side's dots, so the globe reads as a ball.
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.992, 64, 48), new THREE.MeshBasicMaterial({ color: STAGE.core }));
    core.renderOrder = 0;
    this.earthGroup.add(core);

    // Atmosphere: a fresnel halo outside, a faint rim inside.
    const halo = new THREE.Mesh(new THREE.SphereGeometry(1.22, 64, 48), new THREE.ShaderMaterial({
      vertexShader: GLOW_VERT, fragmentShader: HALO_FRAG, side: THREE.BackSide, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: { uColor: { value: new THREE.Color(STAGE.glow) }, uPower: { value: 2.6 }, uStrength: { value: 0.55 } },
    }));
    halo.scale.setScalar(1);
    this.scene.add(halo);
    const rim = new THREE.Mesh(new THREE.SphereGeometry(1.005, 64, 48), new THREE.ShaderMaterial({
      vertexShader: GLOW_VERT, fragmentShader: GLOW_FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uColor: { value: new THREE.Color(STAGE.glow) }, uPower: { value: 3.5 }, uStrength: { value: 0.22 } },
    }));
    this.earthGroup.add(rim);

    // Graticule.
    const grat: number[] = [];
    const R = 1.002;
    for (let lat = -60; lat <= 60; lat += 30) {
      for (let k = 0; k < 96; k++) {
        const a = (k / 96) * Math.PI * 2, b = ((k + 1) / 96) * Math.PI * 2, c = Math.cos((lat * Math.PI) / 180), y = Math.sin((lat * Math.PI) / 180);
        grat.push(Math.cos(a) * c * R, y * R, Math.sin(a) * c * R, Math.cos(b) * c * R, y * R, Math.sin(b) * c * R);
      }
    }
    for (let lon = 0; lon < 180; lon += 30) {
      for (let k = 0; k < 96; k++) {
        const a = (k / 96) * Math.PI * 2, b = ((k + 1) / 96) * Math.PI * 2, t = (lon * Math.PI) / 180;
        grat.push(Math.cos(a) * Math.cos(t) * R, Math.sin(a) * R, Math.cos(a) * Math.sin(t) * R,
          Math.cos(b) * Math.cos(t) * R, Math.sin(b) * R, Math.cos(b) * Math.sin(t) * R);
      }
    }
    const gratGeo = new THREE.BufferGeometry();
    gratGeo.setAttribute("position", new THREE.Float32BufferAttribute(grat, 3));
    this.earthGroup.add(new THREE.LineSegments(gratGeo, new THREE.LineBasicMaterial({ color: 0x8fa3c0, transparent: true, opacity: 0.07, depthWrite: false })));

    const pointMat = () => new THREE.ShaderMaterial({ vertexShader: POINT_VERT, fragmentShader: POINT_FRAG, uniforms: this.uniforms, transparent: true, depthWrite: false });

    // Earth dots.
    const n = this.earth.country.length;
    const dotGeo = new THREE.BufferGeometry();
    dotGeo.setAttribute("position", new THREE.BufferAttribute(this.earth.positions, 3));
    this.dotColor = new THREE.BufferAttribute(new Float32Array(n * 3), 3);
    const dotSize = new Float32Array(n);
    for (let i = 0; i < n; i++) dotSize[i] = this.earth.country[i] >= 0 ? 3.3 : 1.0;
    dotGeo.setAttribute("aColor", this.dotColor);
    dotGeo.setAttribute("aSize", new THREE.BufferAttribute(dotSize, 1));
    dotGeo.setAttribute("aBorn", new THREE.BufferAttribute(new Float32Array(n).fill(-1), 1));
    this.earthGroup.add(new THREE.Points(dotGeo, pointMat()));
    this.paintDots();

    // Sites and pillars.
    this.siteGeo = new THREE.BufferGeometry();
    this.sitePos = new THREE.BufferAttribute(new Float32Array(MAX_SITES * 3), 3);
    this.siteColor = new THREE.BufferAttribute(new Float32Array(MAX_SITES * 3), 3);
    this.siteSize = new THREE.BufferAttribute(new Float32Array(MAX_SITES), 1);
    this.siteBorn = new THREE.BufferAttribute(new Float32Array(MAX_SITES), 1);
    this.siteGeo.setAttribute("position", this.sitePos);
    this.siteGeo.setAttribute("aColor", this.siteColor);
    this.siteGeo.setAttribute("aSize", this.siteSize);
    this.siteGeo.setAttribute("aBorn", this.siteBorn);
    this.siteGeo.setDrawRange(0, 0);
    this.earthGroup.add(new THREE.Points(this.siteGeo, pointMat()));
    this.pillarGeo = new THREE.BufferGeometry();
    this.pillarPos = new THREE.BufferAttribute(new Float32Array(MAX_SITES * 6), 3);
    this.pillarGeo.setAttribute("position", this.pillarPos);
    this.pillarGeo.setDrawRange(0, 0);
    this.earthGroup.add(new THREE.LineSegments(this.pillarGeo, new THREE.LineBasicMaterial({
      color: STAGE.kept, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false })));

    // Arc pool (scene space) and their glowing heads.
    for (let i = 0; i < ARCS; i++) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array((SEG + 1) * 3), 3));
      const mat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false });
      const line = new THREE.Line(geo, mat);
      line.visible = false;
      line.frustumCulled = false;
      this.scene.add(line);
      this.arcs.push({ line, mat, pts: [], t: 0, dur: 1, tail: 0.3, live: false, color: new THREE.Color() });
    }
    const headGeo = new THREE.BufferGeometry();
    this.headPos = new THREE.BufferAttribute(new Float32Array(ARCS * 3).fill(999), 3);
    this.headColor = new THREE.BufferAttribute(new Float32Array(ARCS * 3), 3);
    headGeo.setAttribute("position", this.headPos);
    headGeo.setAttribute("aColor", this.headColor);
    headGeo.setAttribute("aSize", new THREE.BufferAttribute(new Float32Array(ARCS).fill(5.5), 1));
    headGeo.setAttribute("aBorn", new THREE.BufferAttribute(new Float32Array(ARCS).fill(-1), 1));
    const heads = new THREE.Points(headGeo, new THREE.ShaderMaterial({
      vertexShader: POINT_VERT.replace("float facing = clamp(dot(n, toCam), 0.0, 1.0);", "float facing = 1.0;"),
      fragmentShader: POINT_FRAG, uniforms: this.uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    heads.frustumCulled = false;
    this.scene.add(heads);

    // Ripples (earth space).
    const ringGeo = new THREE.RingGeometry(0.82, 1, 48);
    for (let i = 0; i < RIPPLES; i++) {
      const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false });
      const mesh = new THREE.Mesh(ringGeo, mat);
      mesh.visible = false;
      this.earthGroup.add(mesh);
      this.ripples.push({ mesh, mat, t: 0, dur: 1, size: 0.1, live: false });
    }

    // Spark bursts (earth space).
    this.sparkGeo = new THREE.BufferGeometry();
    this.sparkPos = new THREE.BufferAttribute(new Float32Array(BURSTS * SPARKS * 3).fill(999), 3);
    const sparkColor = new Float32Array(BURSTS * SPARKS * 3);
    const gold = new THREE.Color(STAGE.found);
    for (let i = 0; i < BURSTS * SPARKS; i++) sparkColor.set([gold.r, gold.g, gold.b], i * 3);
    this.sparkGeo.setAttribute("position", this.sparkPos);
    this.sparkGeo.setAttribute("aColor", new THREE.BufferAttribute(sparkColor, 3));
    this.sparkGeo.setAttribute("aSize", new THREE.BufferAttribute(new Float32Array(BURSTS * SPARKS).fill(3.2), 1));
    this.sparkGeo.setAttribute("aBorn", new THREE.BufferAttribute(new Float32Array(BURSTS * SPARKS).fill(-1), 1));
    const sparks = new THREE.Points(this.sparkGeo, new THREE.ShaderMaterial({ vertexShader: POINT_VERT, fragmentShader: POINT_FRAG,
      uniforms: this.uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    sparks.frustumCulled = false;
    this.earthGroup.add(sparks);
    for (let i = 0; i < BURSTS; i++) this.bursts.push({ origin: new THREE.Vector3(), vel: Array.from({ length: SPARKS }, () => new THREE.Vector3()), t: 0, live: false });

    // The vault: where kept sites go (your spreadsheet).
    this.vault = new THREE.Group();
    this.vault.position.set(1.62, 0.92, 0.1);
    const vRing = new THREE.Mesh(new THREE.TorusGeometry(0.11, 0.008, 12, 64), new THREE.MeshBasicMaterial({ color: STAGE.kept }));
    vRing.rotation.x = Math.PI / 2;
    const vCore = new THREE.Mesh(new THREE.OctahedronGeometry(0.045, 0), new THREE.MeshBasicMaterial({ color: 0xffe2cf, wireframe: true }));
    this.vault.add(vRing, vCore);
    this.scene.add(this.vault);
    this.vaultLabel = this.makeLabel("vault", "Sites kept");

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.5, 0.2, 0.6);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.bindEvents();
    this.resize();
    if (this.demo) this.seedDemo();
    this.schedule();
    if (this.reduced) this.render();
  }

  // --- public ---------------------------------------------------------------------------------------

  setFocus(alpha2: string[]) {
    this.focus = focusDots(this.earth, alpha2);
    // Turn the target countries towards the camera.
    if (this.focus.size) {
      let x = 0, z = 0;
      for (const i of this.focus) { x += this.earth.positions[i * 3]; z += this.earth.positions[i * 3 + 2]; }
      this.drag.ry = Math.atan2(-x, z);
    }
    this.paintDots();
    this.render();
  }

  private bumpVault() {
    this.vaultCount++;
    this.vaultLabel.querySelector("b")!.textContent = String(this.vaultCount);
  }

  feed(sig: GlobeSignal, animate: boolean) {
    const fx = animate && !this.reduced;
    if (sig.kind === "search") {
      if (fx) this.uniforms.uPulse.value = this.uniforms.uTime.value;
      const sat = sig.source ? this.satellite(sig.source) : null;
      if (sat && fx) {
        sat.flash = 1;
        const from = sat.node.getWorldPosition(new THREE.Vector3());
        const pool = this.focus.size ? [...this.focus] : this.earth.land;
        const shots = 3 + Math.floor(Math.random() * 3);
        for (let k = 0; k < shots; k++) {
          const dot = pool[Math.floor(Math.random() * pool.length)];
          this.arc(from, this.dotWorld(dot), STAGE.search, 1.1 + Math.random() * 0.5, 0.35, k * 0.08);
        }
      }
      if (sig.site && fx) this.ripple(this.siteLocal(sig.site), STAGE.search, 0.09, 1.4);
      return;
    }
    if (sig.kind === "records") { if (fx) this.vaultFlash = 1; return; }
    const state = STATE_OF[sig.kind];
    if (!state || !sig.site) return;
    const s = this.light(sig.site, state, fx);
    if (!s) return;
    if (!fx) { if (sig.kind === "kept") this.bumpVault(); return; }
    const local = this.dotLocal(s.dot);
    if (sig.kind === "read" || sig.kind === "queued") {
      if (this.lastRead !== null && this.lastRead !== s.dot && sig.kind === "read") {
        this.arc(this.dotWorld(this.lastRead), this.dotWorld(s.dot), STAGE.hop, 0.9, 0.5);
      }
      if (sig.kind === "read") this.lastRead = s.dot;
      this.ripple(local, STAGE.seen, 0.045, 0.9);
    } else if (sig.kind === "kept") {
      this.ripple(local, STAGE.kept, 0.16, 1.6);
      this.ripple(local, STAGE.kept, 0.09, 1.1, 0.25);
      this.arc(this.dotWorld(s.dot), this.vault.getWorldPosition(new THREE.Vector3()), STAGE.kept, 1.3, 0.45, 0, () => {
        this.bumpVault();
        this.vaultFlash = 1;
      });
      this.siteLabel(sig.site, local);
    } else if (sig.kind === "found") {
      this.burst(local);
    } else if (state === "dropped") {
      this.ripple(local, STAGE.dropped, 0.07, 1.0);
    } else if (state === "bad") {
      this.ripple(local, STAGE.bad, 0.1, 1.2);
    }
  }

  render() {
    this.composer.render();
    this.placeLabels();
  }

  dispose() {
    this.stop();
    this.cleanup.forEach((f) => f());
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      m.geometry?.dispose();
      (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x?.dispose());
    });
    this.composer.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labelsLayer.remove();
  }

  // --- building blocks ------------------------------------------------------------------------------

  private paintDots() {
    const land = new THREE.Color(STAGE.land), ocean = new THREE.Color(STAGE.ocean), focus = new THREE.Color(STAGE.focus);
    const dim = land.clone().multiplyScalar(0.55);
    const n = this.earth.country.length;
    for (let i = 0; i < n; i++) {
      const c = this.earth.country[i] < 0 ? ocean : this.focus.has(i) ? focus : this.focus.size ? dim : land;
      this.dotColor.setXYZ(i, c.r, c.g, c.b);
    }
    this.dotColor.needsUpdate = true;
  }

  private dotLocal(dot: number) {
    const p = this.earth.positions;
    return new THREE.Vector3(p[dot * 3], p[dot * 3 + 1], p[dot * 3 + 2]);
  }
  private dotWorld(dot: number) {
    return this.earthGroup.localToWorld(this.dotLocal(dot).multiplyScalar(1.01));
  }
  private siteLocal(site: string) {
    return this.dotLocal(siteDot(this.earth, site));
  }

  private light(site: string, state: SiteState, fx: boolean) {
    let s = this.sites.get(site);
    if (!s) {
      if (this.sites.size >= MAX_SITES) return null;
      const dot = siteDot(this.earth, site);
      s = { i: this.sites.size, state, dot };
      this.sites.set(site, s);
      const p = this.dotLocal(dot).multiplyScalar(1.012);
      this.sitePos.setXYZ(s.i, p.x, p.y, p.z);
      this.sitePos.needsUpdate = true;
      this.siteBorn.setX(s.i, fx ? this.uniforms.uTime.value : -1);
      this.siteBorn.needsUpdate = true;
      this.siteGeo.setDrawRange(0, this.sites.size);
    } else if (RANK[state] < RANK[s.state]) {
      return s;
    }
    if (state === "kept" && s.state !== "kept") {
      const base = this.dotLocal(s.dot);
      const h = 1.04 + 0.05 + hashOf(site) * 0.1;
      this.pillarPos.setXYZ(this.pillars * 2, base.x, base.y, base.z);
      this.pillarPos.setXYZ(this.pillars * 2 + 1, base.x * h, base.y * h, base.z * h);
      this.pillarPos.needsUpdate = true;
      this.pillars++;
      this.pillarGeo.setDrawRange(0, this.pillars * 2);
    }
    s.state = state;
    const col = new THREE.Color(state === "kept" ? STAGE.kept : state === "dropped" ? STAGE.dropped : state === "bad" ? STAGE.bad : STAGE.seen);
    this.siteColor.setXYZ(s.i, col.r, col.g, col.b);
    this.siteSize.setX(s.i, state === "kept" ? 8 : state === "seen" ? 5 : 3.6);
    this.siteColor.needsUpdate = true;
    this.siteSize.needsUpdate = true;
    return s;
  }

  private arc(from: THREE.Vector3, to: THREE.Vector3, color: number, dur: number, tail: number, delay = 0, onDone?: () => void) {
    const a = this.arcs.find((x) => !x.live) ?? this.arcs.reduce((m, x) => (x.t > m.t ? x : m));
    const mid = from.clone().add(to).multiplyScalar(0.5);
    const lift = Math.max(from.length(), to.length(), 1) + 0.18 + from.distanceTo(to) * 0.32;
    mid.normalize().multiplyScalar(lift);
    const curve = new THREE.QuadraticBezierCurve3(from.clone(), mid, to.clone());
    a.pts = curve.getPoints(SEG);
    const attr = a.line.geometry.getAttribute("position") as THREE.BufferAttribute;
    a.pts.forEach((p, i) => attr.setXYZ(i, p.x, p.y, p.z));
    attr.needsUpdate = true;
    a.line.geometry.setDrawRange(0, 0);
    a.color.set(color);
    a.mat.color.copy(a.color);
    a.t = -delay / dur;
    a.dur = dur;
    a.tail = tail;
    a.live = true;
    a.onDone = onDone;
    a.line.visible = true;
  }

  private ripple(local: THREE.Vector3, color: number, size: number, dur: number, delay = 0) {
    const r = this.ripples.find((x) => !x.live) ?? this.ripples.reduce((m, x) => (x.t > m.t ? x : m));
    const p = local.clone().normalize().multiplyScalar(1.004);
    r.mesh.position.copy(p);
    r.mesh.lookAt(p.clone().multiplyScalar(2));
    r.mat.color.set(color);
    r.t = -delay;
    r.dur = dur;
    r.size = size;
    r.live = true;
    r.mesh.visible = true;
    r.mesh.scale.setScalar(0.0001);
  }

  private burst(local: THREE.Vector3) {
    const b = this.bursts.find((x) => !x.live) ?? this.bursts.reduce((m, x) => (x.t > m.t ? x : m));
    b.origin.copy(local).normalize().multiplyScalar(1.015);
    const n = b.origin.clone().normalize();
    b.vel.forEach((v) => v.randomDirection().multiplyScalar(0.18 + Math.random() * 0.22).add(n.clone().multiplyScalar(0.28)));
    b.t = 0;
    b.live = true;
  }

  private makeLabel(cls: string, text: string) {
    const el = document.createElement("div");
    el.className = `globe-label ${cls}`;
    el.innerHTML = cls === "vault" ? `<span>${text}</span> <b>0</b>` : `<span></span>`;
    if (cls !== "vault") el.querySelector("span")!.textContent = text;
    this.labelsLayer.appendChild(el);
    return el;
  }

  private satellite(name: string) {
    let sat = this.satellites.get(name);
    if (sat) return sat;
    if (this.satellites.size >= 8) return [...this.satellites.values()][hashOf(name) * this.satellites.size | 0];
    const pivot = new THREE.Group();
    const h = hashOf(name);
    pivot.rotation.set((h - 0.5) * 1.6, h * Math.PI * 2, (hashOf(name + "z") - 0.5) * 1.2);
    const r = 1.42 + (this.satellites.size % 3) * 0.1;
    const orbit = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(
      Array.from({ length: 128 }, (_, i) => new THREE.Vector3(Math.cos((i / 128) * Math.PI * 2) * r, 0, Math.sin((i / 128) * Math.PI * 2) * r))),
      new THREE.LineBasicMaterial({ color: STAGE.search, transparent: true, opacity: 0.16, depthWrite: false }));
    const node = new THREE.Mesh(new THREE.SphereGeometry(0.014, 16, 12), new THREE.MeshBasicMaterial({ color: 0xcfe5ff }));
    node.position.set(r, 0, 0);
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.026, 0.032, 32), new THREE.MeshBasicMaterial({
      color: STAGE.search, transparent: true, opacity: 0.8, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
    node.add(halo);
    const spin = new THREE.Group();
    spin.add(orbit, node);
    pivot.add(spin);
    this.scene.add(pivot);
    const label = this.makeLabel("sat", name);
    sat = { name, pivot: spin, node, halo, speed: 0.12 + h * 0.18, flash: 0, label };
    this.satellites.set(name, sat);
    return sat;
  }

  private siteLabel(site: string, local: THREE.Vector3) {
    const el = this.makeLabel("site", site.replace(/^www\./, ""));
    this.labels.push({ el, local: local.clone().multiplyScalar(1.12), born: this.uniforms.uTime.value, ttl: 7 });
    while (this.labels.length > 7) this.labels.shift()!.el.remove();
  }

  private placeLabels() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    const camDir = this.camera.position.clone().normalize();
    const put = (el: HTMLElement, world: THREE.Vector3, show: boolean, opacity = 1) => {
      const p = this.tmp.copy(world).project(this.camera);
      el.style.transform = `translate(${((p.x + 1) / 2) * w}px, ${((1 - p.y) / 2) * h}px)`;
      el.style.opacity = show ? String(opacity) : "0";
    };
    for (const sat of this.satellites.values()) {
      const wp = sat.node.getWorldPosition(new THREE.Vector3());
      const behind = wp.clone().normalize().dot(camDir) < -0.2 && wp.length() < 2;
      put(sat.label, wp, !behind, 0.9);
    }
    put(this.vaultLabel, this.vault.getWorldPosition(new THREE.Vector3()), true);
    const now = this.uniforms.uTime.value;
    this.labels = this.labels.filter((l) => {
      const age = now - l.born;
      if (age > l.ttl) { l.el.remove(); return false; }
      const wp = this.earthGroup.localToWorld(l.local.clone());
      const facing = wp.clone().normalize().dot(camDir) > 0.15;
      put(l.el, wp, facing, Math.min(1, age * 3, (l.ttl - age) / 1.2));
      return true;
    });
  }

  // --- loop -----------------------------------------------------------------------------------------

  private step = (now: number) => {
    this.frame = 0;
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    const t = (this.uniforms.uTime.value += dt);
    this.uniforms.uBeam.value = (t * 0.45) % (Math.PI * 2);

    // Camera intro, then a slow drift; dragging takes over rotation with inertia.
    this.intro = Math.min(1, this.intro + dt / 1.8);
    const e = 1 - Math.pow(1 - this.intro, 3);
    const dist = this.distance * (1.45 - 0.45 * e);
    this.camera.position.set(0, 0.25, dist);
    this.camera.lookAt(0, 0.08, 0);
    if (!this.drag.on) {
      this.drag.ry += dt * (this.focus.size ? 0.025 : 0.06) + this.drag.vy;
      this.drag.rx += this.drag.vx;
      this.drag.vx *= 0.94;
      this.drag.vy *= 0.94;
      this.drag.rx += (0.35 - this.drag.rx) * 0.01;
    }
    this.drag.rx = Math.max(-0.9, Math.min(1.2, this.drag.rx));
    this.earthGroup.rotation.set(this.drag.rx, this.drag.ry, 0);

    for (const sat of this.satellites.values()) {
      sat.pivot.rotation.y += dt * sat.speed;
      sat.flash = Math.max(0, sat.flash - dt * 1.6);
      sat.node.scale.setScalar(1 + sat.flash * 1.1);
      (sat.halo.material as THREE.MeshBasicMaterial).opacity = 0.3 + sat.flash * 0.6;
      sat.halo.lookAt(this.camera.position);
    }
    this.vaultFlash = Math.max(0, this.vaultFlash - dt * 1.4);
    this.vault.scale.setScalar(1 + this.vaultFlash * 0.6);
    this.vault.rotation.y += dt * 0.6;

    // Arcs: a comet runs from start to end, its tail following.
    this.arcs.forEach((a, i) => {
      if (!a.live) return;
      a.t += dt / a.dur;
      if (a.t < 0) { a.line.geometry.setDrawRange(0, 0); this.headPos.setXYZ(i, 999, 999, 999); return; }
      const head = Math.min(1, a.t), tailEnd = Math.max(0, a.t - a.tail);
      const s = Math.floor(tailEnd * SEG), e2 = Math.ceil(head * SEG);
      a.line.geometry.setDrawRange(s, Math.max(0, e2 - s + 1));
      a.mat.opacity = a.t > 1 ? Math.max(0, 1 - (a.t - 1) / a.tail) * 0.9 : 0.9;
      if (a.t <= 1) {
        const p = a.pts[Math.min(SEG, Math.round(head * SEG))];
        this.headPos.setXYZ(i, p.x, p.y, p.z);
        this.headColor.setXYZ(i, Math.min(1, a.color.r + 0.3), Math.min(1, a.color.g + 0.3), Math.min(1, a.color.b + 0.3));
      } else {
        this.headPos.setXYZ(i, 999, 999, 999);
        if (a.onDone) { a.onDone(); a.onDone = undefined; }
      }
      if (a.t > 1 + a.tail) { a.live = false; a.line.visible = false; }
    });
    this.headPos.needsUpdate = true;
    this.headColor.needsUpdate = true;

    for (const r of this.ripples) {
      if (!r.live) continue;
      r.t += dt;
      if (r.t < 0) continue;
      const k = r.t / r.dur;
      if (k >= 1) { r.live = false; r.mesh.visible = false; continue; }
      r.mesh.scale.setScalar(0.004 + r.size * (1 - Math.pow(1 - k, 3)));
      r.mat.opacity = (1 - k) * 0.95;
    }

    this.bursts.forEach((b, bi) => {
      if (!b.live) return;
      b.t += dt;
      const k = b.t / 1.3;
      for (let j = 0; j < SPARKS; j++) {
        const idx = bi * SPARKS + j;
        if (k >= 1) { this.sparkPos.setXYZ(idx, 999, 999, 999); continue; }
        const v = b.vel[j];
        const ease = 1 - Math.pow(1 - k, 2);
        this.sparkPos.setXYZ(idx, b.origin.x + v.x * ease * 0.35, b.origin.y + v.y * ease * 0.35, b.origin.z + v.z * ease * 0.35);
      }
      if (k >= 1) b.live = false;
    });
    this.sparkPos.needsUpdate = true;

    if (this.demo && t > this.demoAt) this.demoTick(t);
    this.render();
    this.schedule();
  };

  private schedule() {
    if (!this.reduced && this.visible && !document.hidden && !this.frame) {
      this.last = performance.now();
      this.frame = requestAnimationFrame(this.step);
    }
  }
  private stop() {
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
  }

  private resize = () => {
    const w = this.host.clientWidth || 1, h = this.host.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.resolution.set(w / 2, h / 2);
    this.uniforms.uHeight.value = h;
    this.camera.aspect = w / h;
    // Keep the whole globe in view on tall, narrow screens.
    this.distance = w / h < 1 ? 4.6 / Math.max(0.55, w / h) : 4.6;
    this.camera.updateProjectionMatrix();
    if (!this.frame) this.render();
  };

  private bindEvents() {
    const el = this.host;
    const ro = new ResizeObserver(this.resize);
    ro.observe(el);
    const io = new IntersectionObserver(([en]) => { this.visible = en.isIntersecting; if (this.visible) this.schedule(); else this.stop(); });
    io.observe(el);
    const onVis = () => (document.hidden ? this.stop() : this.schedule());
    document.addEventListener("visibilitychange", onVis);
    const down = (e: PointerEvent) => { this.drag.on = true; this.drag.x = e.clientX; this.drag.y = e.clientY; el.setPointerCapture(e.pointerId); el.classList.add("dragging"); };
    const move = (e: PointerEvent) => {
      if (!this.drag.on) return;
      const dx = (e.clientX - this.drag.x) / el.clientWidth, dy = (e.clientY - this.drag.y) / el.clientHeight;
      this.drag.x = e.clientX; this.drag.y = e.clientY;
      this.drag.ry += dx * 3; this.drag.rx += dy * 2;
      this.drag.vy = dx * 3 * 0.5; this.drag.vx = dy * 2 * 0.5;
      if (this.reduced) { this.earthGroup.rotation.set(this.drag.rx, this.drag.ry, 0); this.render(); }
    };
    const up = () => { this.drag.on = false; el.classList.remove("dragging"); };
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    this.cleanup.push(() => {
      ro.disconnect(); io.disconnect(); document.removeEventListener("visibilitychange", onVis);
      el.removeEventListener("pointerdown", down); el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up);
    });
  }

  // --- illustration mode (pages without a run) -----------------------------------------------------

  private demoSites = Array.from({ length: 220 }, (_, i) => {
    const tlds = ["com", "de", "in", "co.uk", "fr", "jp", "com.br", "com.au", "ca", "it", "es", "nl", "ch", "se", "kr", "mx", "za", "sg", "com", "com", "io"];
    return `site${i}.${tlds[i % tlds.length]}`;
  });
  private demoSources = ["SearXNG", "Wikidata", "GLEIF", "SEC EDGAR", "News"];

  private seedDemo() {
    for (let i = 0; i < 60; i++) {
      const site = this.demoSites[i];
      this.light(site, i % 4 === 0 ? "kept" : i % 4 === 1 ? "dropped" : "seen", false);
    }
    this.demoSources.slice(0, 3).forEach((s) => this.satellite(s));
  }

  private demoTick(t: number) {
    this.demoAt = t + 0.25 + Math.random() * 0.5;
    const roll = Math.random();
    const site = this.demoSites[Math.floor(Math.random() * this.demoSites.length)];
    const kind = roll < 0.1 ? "search" : roll < 0.6 ? "read" : roll < 0.75 ? "kept" : roll < 0.85 ? "found" : roll < 0.95 ? "dropped" : "blocked";
    const source = this.demoSources[Math.floor(Math.random() * this.demoSources.length)];
    this.feed({ id: 0, kind, site: kind === "search" ? null : site, source }, true);
  }
}
