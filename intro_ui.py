# ============================================================================
# BOOKLYFI INTRO ANIMATION — 3D Page Flip (VERSION 3)
# ============================================================================

INTRO_HTML = """
    <style>
        /* Skip button */
        .skip-intro-btn {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999999;
            color: rgba(255,255,255,0.6);
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.15);
            padding: 8px 18px;
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.2s ease;
            backdrop-filter: blur(4px);
        }
        .skip-intro-btn:hover {
            color: #fff;
            background: rgba(255,255,255,0.15);
            border-color: rgba(255,255,255,0.3);
        }

        /* Overlay */
        #intro-overlay {
            position: fixed;
            top: 0; left: 0;
            width: 100vw; height: 100vh;
            background: #0f172a;
            z-index: 999999;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            transition: opacity 1.2s ease;
        }

        /* Animated gradient background */
        #intro-bg {
            position: absolute;
            inset: 0;
            background: radial-gradient(ellipse at 30% 40%, rgba(59,130,246,0.12) 0%, transparent 60%),
                        radial-gradient(ellipse at 70% 70%, rgba(139,92,246,0.10) 0%, transparent 60%);
            opacity: 0;
            transition: opacity 1s ease;
        }
        #intro-bg.visible { opacity: 1; }

        /* Particles canvas */
        #intro-particles {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 1;
        }

        /* Book stage */
        #intro-book-stage {
            position: relative;
            z-index: 10;
            perspective: 1200px;
            width: 280px;
            height: 340px;
            opacity: 0;
            transform: translateY(20px);
            transition: opacity 0.8s ease, transform 0.8s ease;
        }
        #intro-book-stage.visible {
            opacity: 1;
            transform: translateY(0);
        }

        /* Book base (back cover + spine) */
        #intro-book-base {
            position: absolute;
            left: 0; top: 0;
            width: 100%; height: 100%;
            transform-style: preserve-3d;
        }

        .book-cover {
            position: absolute;
            width: 100%; height: 100%;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid rgba(59,130,246,0.3);
            border-radius: 2px 8px 8px 2px;
            box-shadow:
                -6px 0 12px rgba(0,0,0,0.4),
                0 4px 20px rgba(0,0,0,0.3),
                inset 0 0 30px rgba(59,130,246,0.03);
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .book-cover-logo {
            width: 60px;
            height: 60px;
            opacity: 0.3;
        }

        /* Page flip wrapper */
        .page-flip-wrapper {
            position: absolute;
            left: 0; top: 0;
            width: 100%; height: 100%;
            transform-style: preserve-3d;
            transform-origin: left center;
            transition: transform 1.4s cubic-bezier(0.645, 0.045, 0.355, 1.000);
        }

        .page-flip-wrapper.flipped {
            transform: rotateY(-180deg);
        }

        .page-face {
            position: absolute;
            left: 0; top: 0;
            width: 100%; height: 100%;
            border-radius: 2px 8px 8px 2px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            backface-visibility: hidden;
            -webkit-backface-visibility: hidden;
            overflow: hidden;
        }

        .page-front {
            background: linear-gradient(160deg, #1e3a5f 0%, #1e293b 100%);
            border: 1px solid rgba(59,130,246,0.2);
            box-shadow: 2px 0 8px rgba(0,0,0,0.3);
        }

        .page-back {
            background: linear-gradient(160deg, #1a1040 0%, #1e293b 100%);
            border: 1px solid rgba(139,92,246,0.2);
            transform: rotateY(180deg);
            box-shadow: -2px 0 8px rgba(0,0,0,0.3);
        }

        /* Page line decorations */
        .page-lines {
            position: absolute;
            width: 72%;
            top: 20%;
        }

        .page-line {
            height: 1px;
            background: rgba(255,255,255,0.06);
            margin-bottom: 10px;
            border-radius: 1px;
        }

        /* Text that slides in on each page */
        .intro-brand-text {
            font-family: 'Inter', -apple-system, sans-serif;
            font-weight: 700;
            text-align: center;
            opacity: 0;
            transform: translateX(-20px);
            transition: opacity 0.6s ease 0.5s, transform 0.6s ease 0.5s;
            position: relative;
            z-index: 1;
        }

        .intro-brand-text.visible {
            opacity: 1;
            transform: translateX(0);
        }

        .intro-brand-title {
            font-size: 2rem;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            line-height: 1.1;
            margin-bottom: 4px;
        }

        .intro-brand-sub {
            font-size: 1rem;
            color: rgba(255,255,255,0.5);
            letter-spacing: 2px;
            text-transform: uppercase;
        }

        .intro-brand-tagline {
            font-size: 0.72rem;
            color: rgba(139,92,246,0.8);
            letter-spacing: 1px;
            margin-top: 8px;
            font-weight: 500;
        }

        /* Logo glow pulse at end */
        #intro-glow-pulse {
            position: absolute;
            width: 300px;
            height: 300px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(59,130,246,0.15) 0%, transparent 70%);
            transform: scale(0);
            transition: transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.8s ease;
            opacity: 0;
            z-index: 0;
        }

        #intro-glow-pulse.pulse {
            transform: scale(1);
            opacity: 1;
        }

        /* Spine shadow */
        .book-spine {
            position: absolute;
            left: -6px;
            top: 2px;
            width: 6px;
            height: calc(100% - 4px);
            background: linear-gradient(to right, #0a1628, #1e293b);
            border-radius: 2px 0 0 2px;
            box-shadow: -2px 0 6px rgba(0,0,0,0.5);
        }
    </style>

    <div id="intro-overlay">
        <div id="intro-bg"></div>
        <canvas id="intro-particles"></canvas>

        <div id="intro-glow-pulse"></div>

        <!-- Book Stage -->
        <div id="intro-book-stage">
            <!-- Spine -->
            <div class="book-spine"></div>

            <!-- Book back cover (always visible) -->
            <div class="book-cover" id="intro-book-base">
                <svg class="book-cover-logo" viewBox="0 0 32 32" fill="none" stroke="rgba(59,130,246,0.4)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="4" width="16" height="24" rx="2"/>
                    <line x1="4" y1="9" x2="20" y2="9"/>
                    <polygon points="22,4 16,18 21,18 15,28 28,13 23,13" stroke="rgba(139,92,246,0.4)"/>
                </svg>
            </div>

            <!-- Page flip 1: reveals BOOKLYFI -->
            <div class="page-flip-wrapper" id="intro-page-1">
                <div class="page-face page-front">
                    <div class="page-lines">
                        <div class="page-line"></div>
                        <div class="page-line" style="width:85%;"></div>
                        <div class="page-line" style="width:70%;"></div>
                        <div class="page-line" style="width:90%;"></div>
                        <div class="page-line" style="width:60%;"></div>
                    </div>
                </div>
                <div class="page-face page-back">
                    <div class="intro-brand-text" id="intro-text-1">
                        <div class="intro-brand-title">BOOKLYFI</div>
                    </div>
                </div>
            </div>

            <!-- Page flip 2: reveals TURBO CHARGED -->
            <div class="page-flip-wrapper" id="intro-page-2">
                <div class="page-face page-front">
                    <div class="page-lines">
                        <div class="page-line"></div>
                        <div class="page-line" style="width:80%;"></div>
                        <div class="page-line" style="width:95%;"></div>
                        <div class="page-line" style="width:75%;"></div>
                        <div class="page-line" style="width:55%;"></div>
                    </div>
                </div>
                <div class="page-face page-back">
                    <div class="intro-brand-text" id="intro-text-2">
                        <div class="intro-brand-sub">TURBO CHARGED ⚡</div>
                        <div class="intro-brand-tagline">AI-Powered Book Translation &amp; Refinement</div>
                    </div>
                </div>
            </div>
        </div>

        <button class="skip-intro-btn" onclick="forceStartApp()" aria-label="Preskoči animaciju">Preskoči →</button>
    </div>

    <script>
        let appStarted = false;
        let particleAnimReq = null;

        // Particle system
        function initParticles() {
            const canvas = document.getElementById('intro-particles');
            if (!canvas) return null;
            const ctx = canvas.getContext('2d');
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;

            const particles = [];
            const count = Math.min(40, Math.floor(window.innerWidth / 30));

            for (let i = 0; i < count; i++) {
                particles.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height,
                    r: Math.random() * 2.5 + 0.5,
                    dx: (Math.random() - 0.5) * 0.4,
                    dy: (Math.random() - 0.5) * 0.4,
                    alpha: Math.random() * 0.4 + 0.1,
                    color: Math.random() > 0.5 ? '59,130,246' : '139,92,246'
                });
            }

            function drawParticles() {
                if (appStarted) return;
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                particles.forEach(p => {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(' + p.color + ',' + p.alpha + ')';
                    ctx.fill();
                    p.x += p.dx;
                    p.y += p.dy;
                    if (p.x < 0 || p.x > canvas.width) p.dx *= -1;
                    if (p.y < 0 || p.y > canvas.height) p.dy *= -1;
                });
                particleAnimReq = requestAnimationFrame(drawParticles);
            }

            drawParticles();
        }

        function forceStartApp() {
            if (appStarted) return;
            appStarted = true;

            if (particleAnimReq) cancelAnimationFrame(particleAnimReq);

            const overlay = document.getElementById('intro-overlay');
            const ui = document.getElementById('main-ui-wrapper');

            if (ui) {
                ui.style.display = 'block';
                void ui.offsetWidth;
                ui.style.opacity = '1';
            }

            if (overlay) {
                overlay.style.opacity = '0';
                setTimeout(() => {
                    document.body.style.overflow = 'auto';
                    overlay.remove();
                }, 1200);
            }
        }

        // Check prefers-reduced-motion
        const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        const reducedMotion = motionQuery.matches;

        // Also respect real-time changes (e.g., user changes system accessibility settings)
        motionQuery.addEventListener('change', (e) => {
            if (e.matches && !appStarted) forceStartApp();
        });

        window.addEventListener('load', () => {
            if (reducedMotion) {
                // Respect reduced motion — skip animation entirely
                forceStartApp();
                return;
            }

            document.body.style.overflow = 'hidden';
            initParticles();

            // Animation sequence:
            // 0.5s  : bg gradient fades in
            // 1.0s  : book appears
            // 2.0s  : page 1 flips → BOOKLYFI
            // 4.0s  : page 2 flips → TURBO CHARGED
            // 6.0s  : glow pulse
            // 7.5s  : fade to UI

            setTimeout(() => {
                const bg = document.getElementById('intro-bg');
                if (bg) bg.classList.add('visible');
            }, 500);

            setTimeout(() => {
                const stage = document.getElementById('intro-book-stage');
                if (stage) stage.classList.add('visible');
            }, 1000);

            setTimeout(() => {
                const page = document.getElementById('intro-page-1');
                if (page) page.classList.add('flipped');
                setTimeout(() => {
                    const t = document.getElementById('intro-text-1');
                    if (t) t.classList.add('visible');
                }, 600);
            }, 2200);

            setTimeout(() => {
                const page = document.getElementById('intro-page-2');
                if (page) page.classList.add('flipped');
                setTimeout(() => {
                    const t = document.getElementById('intro-text-2');
                    if (t) t.classList.add('visible');
                }, 600);
            }, 4200);

            setTimeout(() => {
                const glow = document.getElementById('intro-glow-pulse');
                if (glow) {
                    glow.classList.add('pulse');
                    setTimeout(() => {
                        glow.style.opacity = '0';
                    }, 700);
                }
            }, 6200);

            setTimeout(() => {
                forceStartApp();
            }, 7800);
        });

        // Absolute fail-safe
        setTimeout(() => {
            if (!appStarted) forceStartApp();
        }, 11000);
    </script>
"""
