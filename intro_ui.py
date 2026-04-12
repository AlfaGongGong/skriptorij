# ============================================================================
# BOOKLYFI INTRO ANIMATION — EMERGENCE (Three.js Cinematic, 12s)
# ============================================================================

INTRO_HTML = """
<style>
/* ── Skip button ─────────────────────────────────────────────────────────── */
.skip-intro-btn {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999999;
    color: rgba(255,255,255,0.55);
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.15);
    padding: 8px 20px;
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.25s ease;
    backdrop-filter: blur(8px);
    letter-spacing: 0.04em;
    display: none; /* shown at 2s via JS */
}
.skip-intro-btn:hover {
    color: #fff;
    background: rgba(255,255,255,0.14);
    border-color: rgba(255,255,255,0.3);
}

/* ── Overlay ──────────────────────────────────────────────────────────────── */
#intro-overlay {
    position: fixed;
    inset: 0;
    background: #020617;
    z-index: 999999;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

/* Three.js canvas fills overlay */
#intro-threejs-canvas {
    position: absolute;
    inset: 0;
    width: 100% !important;
    height: 100% !important;
    display: block;
}

/* ── Digital Rain canvas overlay ─────────────────────────────────────────── */
#intro-rain-canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    opacity: 1;
    transition: opacity 1s ease;
}

/* ── UI layer (logo text) ─────────────────────────────────────────────────── */
#intro-ui-layer {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    z-index: 10;
}

/* Logo text (hidden until phase 6) */
#intro-logo-text {
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: clamp(2.4rem, 6vw, 5rem);
    font-weight: 700;
    letter-spacing: 0.18em;
    color: #fff;
    opacity: 0;
    text-shadow:
        0 0 20px rgba(96,165,250,0.8),
        0 0 60px rgba(96,165,250,0.4),
        0 0 120px rgba(167,139,250,0.3);
    white-space: nowrap;
    transform: scale(0.85);
    transition: opacity 0s, transform 0s;
}
#intro-logo-text.visible {
    opacity: 1;
    transform: scale(1);
    transition: opacity 0.6s ease, transform 0.6s cubic-bezier(0.34,1.56,0.64,1);
}
/* individual letter spans */
#intro-logo-text .letter {
    display: inline-block;
    opacity: 0;
    transform: translateY(30px);
    transition: opacity 0.35s ease, transform 0.45s cubic-bezier(0.34,1.56,0.64,1);
}
#intro-logo-text .letter.in {
    opacity: 1;
    transform: translateY(0);
}

#intro-subtitle-text {
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: clamp(0.85rem, 2vw, 1.2rem);
    font-weight: 500;
    letter-spacing: 0.35em;
    color: rgba(255,255,255,0.7);
    margin-top: 14px;
    opacity: 0;
    text-transform: uppercase;
    text-shadow: 0 0 12px rgba(6,182,212,0.7);
    transition: opacity 0.6s ease 0.5s;
}
#intro-subtitle-text.visible { opacity: 1; }

#intro-loading-text {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 0.12em;
    color: rgba(96,165,250,0.6);
    margin-top: 36px;
    opacity: 0;
    transition: opacity 0.4s ease;
}
#intro-loading-text.visible { opacity: 1; }

/* Loading bar */
#intro-progress-wrap {
    position: absolute;
    bottom: 40px;
    left: 50%;
    transform: translateX(-50%);
    width: min(320px, 80vw);
    opacity: 0;
    transition: opacity 0.5s ease;
}
#intro-progress-wrap.visible { opacity: 1; }
#intro-progress-bar-bg {
    width: 100%;
    height: 3px;
    background: rgba(255,255,255,0.08);
    border-radius: 999px;
    overflow: hidden;
}
#intro-progress-bar-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6, #06b6d4);
    border-radius: 999px;
    transition: width 0.4s ease;
    box-shadow: 0 0 8px rgba(96,165,250,0.7);
}

/* ── Final fade overlay ───────────────────────────────────────────────────── */
#intro-fade-overlay {
    position: absolute;
    inset: 0;
    background: #020617;
    opacity: 0;
    pointer-events: none;
    transition: opacity 1.2s ease;
    z-index: 20;
}
#intro-fade-overlay.fading { opacity: 1; }

/* ── Bloom / glow pulse overlay ──────────────────────────────────────────── */
#intro-bloom-overlay {
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 45%, rgba(96,165,250,0.25) 0%, transparent 65%);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.4s ease;
}
#intro-bloom-overlay.glow { opacity: 1; animation: bloomPulse 0.5s ease-in-out 3; }

@keyframes bloomPulse {
    0%,100% { opacity: 0.3; }
    50%      { opacity: 1; }
}

/* ── Reduced motion fallback ──────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
    #intro-overlay { animation: none !important; }
}
</style>

<!-- ─── Three.js CDN ─────────────────────────────────────────────────────── -->
<script src="https://cdn.jsdelivr.net/npm/three@0.162.0/build/three.min.js"></script>

<!-- ─── Intro DOM ──────────────────────────────────────────────────────────── -->
<div id="intro-overlay" role="dialog" aria-label="Uvodni ekran" aria-modal="true">
    <canvas id="intro-rain-canvas"></canvas>
    <canvas id="intro-threejs-canvas"></canvas>

    <div id="intro-ui-layer">
        <div id="intro-logo-text" aria-live="polite">
            <span class="letter" data-l="B">B</span><span
                  class="letter" data-l="O">O</span><span
                  class="letter" data-l="O">O</span><span
                  class="letter" data-l="K">K</span><span
                  class="letter" data-l="L">L</span><span
                  class="letter" data-l="Y">Y</span><span
                  class="letter" data-l="F">F</span><span
                  class="letter" data-l="I">I</span>
        </div>
        <div id="intro-subtitle-text">TURBO CHARGED &thinsp;&#9889;</div>
        <div id="intro-loading-text">Initializing BOOKLYFI&hellip;</div>
    </div>

    <div id="intro-progress-wrap" aria-hidden="true">
        <div id="intro-progress-bar-bg">
            <div id="intro-progress-bar-fill"></div>
        </div>
    </div>

    <div id="intro-bloom-overlay" aria-hidden="true"></div>
    <div id="intro-fade-overlay" aria-hidden="true"></div>

    <button class="skip-intro-btn" id="skip-intro-btn"
            onclick="skipIntro()" aria-label="Preskoči intro">
        Preskoči
    </button>
</div>

<!-- ─── Intro Animation Script ────────────────────────────────────────────── -->
<script>
(function () {
"use strict";

// ── Respect prefers-reduced-motion ───────────────────────────────────────────
if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    forceStartApp();
    return;
}

// ── WebGL availability check ──────────────────────────────────────────────────
function webglAvailable() {
    try {
        const canvas = document.createElement('canvas');
        return !!(window.WebGLRenderingContext &&
            (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
    } catch(e) { return false; }
}
if (!webglAvailable() || typeof THREE === 'undefined') {
    // CSS-only fallback: just fade in app after 2s
    setTimeout(forceStartApp, 2000);
    return;
}

// ═════════════════════════════════════════════════════════════════════════════
//  CONSTANTS & STATE
// ═════════════════════════════════════════════════════════════════════════════
const TOTAL_DURATION = 12000; // ms
const IS_MOBILE = window.innerWidth < 640;
const PARTICLE_COUNT = IS_MOBILE ? 2200 : 5000;
const TRAIL_COUNT = IS_MOBILE ? 600 : 1400;

let startTime = null;
let rafId = null;
let appStarted = false;

// Three.js
let scene, camera, renderer, particleMesh, trailMesh, pointLight, ambientLight;
let positions, velocities, targets, colors, sizes, trails;
let bookTargets = [];
let logoTargets = [];
let phase = 0;

// ═════════════════════════════════════════════════════════════════════════════
//  DIGITAL RAIN (Canvas 2D)
// ═════════════════════════════════════════════════════════════════════════════
const rainCanvas = document.getElementById('intro-rain-canvas');
const rainCtx = rainCanvas.getContext('2d');
const RAIN_CHARS = '@#$%*01234⚡∞≡→∆Ω∑∏√π';
let rainColumns = [], rainDrops = [], rainActive = true;

function initRain() {
    rainCanvas.width  = window.innerWidth;
    rainCanvas.height = window.innerHeight;
    const colW = 18;
    const cols = Math.floor(rainCanvas.width / colW);
    rainColumns = Array.from({length: cols}, (_, i) => ({
        x: i * colW + 9,
        y: Math.random() * -400,
        speed: 1.5 + Math.random() * 2.5,
        chars: Array.from({length: 20}, () => RAIN_CHARS[Math.floor(Math.random() * RAIN_CHARS.length)])
    }));
}

function renderRain(t) {
    rainCtx.fillStyle = 'rgba(2,6,23,0.18)';
    rainCtx.fillRect(0, 0, rainCanvas.width, rainCanvas.height);

    const alpha = Math.max(0, 1 - (t - 800) / 1400);
    if (alpha <= 0) {
        if (rainActive) {
            rainCtx.clearRect(0, 0, rainCanvas.width, rainCanvas.height);
            rainActive = false;
        }
        return;
    }

    rainCtx.font = '14px "JetBrains Mono", monospace';
    for (const col of rainColumns) {
        col.y += col.speed;
        if (col.y > rainCanvas.height) col.y = -240;
        for (let j = 0; j < col.chars.length; j++) {
            const cy = col.y - j * 16;
            if (cy < -20 || cy > rainCanvas.height + 20) continue;
            const fade = j === 0 ? 1 : (1 - j / col.chars.length) * 0.7;
            const g = j === 0
                ? `rgba(224,242,254,${fade * alpha})`
                : `rgba(96,165,250,${fade * alpha * 0.8})`;
            rainCtx.fillStyle = g;
            // mutate chars occasionally
            if (Math.random() < 0.01)
                col.chars[j] = RAIN_CHARS[Math.floor(Math.random() * RAIN_CHARS.length)];
            rainCtx.fillText(col.chars[j], col.x, cy);
        }
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  THREE.JS SETUP
// ═════════════════════════════════════════════════════════════════════════════
function initThree() {
    const W = window.innerWidth, H = window.innerHeight;
    scene = new THREE.Scene();

    camera = new THREE.PerspectiveCamera(70, W / H, 0.1, 2000);
    camera.position.set(0, 0, 100);

    renderer = new THREE.WebGLRenderer({
        canvas: document.getElementById('intro-threejs-canvas'),
        antialias: !IS_MOBILE,
        alpha: true
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(W, H);
    renderer.setClearColor(0x020617, 1);

    // Lights
    ambientLight = new THREE.AmbientLight(0x60a5fa, 0.4);
    scene.add(ambientLight);
    pointLight = new THREE.PointLight(0x60a5fa, 3, 200);
    pointLight.position.set(0, 0, 50);
    scene.add(pointLight);

    buildParticleSystem();
    buildTrailSystem();
}

// ── Particle system ──────────────────────────────────────────────────────────
function buildParticleSystem() {
    const geo = new THREE.BufferGeometry();
    positions  = new Float32Array(PARTICLE_COUNT * 3);
    velocities = new Float32Array(PARTICLE_COUNT * 3);
    targets    = new Float32Array(PARTICLE_COUNT * 3);
    colors     = new Float32Array(PARTICLE_COUNT * 3);
    sizes      = new Float32Array(PARTICLE_COUNT);

    // Scatter particles randomly (start state)
    for (let i = 0; i < PARTICLE_COUNT; i++) {
        const si = i * 3;
        const r = 200 + Math.random() * 200;
        const theta = Math.random() * Math.PI * 2;
        const phi   = Math.acos(2 * Math.random() - 1);
        positions[si]   = r * Math.sin(phi) * Math.cos(theta);
        positions[si+1] = r * Math.sin(phi) * Math.sin(theta);
        positions[si+2] = r * Math.cos(phi) - 100;
        velocities[si]   = 0;
        velocities[si+1] = 0;
        velocities[si+2] = 0;
        targets[si]   = positions[si];
        targets[si+1] = positions[si+1];
        targets[si+2] = positions[si+2];
        colors[si]   = 0.37;
        colors[si+1] = 0.65;
        colors[si+2] = 0.98;
        sizes[i] = IS_MOBILE ? 1.2 : 1.6;
    }

    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color',    new THREE.BufferAttribute(colors, 3));
    geo.setAttribute('size',     new THREE.BufferAttribute(sizes, 1));

    const mat = new THREE.PointsMaterial({
        size: IS_MOBILE ? 1.4 : 1.8,
        vertexColors: true,
        transparent: true,
        opacity: 0,
        sizeAttenuation: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });
    particleMesh = new THREE.Points(geo, mat);
    scene.add(particleMesh);
}

// ── Trail system ─────────────────────────────────────────────────────────────
function buildTrailSystem() {
    const geo = new THREE.BufferGeometry();
    trails = new Float32Array(TRAIL_COUNT * 3);
    const tc = new Float32Array(TRAIL_COUNT * 3);
    const ts = new Float32Array(TRAIL_COUNT);
    for (let i = 0; i < TRAIL_COUNT; i++) {
        trails[i*3]   = (Math.random()-0.5)*400;
        trails[i*3+1] = (Math.random()-0.5)*400;
        trails[i*3+2] = (Math.random()-0.5)*200;
        tc[i*3]   = 0.02;
        tc[i*3+1] = 0.71;
        tc[i*3+2] = 0.83;
        ts[i] = IS_MOBILE ? 0.6 : 0.9;
    }
    geo.setAttribute('position', new THREE.BufferAttribute(trails, 3));
    geo.setAttribute('color',    new THREE.BufferAttribute(tc, 3));
    geo.setAttribute('size',     new THREE.BufferAttribute(ts, 1));
    const mat = new THREE.PointsMaterial({
        size: 0.9,
        vertexColors: true,
        transparent: true,
        opacity: 0,
        sizeAttenuation: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });
    trailMesh = new THREE.Points(geo, mat);
    scene.add(trailMesh);
}

// ═════════════════════════════════════════════════════════════════════════════
//  TARGET GENERATORS
// ═════════════════════════════════════════════════════════════════════════════

// Book silhouette (3D cuboid made of voxel positions)
function genBookTargets() {
    const pts = [];
    const W=28, H=38, D=8;
    for (let i=0; i<PARTICLE_COUNT; i++) {
        let x, y, z;
        const r = Math.random();
        if (r < 0.35) {
            // cover face
            x = (Math.random()-0.5)*W;
            y = (Math.random()-0.5)*H;
            z = D/2 + (Math.random()-0.5)*1.5;
        } else if (r < 0.55) {
            // spine
            x = -W/2 + (Math.random()-0.5)*2;
            y = (Math.random()-0.5)*H;
            z = (Math.random()-0.5)*D;
        } else if (r < 0.70) {
            // back cover
            x = (Math.random()-0.5)*W;
            y = (Math.random()-0.5)*H;
            z = -D/2 + (Math.random()-0.5)*1.5;
        } else if (r < 0.85) {
            // pages (right edge)
            x = W/2 + (Math.random()-0.5)*1.5;
            y = (Math.random()-0.5)*H;
            z = (Math.random()-0.5)*D;
        } else {
            // top/bottom edges
            const top = Math.random() < 0.5;
            x = (Math.random()-0.5)*W;
            y = top ? H/2 : -H/2;
            z = (Math.random()-0.5)*D;
        }
        pts.push(x, y, z);
    }
    return pts;
}

// Logo text shape (horizontal bars approximating 8 letters "BOOKLYFI")
function genLogoTargets() {
    // 8 letter blocks, each ~10 units wide, ~15 tall
    const pts = [];
    const letW = 8, letH = 14, spacing = 12;
    const totalW = 8 * spacing;
    const startX = -totalW / 2 + spacing/2;

    // Simple pixel font for each letter — 5×7 bitmaps
    const FONT = {
        B: [[1,1,1,0],[1,0,0,1],[1,1,1,0],[1,0,0,1],[1,1,1,0]],
        O: [[1,1,1,1],[1,0,0,1],[1,0,0,1],[1,0,0,1],[1,1,1,1]],
        K: [[1,0,0,1],[1,0,1,0],[1,1,0,0],[1,0,1,0],[1,0,0,1]],
        L: [[1,0,0,0],[1,0,0,0],[1,0,0,0],[1,0,0,0],[1,1,1,1]],
        Y: [[1,0,0,1],[1,0,0,1],[0,1,1,0],[0,1,0,0],[0,1,0,0]],
        F: [[1,1,1,1],[1,0,0,0],[1,1,1,0],[1,0,0,0],[1,0,0,0]],
        I: [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[1,1,1]],
    };
    const letters = ['B','O','O','K','L','Y','F','I'];
    const ppLetter = Math.floor(PARTICLE_COUNT / letters.length);

    for (let li = 0; li < letters.length; li++) {
        const lx = startX + li * spacing;
        const bitmap = FONT[letters[li]];
        const rows = bitmap.length;
        const cols = bitmap[0].length;
        for (let p = 0; p < ppLetter; p++) {
            const ri = Math.floor(Math.random() * rows);
            const ci = Math.floor(Math.random() * cols);
            if (bitmap[ri][ci]) {
                pts.push(
                    lx + (ci / (cols-1) - 0.5) * letW + (Math.random()-0.5)*0.8,
                    (0.5 - ri / (rows-1)) * letH  + (Math.random()-0.5)*0.8,
                    (Math.random()-0.5)*2
                );
            } else {
                // push to random offscreen — will never be "visible" (transparent)
                const scatter = 250;
                pts.push(
                    (Math.random()-0.5)*scatter,
                    (Math.random()-0.5)*scatter,
                    (Math.random()-0.5)*scatter*0.5
                );
            }
        }
    }
    // pad to exactly PARTICLE_COUNT
    while (pts.length < PARTICLE_COUNT * 3) {
        pts.push((Math.random()-0.5)*200,(Math.random()-0.5)*200,(Math.random()-0.5)*100);
    }
    return pts.slice(0, PARTICLE_COUNT * 3);
}

// ═════════════════════════════════════════════════════════════════════════════
//  LERP HELPERS
// ═════════════════════════════════════════════════════════════════════════════
function lerp(a, b, t) { return a + (b - a) * t; }
function easeInOut(t) { return t < 0.5 ? 2*t*t : -1+(4-2*t)*t; }
function easeOut(t) { return 1 - Math.pow(1-t, 3); }
function easeIn(t) { return t * t * t; }

// ═════════════════════════════════════════════════════════════════════════════
//  MAIN ANIMATION LOOP
// ═════════════════════════════════════════════════════════════════════════════
function animate(ts) {
    rafId = requestAnimationFrame(animate);
    if (!startTime) startTime = ts;
    const elapsed = ts - startTime; // ms
    const t = Math.min(elapsed / TOTAL_DURATION, 1.0); // 0..1

    updateProgress(t);
    updatePhases(elapsed, t, ts);

    if (rainActive) renderRain(elapsed);

    renderer.render(scene, camera);
}

// ── Progress bar & loading text ───────────────────────────────────────────────
function updateProgress(t) {
    const fill = document.getElementById('intro-progress-bar-fill');
    if (fill) fill.style.width = (t * 100).toFixed(1) + '%';
}

// ═════════════════════════════════════════════════════════════════════════════
//  PHASE LOGIC
// ═════════════════════════════════════════════════════════════════════════════
let _bookTargetsArr = null;
let _logoTargetsArr = null;
let _phaseInited = {};

function updatePhases(elapsed, t, ts) {
    const pos = particleMesh.geometry.attributes.position.array;
    const col = particleMesh.geometry.attributes.color.array;
    const sz  = particleMesh.geometry.attributes.size.array;
    const trailPos = trailMesh.geometry.attributes.position.array;
    const pMat = particleMesh.material;
    const tMat = trailMesh.material;

    // ── Phase 1 · 0-1 s · Digital rain + particles fade in ────────────────────
    if (elapsed < 1000) {
        if (!_phaseInited[1]) {
            _phaseInited[1] = true;
        }
        pMat.opacity = lerp(0, 0.3, elapsed / 1000);
        // particles scattered — no movement yet

    // ── Phase 2 · 1-3 s · Book assembly ───────────────────────────────────────
    } else if (elapsed < 3000) {
        if (!_phaseInited[2]) {
            _phaseInited[2] = true;
            _bookTargetsArr = genBookTargets();
            document.getElementById('intro-progress-wrap').classList.add('visible');
        }
        const p2 = (elapsed - 1000) / 2000;
        const ease = easeInOut(p2);
        pMat.opacity = lerp(0.3, 0.9, p2);
        tMat.opacity = lerp(0, 0.15, p2);

        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const si = i * 3;
            const bt = _bookTargetsArr;
            pos[si]   = lerp(pos[si],   bt[si],   0.04 + 0.03*ease);
            pos[si+1] = lerp(pos[si+1], bt[si+1], 0.04 + 0.03*ease);
            pos[si+2] = lerp(pos[si+2], bt[si+2], 0.04 + 0.03*ease);
            // Color: blue → cyan
            col[si]   = lerp(col[si],   0.37, 0.03);
            col[si+1] = lerp(col[si+1], 0.65, 0.03);
            col[si+2] = lerp(col[si+2], 0.98, 0.03);
            sz[i] = IS_MOBILE ? lerp(sz[i], 1.2, 0.02) : lerp(sz[i], 1.6, 0.02);
        }
        // Gentle book rotation
        particleMesh.rotation.y = Math.sin(elapsed * 0.0008) * 0.3;
        particleMesh.rotation.x = Math.sin(elapsed * 0.0005) * 0.12;

    // ── Phase 3 · 3-5 s · Book dissolution — pages scatter ───────────────────
    } else if (elapsed < 5000) {
        if (!_phaseInited[3]) {
            _phaseInited[3] = true;
            // Assign random scatter velocities
            for (let i = 0; i < PARTICLE_COUNT; i++) {
                const si = i * 3;
                const angle = Math.random() * Math.PI * 2;
                const lift  = (Math.random()-0.5)*0.8 + 0.3;
                const speed = 0.4 + Math.random() * 1.2;
                velocities[si]   = Math.cos(angle) * speed;
                velocities[si+1] = lift * speed;
                velocities[si+2] = (Math.random()-0.5) * speed * 0.6;
            }
        }
        const p3 = (elapsed - 3000) / 2000;
        pMat.opacity = lerp(0.9, 0.75, p3);
        tMat.opacity = lerp(0.15, 0.45, p3);

        particleMesh.rotation.y += 0.005;
        particleMesh.rotation.x += 0.002;

        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const si = i * 3;
            // explode out from book
            pos[si]   += velocities[si]   * 0.9;
            pos[si+1] += velocities[si+1] * 0.9;
            pos[si+2] += velocities[si+2] * 0.9;
            // drift trails behind
            trailPos[si]   = pos[si]   - velocities[si]   * 3;
            trailPos[si+1] = pos[si+1] - velocities[si+1] * 3;
            trailPos[si+2] = pos[si+2] - velocities[si+2] * 3;
            // Color → white/bright cyan
            col[si]   = lerp(col[si],   0.9, 0.015);
            col[si+1] = lerp(col[si+1], 0.95, 0.015);
            col[si+2] = lerp(col[si+2], 1.0, 0.015);
            sz[i] = lerp(sz[i], IS_MOBILE ? 1.8 : 2.4, 0.012);
        }

    // ── Phase 4 · 5-7 s · Spiral / helix flow ─────────────────────────────────
    } else if (elapsed < 7000) {
        if (!_phaseInited[4]) {
            _phaseInited[4] = true;
            particleMesh.rotation.set(0, 0, 0);
        }
        const p4 = (elapsed - 5000) / 2000;
        tMat.opacity = lerp(0.45, 0.3, p4);
        pMat.opacity = lerp(0.75, 0.85, p4);

        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const si = i * 3;
            const phase_i = (i / PARTICLE_COUNT) * Math.PI * 2;
            const speed4  = 0.002 + (i % 7) * 0.0003;
            // spiral
            const angle   = elapsed * speed4 + phase_i;
            const radius  = 30 + 40 * ((i % 100) / 100);
            const helixY  = Math.sin(elapsed * 0.001 + phase_i * 0.3) * 25;

            const tx = Math.cos(angle) * radius;
            const ty = helixY + Math.sin(angle * 0.5 + phase_i) * 15;
            const tz = Math.sin(angle) * radius * 0.4 + Math.cos(elapsed * 0.0006 + phase_i) * 20;

            pos[si]   = lerp(pos[si],   tx, 0.025);
            pos[si+1] = lerp(pos[si+1], ty, 0.025);
            pos[si+2] = lerp(pos[si+2], tz, 0.025);

            trailPos[si]   = pos[si]   - (tx - pos[si]) * 2;
            trailPos[si+1] = pos[si+1] - (ty - pos[si+1]) * 2;
            trailPos[si+2] = pos[si+2] - (tz - pos[si+2]) * 2;

            // Color: blue / purple swirl
            const hue = (i / PARTICLE_COUNT + elapsed * 0.00008) % 1;
            col[si]   = lerp(0.37, 0.65, Math.abs(Math.sin(hue * Math.PI)));
            col[si+1] = lerp(0.55, 0.82, Math.abs(Math.cos(hue * Math.PI)));
            col[si+2] = 0.97;
            sz[i] = IS_MOBILE ? 1.4 : 1.8;
        }
        // Camera drift
        camera.position.x = Math.sin(elapsed * 0.00025) * 8;
        camera.position.y = Math.cos(elapsed * 0.0002) * 4;
        camera.lookAt(0, 0, 0);

    // ── Phase 5 · 7-9 s · Logo convergence ────────────────────────────────────
    } else if (elapsed < 9000) {
        if (!_phaseInited[5]) {
            _phaseInited[5] = true;
            _logoTargetsArr = genLogoTargets();
        }
        const p5 = (elapsed - 7000) / 2000;
        const ease5 = easeInOut(p5);
        pMat.opacity = lerp(0.85, 1.0, p5);
        tMat.opacity = lerp(0.3, 0.1, p5);

        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const si = i * 3;
            const lt = _logoTargetsArr;
            const speed = 0.06 + 0.04 * ease5;
            pos[si]   = lerp(pos[si],   lt[si],   speed);
            pos[si+1] = lerp(pos[si+1], lt[si+1], speed);
            pos[si+2] = lerp(pos[si+2], lt[si+2], speed);
            // Color → bright blue/white
            col[si]   = lerp(col[si],   0.6, 0.03);
            col[si+1] = lerp(col[si+1], 0.8, 0.03);
            col[si+2] = lerp(col[si+2], 1.0, 0.03);
            sz[i] = lerp(sz[i], IS_MOBILE ? 1.0 : 1.3, 0.025);
        }
        // Dynamic point light intensity
        pointLight.intensity = 3 + Math.sin(elapsed * 0.005) * 1.5;
        // Camera zoom in
        camera.position.z = lerp(camera.position.z, 75, 0.015);
        camera.position.x = lerp(camera.position.x, 0, 0.05);
        camera.position.y = lerp(camera.position.y, 0, 0.05);
        camera.lookAt(0, 0, 0);

    // ── Phase 6 · 9-10 s · Text assembly ─────────────────────────────────────
    } else if (elapsed < 10000) {
        if (!_phaseInited[6]) {
            _phaseInited[6] = true;
            // Show logo text container
            document.getElementById('intro-logo-text').classList.add('visible');
            document.getElementById('intro-loading-text').classList.add('visible');
            // Stagger letters
            const letters = document.querySelectorAll('#intro-logo-text .letter');
            letters.forEach((el, i) => {
                setTimeout(() => el.classList.add('in'), i * 80);
            });
            // Subtitle
            setTimeout(() => {
                document.getElementById('intro-subtitle-text').classList.add('visible');
            }, 700);
        }
        const p6 = (elapsed - 9000) / 1000;
        pMat.opacity = lerp(1.0, 0.55, p6);
        tMat.opacity = lerp(0.1, 0.0, p6);
        // subtle orbit around logo
        const angle6 = elapsed * 0.001;
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            const si = i * 3;
            const lt = _logoTargetsArr;
            pos[si]   = lerp(pos[si],   lt[si],   0.03);
            pos[si+1] = lerp(pos[si+1], lt[si+1], 0.03);
            pos[si+2] = lerp(pos[si+2], lt[si+2], 0.03);
        }
        pointLight.intensity = 4 + Math.sin(elapsed * 0.01) * 2;

    // ── Phase 7 · 10-11 s · Glow crescendo ────────────────────────────────────
    } else if (elapsed < 11000) {
        if (!_phaseInited[7]) {
            _phaseInited[7] = true;
            document.getElementById('intro-bloom-overlay').classList.add('glow');
        }
        const p7 = (elapsed - 10000) / 1000;
        pMat.opacity = lerp(0.55, 0.2, p7);
        // Pulse point light
        pointLight.intensity = 6 + Math.sin(elapsed * 0.03) * 3;

    // ── Phase 8 · 11-12 s · Fade out ─────────────────────────────────────────
    } else if (elapsed < 12000) {
        if (!_phaseInited[8]) {
            _phaseInited[8] = true;
            document.getElementById('intro-fade-overlay').classList.add('fading');
        }
        const p8 = (elapsed - 11000) / 1000;
        pMat.opacity = Math.max(0, lerp(0.2, 0, p8));
        tMat.opacity = 0;

    // ── Done ─────────────────────────────────────────────────────────────────
    } else {
        forceStartApp();
        return;
    }

    // Invalidate buffer geometries
    particleMesh.geometry.attributes.position.needsUpdate = true;
    particleMesh.geometry.attributes.color.needsUpdate    = true;
    particleMesh.geometry.attributes.size.needsUpdate     = true;
    if (_phaseInited[3] || _phaseInited[4]) {
        trailMesh.geometry.attributes.position.needsUpdate = true;
    }
}

// ═════════════════════════════════════════════════════════════════════════════
//  PUBLIC: Skip & Force Start
// ═════════════════════════════════════════════════════════════════════════════
window.skipIntro = function() {
    forceStartApp();
};

function forceStartApp() {
    if (appStarted) return;
    appStarted = true;
    if (rafId) cancelAnimationFrame(rafId);

    // Fade then remove overlay
    const overlay = document.getElementById('intro-overlay');
    const fadeEl  = document.getElementById('intro-fade-overlay');
    if (fadeEl) fadeEl.classList.add('fading');
    setTimeout(() => {
        if (overlay) overlay.remove();
        const mainUI = document.getElementById('main-ui-wrapper');
        if (mainUI) {
            mainUI.style.display = 'block';
            requestAnimationFrame(() => {
                mainUI.style.opacity = '1';
                document.body.style.overflow = '';
            });
        }
        // Cleanup Three.js
        if (renderer) {
            renderer.dispose();
            if (particleMesh) { particleMesh.geometry.dispose(); particleMesh.material.dispose(); }
            if (trailMesh) { trailMesh.geometry.dispose(); trailMesh.material.dispose(); }
        }
    }, 1300);
}

// ═════════════════════════════════════════════════════════════════════════════
//  RESIZE
// ═════════════════════════════════════════════════════════════════════════════
function onResize() {
    const W = window.innerWidth, H = window.innerHeight;
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    renderer.setSize(W, H);
    rainCanvas.width  = W;
    rainCanvas.height = H;
    initRain();
}
window.addEventListener('resize', onResize, {passive: true});

// ═════════════════════════════════════════════════════════════════════════════
//  BOOT
// ═════════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', function bootIntro() {
    document.body.style.overflow = 'hidden';

    // Show skip button after 2 s
    setTimeout(() => {
        const btn = document.getElementById('skip-intro-btn');
        if (btn) btn.style.display = 'block';
    }, 2000);

    initRain();
    initThree();
    requestAnimationFrame(animate);

    // Hard failsafe — always show UI after 14s
    setTimeout(() => { if (!appStarted) forceStartApp(); }, 14000);
}, {once: true});

})();
</script>
"""
