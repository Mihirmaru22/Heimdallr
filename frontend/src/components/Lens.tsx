import { useEffect, useRef } from "react";
import * as THREE from "three";
import { isDark } from "../theme";

// The Lens: a slowly turning globe of sources swept by a beam. On the job page it is driven by the real
// activity feed (see DESIGN.md): a search sends a scan ring across the globe, a site being read lights a
// point, a kept site turns the beacon colour and is wired to the core, a dropped site fades. With `demo`
// it lights random points, as an illustration on pages without a job.

export interface LensSignal { id: number; kind: string; site?: string | null }

type SiteState = "seen" | "kept" | "dropped" | "bad";
const STATE_OF: Record<string, SiteState | undefined> = {
  queued: "seen", read: "seen", links: "seen", kept: "kept", found: "kept", records: "kept",
  dropped: "dropped", skipped: "dropped", blocked: "dropped", failed: "bad",
};
const RANK: Record<SiteState, number> = { seen: 0, dropped: 1, bad: 2, kept: 3 };

const SHELL = 1100;
const MAX_SITES = 700;

const VERT = /* glsl */ `
attribute vec3 aColor;
attribute float aSize;
attribute float aBorn;
uniform float uTime;
uniform float uBeam;
uniform float uPulse;
uniform float uPixel;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vec3 n = normalize(world.xyz);
  float ang = atan(world.x, world.z);
  float d = abs(mod(ang - uBeam + 3.14159, 6.28318) - 3.14159);
  float beam = smoothstep(0.7, 0.0, d);
  float age = aBorn < 0.0 ? 1.0 : clamp((uTime - aBorn) / 0.7, 0.0, 1.0);
  float pop = age * (1.0 + 1.6 * (1.0 - age));
  float pt = uTime - uPulse;
  float lat = asin(clamp(n.y, -1.0, 1.0));
  float ring = (pt > 0.0 && pt < 1.6) ? smoothstep(0.16, 0.0, abs(lat - (-1.7 + pt * 2.2))) * (1.0 - pt / 1.6) : 0.0;
  float facing = dot(n, normalize(cameraPosition)) * 0.5 + 0.5;
  vColor = aColor;
  vAlpha = (0.18 + 0.82 * facing) * (0.6 + 0.4 * beam + ring);
  vec4 mv = viewMatrix * world;
  gl_PointSize = aSize * pop * uPixel * (1.0 + 0.5 * beam + 0.9 * ring) * (6.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;
void main() {
  float r = length(gl_PointCoord - 0.5);
  if (r > 0.5) discard;
  gl_FragColor = vec4(vColor, smoothstep(0.5, 0.18, r) * vAlpha);
}`;

function hash(s: string, seed: number) {
  let h = 2166136261 ^ seed;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) % 100000) / 100000;
}

function spherePoint(u: number, v: number, r: number) {
  const theta = 2 * Math.PI * u;
  const phi = Math.acos(2 * v - 1);
  return new THREE.Vector3(r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

function palette() {
  const css = getComputedStyle(document.documentElement);
  const c = (name: string, fallback: string) => new THREE.Color((css.getPropertyValue(name).trim() || fallback));
  return {
    dust: c("--lens-dust", "#8a8d93"), ink: c("--ink", "#141518"), accent: c("--accent", "#c2410c"),
    faint: c("--lens-faint", "#c9cbce"), bad: c("--bad", "#bf3028"), line: c("--lens-line", "#c9cbce"),
  };
}

export default function Lens({ signals, demo = false, className = "" }:
  { signals?: LensSignal[]; demo?: boolean; className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const feed = useRef<(s: LensSignal) => void>(() => {});
  const seen = useRef(0);

  useEffect(() => {
    const el = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    } catch {
      el.classList.add("lens-fallback");
      return;
    }
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    el.appendChild(renderer.domElement);
    renderer.domElement.setAttribute("aria-hidden", "true");

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 50);
    camera.position.set(0, 0.35, 4.3);
    camera.lookAt(0, 0, 0);
    const globe = new THREE.Group();
    globe.rotation.z = 0.32;
    scene.add(globe);

    const uniforms = { uTime: { value: 0 }, uBeam: { value: 0 }, uPulse: { value: -10 }, uPixel: { value: renderer.getPixelRatio() } };
    const material = () => new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms, transparent: true, depthWrite: false });

    // The shell: an even Fibonacci sphere of dust.
    const shellGeo = new THREE.BufferGeometry();
    const shellPos = new Float32Array(SHELL * 3);
    const shellSize = new Float32Array(SHELL);
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < SHELL; i++) {
      const y = 1 - (i / (SHELL - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      shellPos.set([Math.cos(golden * i) * r, y, Math.sin(golden * i) * r], i * 3);
      shellSize[i] = 1.5 + (i % 7 === 0 ? 1.0 : 0);
    }
    shellGeo.setAttribute("position", new THREE.BufferAttribute(shellPos, 3));
    shellGeo.setAttribute("aSize", new THREE.BufferAttribute(shellSize, 1));
    shellGeo.setAttribute("aBorn", new THREE.BufferAttribute(new Float32Array(SHELL).fill(-1), 1));
    const shellColor = new THREE.BufferAttribute(new Float32Array(SHELL * 3), 3);
    shellGeo.setAttribute("aColor", shellColor);
    globe.add(new THREE.Points(shellGeo, material()));

    // Orbit rings and the core.
    const ringMat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.55 });
    const ringPts = (r: number) => Array.from({ length: 129 }, (_, i) =>
      new THREE.Vector3(Math.cos((i / 128) * Math.PI * 2) * r, 0, Math.sin((i / 128) * Math.PI * 2) * r));
    const rings = [[1.32, 0.4, 0], [1.5, -0.9, 0.5], [1.18, 1.3, -0.4]].map(([r, x, y]) => {
      const loop = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(ringPts(r)), ringMat);
      loop.rotation.set(x, y, 0);
      scene.add(loop);
      return loop;
    });
    const coreMat = new THREE.MeshBasicMaterial({ wireframe: true, transparent: true, opacity: 0.5 });
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.3, 1), coreMat);
    globe.add(core);

    // Sites: points that light up as the research touches them, plus wires from kept sites to the core.
    const siteGeo = new THREE.BufferGeometry();
    const sitePos = new THREE.BufferAttribute(new Float32Array(MAX_SITES * 3), 3);
    const siteColor = new THREE.BufferAttribute(new Float32Array(MAX_SITES * 3), 3);
    const siteSize = new THREE.BufferAttribute(new Float32Array(MAX_SITES), 1);
    const siteBorn = new THREE.BufferAttribute(new Float32Array(MAX_SITES), 1);
    siteGeo.setAttribute("position", sitePos);
    siteGeo.setAttribute("aColor", siteColor);
    siteGeo.setAttribute("aSize", siteSize);
    siteGeo.setAttribute("aBorn", siteBorn);
    siteGeo.setDrawRange(0, 0);
    globe.add(new THREE.Points(siteGeo, material()));
    const wireGeo = new THREE.BufferGeometry();
    const wirePos = new THREE.BufferAttribute(new Float32Array(MAX_SITES * 6), 3);
    wireGeo.setAttribute("position", wirePos);
    wireGeo.setDrawRange(0, 0);
    const wireMat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.32 });
    globe.add(new THREE.LineSegments(wireGeo, wireMat));

    const sites = new Map<string, { i: number; state: SiteState }>();
    let wires = 0;
    let colors = palette();

    const paintSite = (i: number, state: SiteState) => {
      const col = state === "kept" ? colors.accent : state === "dropped" ? colors.faint : state === "bad" ? colors.bad : colors.ink;
      siteColor.setXYZ(i, col.r, col.g, col.b);
      siteSize.setX(i, state === "kept" ? 5 : state === "seen" ? 3.4 : 2.8);
      siteColor.needsUpdate = true;
      siteSize.needsUpdate = true;
    };
    const recolor = () => {
      colors = palette();
      for (let i = 0; i < SHELL; i++) shellColor.setXYZ(i, colors.dust.r, colors.dust.g, colors.dust.b);
      shellColor.needsUpdate = true;
      ringMat.color.copy(colors.line);
      coreMat.color.copy(colors.accent);
      wireMat.color.copy(colors.accent);
      wireMat.opacity = isDark() ? 0.4 : 0.3;
      for (const { i, state } of sites.values()) paintSite(i, state);
      draw();
    };

    const light = (site: string, state: SiteState) => {
      let s = sites.get(site);
      if (!s) {
        if (sites.size >= MAX_SITES) return;
        s = { i: sites.size, state };
        sites.set(site, s);
        const p = spherePoint(hash(site, 1), hash(site, 7), 1.03);
        sitePos.setXYZ(s.i, p.x, p.y, p.z);
        sitePos.needsUpdate = true;
        siteBorn.setX(s.i, uniforms.uTime.value);
        siteBorn.needsUpdate = true;
        siteGeo.setDrawRange(0, sites.size);
      } else if (RANK[state] < RANK[s.state]) {
        return;
      }
      if (state === "kept" && s.state !== "kept") {
        const p = new THREE.Vector3().fromBufferAttribute(sitePos, s.i);
        wirePos.setXYZ(wires * 2, 0, 0, 0);
        wirePos.setXYZ(wires * 2 + 1, p.x, p.y, p.z);
        wirePos.needsUpdate = true;
        wires++;
        wireGeo.setDrawRange(0, wires * 2);
      }
      s.state = state;
      paintSite(s.i, state);
    };

    feed.current = (sig: LensSignal) => {
      if (sig.kind === "search") uniforms.uPulse.value = uniforms.uTime.value;
      const state = STATE_OF[sig.kind];
      if (state && sig.site) light(sig.site, state);
      if (reduced) draw();
    };

    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.position.z = w / h < 1 ? 4.3 / Math.max(0.62, w / h) : 4.3;
      camera.updateProjectionMatrix();
      draw();
    };

    // Pointer tilts the lens a little; it eases back when the pointer leaves.
    const tilt = { x: 0, y: 0, tx: 0, ty: 0 };
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      tilt.tx = ((e.clientY - r.top) / r.height - 0.5) * 0.35;
      tilt.ty = ((e.clientX - r.left) / r.width - 0.5) * 0.5;
    };
    const onLeave = () => { tilt.tx = 0; tilt.ty = 0; };

    let last = performance.now();
    let demoAt = 0;
    let frame = 0;
    let visible = true;
    function draw() {
      renderer.render(scene, camera);
    }
    const step = (now: number) => {
      frame = 0;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = (uniforms.uTime.value += dt);
      uniforms.uBeam.value = (t * 0.55) % (Math.PI * 2);
      tilt.x += (tilt.tx - tilt.x) * 0.05;
      tilt.y += (tilt.ty - tilt.y) * 0.05;
      globe.rotation.y += dt * 0.08;
      globe.rotation.x = tilt.x;
      scene.rotation.y = tilt.y;
      core.rotation.x -= dt * 0.25;
      core.rotation.y -= dt * 0.18;
      rings.forEach((r, i) => { r.rotation.y += dt * (0.05 + i * 0.03) * (i % 2 ? -1 : 1); });
      if (demo && t > demoAt) {
        demoAt = t + 0.5 + Math.random() * 0.7;
        const site = `demo-${Math.floor(Math.random() * 160)}`;
        const roll = Math.random();
        if (roll < 0.08) uniforms.uPulse.value = t;
        light(site, roll < 0.45 ? "seen" : roll < 0.75 ? "kept" : "dropped");
      }
      draw();
      schedule();
    };
    const schedule = () => {
      if (!reduced && visible && !document.hidden && !frame) { last = performance.now(); frame = requestAnimationFrame(step); }
    };
    const stop = () => { if (frame) cancelAnimationFrame(frame); frame = 0; };

    if (demo && reduced) {
      for (let i = 0; i < 70; i++) light(`demo-${i}`, i % 3 === 0 ? "kept" : i % 3 === 1 ? "seen" : "dropped");
    }

    const ro = new ResizeObserver(resize);
    ro.observe(el);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) schedule(); else stop(); });
    io.observe(el);
    const onVis = () => (document.hidden ? stop() : schedule());
    document.addEventListener("visibilitychange", onVis);
    const mo = new MutationObserver(recolor);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", recolor);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);

    recolor();
    resize();
    schedule();

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      mo.disconnect();
      mq.removeEventListener("change", recolor);
      document.removeEventListener("visibilitychange", onVis);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      feed.current = () => {};
      seen.current = 0;
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x?.dispose());
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [demo]);

  // Hand new signals to the scene; the scene keeps its own state, so only unseen ids are sent.
  useEffect(() => {
    if (!signals) return;
    for (const s of signals) {
      if (s.id > seen.current) { feed.current(s); seen.current = s.id; }
    }
  }, [signals]);

  return <div ref={host} className={`lens ${className}`} />;
}
