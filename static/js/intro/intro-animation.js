

// ============================================================================
// BOOKLYFI INTRO — Main IntroAnimation Orchestrator
// ============================================================================
// Depends on:
//   • THREE (three.min.js CDN)
//   • genBookTargets / genLogoTargets  (particle-system.js)
//   • DigitalRain                      (post-processing.js)

class IntroAnimation {
    constructor() {
        // Three.js objects
        this.scene        = null;
        this.camera       = null;
        this.renderer     = null;
        this.particleMesh = null;
        this.trailMesh    = null;
        this.pointLight   = null;
        this.ambientLight = null;

        // Typed arrays for GPU buffers
        this.positions  = null;
        this.velocities = null;
        this.targets    = null;
        this.colors     = null;
        this.sizes      = null;
        this.trails     = null;

        // Cached target shapes
        this._bookTargetsArr = null;
        this._logoTargetsArr = null;
        this._phaseInited    = {};

        // Digital rain
        this.rain = null;

        // Timing
        this.startTime       = null;
        this.rafId           = null;
        this.appStarted      = false;
        this._threeRetryCount = 0;

        // Responsive constants — more, smaller particles for denser logo formation
        this.IS_MOBILE      = window.innerWidth < 640;
        this.PARTICLE_COUNT = this.IS_MOBILE ? 6000 : 18000;
        this.TRAIL_COUNT    = this.IS_MOBILE ?  800 :  2000;
        this.TOTAL_DURATION      = 15000; // ms (longer to allow book hold + clear logo)
        this.PRELOAD_FADE_MS     = 400;   // must match CSS transition on #intro-pre-load
    }

    // =========================================================================
    //  PUBLIC ENTRY POINT
    // =========================================================================
    init() {
        // Respect prefers-reduced-motion
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            this._finish();
            return;
        }

        // Require WebGL
        if (!this._webglAvailable()) {
            setTimeout(() => this._finish(), 2000);
            return;
        }

        // Wait for Three.js (deferred script may still be loading) — retry up to 20×200ms
        if (typeof THREE === 'undefined') {
            if (this._threeRetryCount < 20) {
                this._threeRetryCount++;
                setTimeout(() => this.init(), 200);
            } else {
                setTimeout(() => this._finish(), 2000);
            }
            return;
        }

        document.body.style.overflow = 'hidden';

        // Show skip button after 2 s
        setTimeout(() => {
            const btn = document.getElementById('skip-intro-btn');
            if (btn) btn.style.display = 'block';
        }, 2000);

        try {
            // Digital rain removed — V8 SVG ghost background replaces it
            this._initThree();
        } catch (e) {
            // Three.js initialisation failed — keep dots visible as fallback and redirect
            this._restorePreload();
            setTimeout(() => this._finish(), 2000);
            return;
        }

        // Kick off the loop; the pre-loader dots are hidden only after the first frame
        // successfully renders so the user always sees the CSS fallback briefly.
        this.rafId = requestAnimationFrame(ts => this._animate(ts));

        // Hard failsafe — always proceed after 18 s
        setTimeout(() => { if (!this.appStarted) this._finish(); }, 18000);
    }

    // =========================================================================
    //  WEBGL CHECK
    // =========================================================================
    _webglAvailable() {
        try {
            const c = document.createElement('canvas');
            return !!(window.WebGLRenderingContext &&
                (c.getContext('webgl') || c.getContext('experimental-webgl')));
        } catch (_) { return false; }
    }

    // =========================================================================
    //  THREE.JS INITIALISATION
    // =========================================================================
    _initThree() {
        const W = window.innerWidth, H = window.innerHeight;

        this.scene = new THREE.Scene();

        this.camera = new THREE.PerspectiveCamera(70, W / H, 0.1, 2000);
        this.camera.position.set(0, 0, 100);

        this.renderer = new THREE.WebGLRenderer({
            canvas:    document.getElementById('intro-threejs-canvas'),
            antialias: !this.IS_MOBILE,
            alpha:     true,
        });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.setSize(W, H);
        // Transparent clear so the digital-rain canvas underneath shows through
        this.renderer.setClearColor(0x000000, 0);

        this.ambientLight = new THREE.AmbientLight(0x60a5fa, 0.4);
        this.scene.add(this.ambientLight);

        this.pointLight = new THREE.PointLight(0x60a5fa, 3, 200);
        this.pointLight.position.set(0, 0, 50);
        this.scene.add(this.pointLight);

        this._buildParticleSystem();
        this._buildTrailSystem();

        window.addEventListener('resize', () => this._onResize(), { passive: true });
    }

    // =========================================================================
    //  GEOMETRY BUILDERS
    // =========================================================================
    _buildParticleSystem() {
        const N   = this.PARTICLE_COUNT;
        const geo = new THREE.BufferGeometry();

        this.positions  = new Float32Array(N * 3);
        this.velocities = new Float32Array(N * 3);
        this.targets    = new Float32Array(N * 3);
        this.colors     = new Float32Array(N * 3);
        this.sizes      = new Float32Array(N);

        for (let i = 0; i < N; i++) {
            const si    = i * 3;
            const r     = 200 + Math.random() * 200;
            const theta = Math.random() * Math.PI * 2;
            const phi   = Math.acos(2 * Math.random() - 1);
            this.positions[si]   = r * Math.sin(phi) * Math.cos(theta);
            this.positions[si+1] = r * Math.sin(phi) * Math.sin(theta);
            this.positions[si+2] = r * Math.cos(phi) - 100;
            this.colors[si]   = 0.37;
            this.colors[si+1] = 0.65;
            this.colors[si+2] = 0.98;
            this.sizes[i] = this.IS_MOBILE ? 0.5 : 0.65;
        }

        geo.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
        geo.setAttribute('color',    new THREE.BufferAttribute(this.colors,    3));
        geo.setAttribute('size',     new THREE.BufferAttribute(this.sizes,     1));

        const mat = new THREE.PointsMaterial({
            size:          this.IS_MOBILE ? 0.55 : 0.70,
            vertexColors:  true,
            transparent:   true,
            opacity:       0,
            sizeAttenuation: true,
            blending:      THREE.AdditiveBlending,
            depthWrite:    false,
        });
        this.particleMesh = new THREE.Points(geo, mat);
        this.scene.add(this.particleMesh);
    }

    _buildTrailSystem() {
        const N   = this.TRAIL_COUNT;
        const geo = new THREE.BufferGeometry();

        this.trails = new Float32Array(N * 3);
        const tc    = new Float32Array(N * 3);
        const ts    = new Float32Array(N);

        for (let i = 0; i < N; i++) {
            this.trails[i*3]   = (Math.random() - 0.5) * 400;
            this.trails[i*3+1] = (Math.random() - 0.5) * 400;
            this.trails[i*3+2] = (Math.random() - 0.5) * 200;
            tc[i*3]   = 0.02;
            tc[i*3+1] = 0.71;
            tc[i*3+2] = 0.83;
            ts[i] = this.IS_MOBILE ? 0.3 : 0.45;
        }

        geo.setAttribute('position', new THREE.BufferAttribute(this.trails, 3));
        geo.setAttribute('color',    new THREE.BufferAttribute(tc, 3));
        geo.setAttribute('size',     new THREE.BufferAttribute(ts, 1));

        const mat = new THREE.PointsMaterial({
            size:          0.6,
            vertexColors:  true,
            transparent:   true,
            opacity:       0,
            sizeAttenuation: true,
            blending:      THREE.AdditiveBlending,
            depthWrite:    false,
        });
        this.trailMesh = new THREE.Points(geo, mat);
        this.scene.add(this.trailMesh);
    }

    // =========================================================================
    //  MATH HELPERS
    // =========================================================================
    _lerp(a, b, t)    { return a + (b - a) * t; }
    _easeInOut(t)     { return t < 0.5 ? 2*t*t : -1+(4-2*t)*t; }
    _easeOut(t)       { return 1 - Math.pow(1-t, 3); }

    // =========================================================================
    //  MAIN ANIMATION LOOP
    // =========================================================================
    _animate(ts) {
        this.rafId = requestAnimationFrame(ts2 => this._animate(ts2));
        if (!this.startTime) this.startTime = ts;

        const elapsed = ts - this.startTime;
        const t       = Math.min(elapsed / this.TOTAL_DURATION, 1.0);

        this._updateProgress(t);
        this._updatePhases(elapsed);

        if (this.rain && this.rain.active) this.rain.render(elapsed);

        try {
            this.renderer.render(this.scene, this.camera);
        } catch (e) {
            // WebGL render failed — cancel loop, restore dots, redirect shortly
            cancelAnimationFrame(this.rafId);
            this._restorePreload();
            if (!this.appStarted) setTimeout(() => this._finish(), 2000);
            return;
        }

        // Hide the CSS pre-loader on the first successfully rendered frame
        if (!this._preloadHidden) {
            this._preloadHidden = true;
            const preLoad = document.getElementById('intro-pre-load');
            if (preLoad) preLoad.classList.add('fading-out');
            setTimeout(() => {
                if (preLoad) preLoad.classList.add('hidden');
            }, this.PRELOAD_FADE_MS);
        }
    }

    _restorePreload() {
        const preLoad = document.getElementById('intro-pre-load');
        if (preLoad) {
            preLoad.classList.remove('fading-out', 'hidden');
        }
    }

    _updateProgress(t) {
        const fill = document.getElementById('intro-progress-bar-fill');
        if (fill) fill.style.width = (t * 100).toFixed(1) + '%';
    }

    // =========================================================================
    //  PHASE LOGIC  (8 phases · 0-12 s)
    // =========================================================================
    _updatePhases(elapsed) {
        const pos      = this.particleMesh.geometry.attributes.position.array;
        const col      = this.particleMesh.geometry.attributes.color.array;
        const sz       = this.particleMesh.geometry.attributes.size.array;
        const trailPos = this.trailMesh.geometry.attributes.position.array;
        const pMat     = this.particleMesh.material;
        const tMat     = this.trailMesh.material;
        const lerp     = this._lerp.bind(this);

        // ── Phase 1 · 0-1 s · Digital rain + particles fade in ───────────────
        if (elapsed < 1000) {
            pMat.opacity = lerp(0, 0.6, elapsed / 1000);

        // ── Phase 2 · 1-4 s · Book assembly ──────────────────────────────────
        } else if (elapsed < 4000) {
            if (!this._phaseInited[2]) {
                this._phaseInited[2]  = true;
                this._bookTargetsArr  = genBookTargets(this.PARTICLE_COUNT);
                const pw = document.getElementById('intro-progress-wrap');
                if (pw) pw.classList.add('visible');
            }
            const p2   = (elapsed - 1000) / 3000;
            const ease = this._easeInOut(p2);
            pMat.opacity = lerp(0.6, 0.92, p2);
            tMat.opacity = lerp(0, 0.15, p2);

            const bt = this._bookTargetsArr;
            for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                const si = i * 3;
                const sp = 0.03 + 0.02 * ease;
                pos[si]   = lerp(pos[si],   bt[si],   sp);
                pos[si+1] = lerp(pos[si+1], bt[si+1], sp);
                pos[si+2] = lerp(pos[si+2], bt[si+2], sp);
                col[si]   = lerp(col[si],   0.37, 0.03);
                col[si+1] = lerp(col[si+1], 0.65, 0.03);
                col[si+2] = lerp(col[si+2], 0.98, 0.03);
                sz[i] = this.IS_MOBILE ? lerp(sz[i], 0.5, 0.015) : lerp(sz[i], 0.65, 0.015);
            }
            this.particleMesh.rotation.y = Math.sin(elapsed * 0.0008) * 0.3;
            this.particleMesh.rotation.x = Math.sin(elapsed * 0.0005) * 0.12;

        // ── Phase 2b · 4-6 s · Hold book steady — "šta je u pitanju" ─────────
        } else if (elapsed < 6000) {
            if (!this._phaseInited[21]) {
                this._phaseInited[21] = true;
            }
            // Stabilise book: slow gentle rotation, high opacity
            const p2b = (elapsed - 4000) / 2000;
            pMat.opacity = lerp(0.92, 0.88, p2b);
            tMat.opacity = lerp(0.15, 0.10, p2b);
            const bt = this._bookTargetsArr;
            for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                const si = i * 3;
                pos[si]   = lerp(pos[si],   bt[si],   0.015);
                pos[si+1] = lerp(pos[si+1], bt[si+1], 0.015);
                pos[si+2] = lerp(pos[si+2], bt[si+2], 0.015);
            }
            this.particleMesh.rotation.y = Math.sin(elapsed * 0.0004) * 0.12;
            this.particleMesh.rotation.x = Math.sin(elapsed * 0.0003) * 0.05;

        // ── Phase 3 · 6-8 s · Dissolution — pages scatter ────────────────────
        } else if (elapsed < 8000) {
            if (!this._phaseInited[3]) {
                this._phaseInited[3] = true;
                for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                    const si    = i * 3;
                    const angle = Math.random() * Math.PI * 2;
                    const lift  = (Math.random() - 0.5) * 0.8 + 0.3;
                    const speed = 0.4 + Math.random() * 1.2;
                    this.velocities[si]   = Math.cos(angle) * speed;
                    this.velocities[si+1] = lift * speed;
                    this.velocities[si+2] = (Math.random() - 0.5) * speed * 0.6;
                }
            }
            const p3 = (elapsed - 6000) / 2000;
            pMat.opacity = lerp(0.88, 0.75, p3);
            tMat.opacity = lerp(0.10, 0.45, p3);
            this.particleMesh.rotation.y += 0.005;
            this.particleMesh.rotation.x += 0.002;

            for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                const si = i * 3;
                pos[si]       += this.velocities[si]   * 0.9;
                pos[si+1]     += this.velocities[si+1] * 0.9;
                pos[si+2]     += this.velocities[si+2] * 0.9;
                if (i < this.TRAIL_COUNT) {
                    trailPos[si]   = pos[si]   - this.velocities[si]   * 3;
                    trailPos[si+1] = pos[si+1] - this.velocities[si+1] * 3;
                    trailPos[si+2] = pos[si+2] - this.velocities[si+2] * 3;
                }
                col[si]   = lerp(col[si],   0.9,  0.015);
                col[si+1] = lerp(col[si+1], 0.95, 0.015);
                col[si+2] = lerp(col[si+2], 1.0,  0.015);
                sz[i] = lerp(sz[i], this.IS_MOBILE ? 0.9 : 1.1, 0.012);
            }

        // ── Phase 4 · 8-10 s · Spiral / helix flow ───────────────────────────
        } else if (elapsed < 10000) {
            if (!this._phaseInited[4]) {
                this._phaseInited[4] = true;
                this.particleMesh.rotation.set(0, 0, 0);
            }
            const p4 = (elapsed - 8000) / 2000;
            tMat.opacity = lerp(0.45, 0.3, p4);
            pMat.opacity = lerp(0.75, 0.85, p4);

            for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                const si      = i * 3;
                const phase_i = (i / this.PARTICLE_COUNT) * Math.PI * 2;
                const speed4  = 0.002 + (i % 7) * 0.0003;
                const angle   = elapsed * speed4 + phase_i;
                const radius  = 30 + 40 * ((i % 100) / 100);
                const helixY  = Math.sin(elapsed * 0.001 + phase_i * 0.3) * 25;
                const tx = Math.cos(angle) * radius;
                const ty = helixY + Math.sin(angle * 0.5 + phase_i) * 15;
                const tz = Math.sin(angle) * radius * 0.4 + Math.cos(elapsed * 0.0006 + phase_i) * 20;
                pos[si]   = lerp(pos[si],   tx, 0.025);
                pos[si+1] = lerp(pos[si+1], ty, 0.025);
                pos[si+2] = lerp(pos[si+2], tz, 0.025);
                if (i < this.TRAIL_COUNT) {
                    trailPos[si]   = pos[si]   - (tx - pos[si]) * 2;
                    trailPos[si+1] = pos[si+1] - (ty - pos[si+1]) * 2;
                    trailPos[si+2] = pos[si+2] - (tz - pos[si+2]) * 2;
                }
                const hue = (i / this.PARTICLE_COUNT + elapsed * 0.00008) % 1;
                col[si]   = lerp(0.37, 0.65, Math.abs(Math.sin(hue * Math.PI)));
                col[si+1] = lerp(0.55, 0.82, Math.abs(Math.cos(hue * Math.PI)));
                col[si+2] = 0.97;
                sz[i] = this.IS_MOBILE ? 0.55 : 0.70;
            }
            this.camera.position.x = Math.sin(elapsed * 0.00025) * 8;
            this.camera.position.y = Math.cos(elapsed * 0.0002)  * 4;
            this.camera.lookAt(0, 0, 0);

        // ── Phase 5 · 10-12.5 s · Logo convergence ───────────────────────────
        } else if (elapsed < 12500) {
            if (!this._phaseInited[5]) {
                this._phaseInited[5] = true;
                this._logoTargetsArr = genLogoTargets(this.PARTICLE_COUNT);
            }
            const p5    = (elapsed - 10000) / 2500;
            const ease5 = this._easeInOut(p5);
            pMat.opacity = lerp(0.85, 1.0, p5);
            tMat.opacity = lerp(0.3,  0.1, p5);

            const lt    = this._logoTargetsArr;
            const speed = 0.07 + 0.05 * ease5;
            for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                const si = i * 3;
                pos[si]   = lerp(pos[si],   lt[si],   speed);
                pos[si+1] = lerp(pos[si+1], lt[si+1], speed);
                pos[si+2] = lerp(pos[si+2], lt[si+2], speed);
                col[si]   = lerp(col[si],   0.6, 0.04);
                col[si+1] = lerp(col[si+1], 0.8, 0.04);
                col[si+2] = lerp(col[si+2], 1.0, 0.04);
                sz[i]     = lerp(sz[i], this.IS_MOBILE ? 0.45 : 0.60, 0.03);
            }
            this.pointLight.intensity = 3 + Math.sin(elapsed * 0.005) * 1.5;
            this.camera.position.z    = lerp(this.camera.position.z, 75, 0.015);
            this.camera.position.x    = lerp(this.camera.position.x, 0,  0.05);
            this.camera.position.y    = lerp(this.camera.position.y, 0,  0.05);
            this.camera.lookAt(0, 0, 0);

        // ── Phase 6 · 12.5-13.5 s · Show only loading text ───────────────────
        } else if (elapsed < 13500) {
            if (!this._phaseInited[6]) {
                this._phaseInited[6] = true;
                // Show ONLY the loading text — hide HTML logo letters and subtitle
                const loadEl = document.getElementById('intro-loading-text');
                if (loadEl) loadEl.classList.add('visible');
                // Keep HTML logo and subtitle hidden (particles already show BOOKLYFI)
            }
            const p6 = (elapsed - 12500) / 1000;
            pMat.opacity = lerp(1.0, 0.65, p6);
            tMat.opacity = lerp(0.1, 0.0,  p6);

            const lt = this._logoTargetsArr;
            for (let i = 0; i < this.PARTICLE_COUNT; i++) {
                const si = i * 3;
                pos[si]   = lerp(pos[si],   lt[si],   0.025);
                pos[si+1] = lerp(pos[si+1], lt[si+1], 0.025);
                pos[si+2] = lerp(pos[si+2], lt[si+2], 0.025);
            }
            this.pointLight.intensity = 4 + Math.sin(elapsed * 0.01) * 2;

        // ── Phase 7 · 13.5-14.5 s · Glow crescendo ──────────────────────────
        } else if (elapsed < 14500) {
            if (!this._phaseInited[7]) {
                this._phaseInited[7] = true;
                const bloom = document.getElementById('intro-bloom-overlay');
                if (bloom) bloom.classList.add('glow');
            }
            const p7 = (elapsed - 13500) / 1000;
            pMat.opacity = lerp(0.65, 0.2, p7);
            this.pointLight.intensity = 6 + Math.sin(elapsed * 0.03) * 3;

        // ── Phase 8 · 14.5-15.5 s · Fade out ────────────────────────────────
        } else if (elapsed < 15500) {
            if (!this._phaseInited[8]) {
                this._phaseInited[8] = true;
                const fadeEl = document.getElementById('intro-fade-overlay');
                if (fadeEl) fadeEl.classList.add('fading');
            }
            const p8 = (elapsed - 14500) / 1000;
            pMat.opacity = Math.max(0, lerp(0.2, 0, p8));
            tMat.opacity = 0;

        // ── Done ──────────────────────────────────────────────────────────────
        } else {
            this._finish();
            return;
        }

        // Upload buffer changes to GPU
        this.particleMesh.geometry.attributes.position.needsUpdate = true;
        this.particleMesh.geometry.attributes.color.needsUpdate    = true;
        this.particleMesh.geometry.attributes.size.needsUpdate     = true;
        if (this._phaseInited[3] || this._phaseInited[4]) {
            this.trailMesh.geometry.attributes.position.needsUpdate = true;
        }
    }

    // =========================================================================
    //  SKIP / FINISH
    // =========================================================================
    skip() {
        this._finish();
    }

    _finish() {
        if (this.appStarted) return;
        this.appStarted = true;

        if (this.rafId) cancelAnimationFrame(this.rafId);

        // Fade overlay then navigate to main app
        const fadeEl = document.getElementById('intro-fade-overlay');
        if (fadeEl) fadeEl.classList.add('fading');

        setTimeout(() => {
            // Clean up Three.js resources
            if (this.renderer) {
                this.renderer.dispose();
                if (this.particleMesh) {
                    this.particleMesh.geometry.dispose();
                    this.particleMesh.material.dispose();
                }
                if (this.trailMesh) {
                    this.trailMesh.geometry.dispose();
                    this.trailMesh.material.dispose();
                }
            }
            // Navigate to main application
            window.location.href = '/';
        }, 1300);
    }

    // =========================================================================
    //  RESIZE
    // =========================================================================
    _onResize() {
        const W = window.innerWidth, H = window.innerHeight;
        this.camera.aspect = W / H;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(W, H);
        if (this.rain) this.rain.resize();
    }
}

// ── Auto-start on DOMContentLoaded ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    const intro = new IntroAnimation();
    // Expose skip globally so the skip button onclick can call it
    window.skipIntro = () => intro.skip();
    intro.init();
}, { once: true });


