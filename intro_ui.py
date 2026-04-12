# ============================================================================
# BOOKLYFI INTRO ANIMATION — 3D Page Flip (VERSION 3 TURBO)
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

        /* ── Keyframe animations ────────────────────────────────── */
        @keyframes bgGradientShift {
            0%   { background-position: 0% 0%; }
            33%  { background-position: 100% 50%; }
            66%  { background-position: 50% 100%; }
            100% { background-position: 0% 0%; }
        }

        @keyframes logoEntrance {
            0%   { transform: scale(0.3) rotate(10deg); opacity: 0; }
            60%  { transform: scale(1.08) rotate(-2deg); opacity: 1; }
            100% { transform: scale(1) rotate(0deg); opacity: 1; }
        }

        @keyframes textSlideIn {
            0%   { transform: translateX(-60px); opacity: 0; }
            100% { transform: translateX(0);     opacity: 1; }
        }

        @keyframes glowPulse {
            0%, 100% { filter: drop-shadow(0 0 10px rgba(96,165,250,0.4)); }
            50%       { filter: drop-shadow(0 0 30px rgba(96,165,250,0.9)) drop-shadow(0 0 60px rgba(167,139,250,0.5)); }
        }

        @keyframes introFadeIn {
            from { opacity: 0; }
            to   { opacity: 1; }
        }

        @keyframes bookFloat {
            0%, 100% { transform: translateY(0px); }
            50%       { transform: translateY(-8px); }
        }

        @keyframes particleBurst {
            0%   { transform: translate(0, 0) scale(1); opacity: 1; }
            100% { transform: translate(var(--tx), var(--ty)) scale(0); opacity: 0; }
        }

        /* Overlay */
        #intro-overlay {
            position: fixed;
            top: 0; left: 0;
            width: 100vw; height: 100vh;
            background: #0a0e27;
            z-index: 999999;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            transition: opacity 1.2s ease;
            animation: introFadeIn 0.5s ease forwards;
        }

        /* Animated gradient background */
        #intro-bg {
            position: absolute;
            inset: 0;
            background: radial-gradient(ellipse at 20% 30%, rgba(96,165,250,0.18) 0%, transparent 55%),
                        radial-gradient(ellipse at 80% 70%, rgba(167,139,250,0.15) 0%, transparent 55%),
                        radial-gradient(ellipse at 50% 90%, rgba(74,222,128,0.06) 0%, transparent 40%);
            background-size: 200% 200%;
            opacity: 0;
            transition: opacity 1s ease;
            animation: bgGradientShift 8s ease-in-out infinite;
        }
        #intro-bg.visible { opacity: 1; }

        /* Particles canvas */
        #intro-particles {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 1;
        }

        /* Burst particles container */
        #intro-burst-particles {
            position: absolute;
            inset: 0;
            pointer-events: none;
            z-index: 2;
            overflow: hidden;
        }

        .burst-particle {
            position: absolute;
            border-radius: 50%;
            animation: particleBurst 1.2s ease-out forwards;
        }

        /* Book stage */
        #intro-book-stage {
            position: relative;
            z-index: 10;
            perspective: 1200px;
            width: 280px;
            height: 340px;
            opacity: 0;
            transform: scale(0.3) rotate(10deg) translateY(20px);
            transition: none;
        }
        #intro-book-stage.visible {
            opacity: 1;
            transform: scale(1) rotate(0deg) translateY(0);
            animation: logoEntrance 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) forwards,
                       bookFloat 3s ease-in-out 1.5s infinite;
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
            background: linear-gradient(135deg, #1e293b 0%, #0a0e27 100%);
            border: 1px solid rgba(96,165,250,0.4);
            border-radius: 2px 8px 8px 2px;
            box-shadow:
                -6px 0 12px rgba(0,0,0,0.4),
                0 4px 20px rgba(0,0,0,0.3),
                inset 0 0 30px rgba(96,165,250,0.04);
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .book-cover-logo {
            width: 60px;
            height: 60px;
            opacity: 0.35;
            animation: glowPulse 3s ease-in-out infinite;
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
            border: 1px solid rgba(96,165,250,0.25);
            box-shadow: 2px 0 8px rgba(0,0,0,0.3);
        }

        .page-back {
            background: linear-gradient(160deg, #1a1040 0%, #1e293b 100%);
            border: 1px solid rgba(167,139,250,0.25);
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
            background: rgba(255,255,255,0.05);
            margin-bottom: 10px;
            border-radius: 1px;
        }

        /* Text that slides in on each page */
        .intro-brand-text {
            font-family: 'Inter', -apple-system, sans-serif;
            font-weight: 700;
            text-align: center;
            opacity: 0;
            transform: translateX(-40px);
            transition: none;
            position: relative;
            z-index: 1;
        }

        .intro-brand-text.visible {
            opacity: 1;
            transform: translateX(0);
            animation: textSlideIn 0.7s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
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
            color: rgba(255,255,255,0.7);
            letter-spacing: 2px;
            text-transform: uppercase;
        }

        .intro-brand-tagline {
            font-size: 0.72rem;
            color: rgba(167,139,250,0.85);
            letter-spacing: 1px;
            margin-top: 8px;
            font-weight: 500;
        }

        /* Logo glow pulse at end */
        #intro-glow-pulse {
            position: absolute;
            width: 500px;
            height: 500px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(96,165,250,0.12) 0%, rgba(167,139,250,0.06) 40%, transparent 70%);
            transform: scale(0);
            transition: transform 1s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 1s ease;
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
            background: linear-gradient(to right, #050a1a, #141929);
            border-radius: 2px 0 0 2px;
            box-shadow: -2px 0 6px rgba(0,0,0,0.5);
        }

        /* Horizontal scan lines for depth */
        .page-scan-line {
            position: absolute;
            left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(96,165,250,0.15), transparent);
            animation: scanMove 4s linear infinite;
        }

        @keyframes scanMove {
            0%   { top: 0%; }
            100% { top: 100%; }
        }
    </style>

    <div id="intro-overlay">
        <div id="intro-bg"></div>
        <canvas id="intro-particles"></canvas>
        <div id="intro-burst-particles"></div>

        <div id="intro-glow-pulse"></div>

        <!-- Book Stage -->
        <div id="intro-book-stage">
            <!-- Spine -->
            <div class="book-spine"></div>

            <!-- Book back cover (always visible) -->
            <div class="book-cover" id="intro-book-base">
                <svg class="book-cover-logo" viewBox="0 0 32 32" fill="none" stroke="rgba(96,165,250,0.5)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="4" width="16" height="24" rx="2"/>
                    <line x1="4" y1="9" x2="20" y2="9"/>
                    <polygon points="22,4 16,18 21,18 15,28 28,13 23,13" stroke="rgba(167,139,250,0.5)"/>
                </svg>
            </div>

            <!-- Page flip 1: reveals BOOKLYFI -->
            <div class="page-flip-wrapper" id="intro-page-1">
                <div class="page-face page-front">
                    <div class="page-scan-line"></div>
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
                    <div class="page-scan-line" style="animation-delay:2s"></div>
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

        // ── Background particle system (ambient floaters) ──
        function initParticles() {
            const canvas = document.getElementById('intro-particles');
            if (!canvas) return null;
            const ctx = canvas.getContext('2d');
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;

            const count = Math.min(80, Math.floor(window.innerWidth / 15));
            const particles = [];

            const colors = ['96,165,250', '167,139,250', '74,222,128', '251,191,36', '248,113,113'];

            for (let i = 0; i < count; i++) {
                const color = colors[Math.floor(Math.random() * colors.length)];
                particles.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height,
                    r: Math.random() * 2.8 + 0.4,
                    dx: (Math.random() - 0.5) * 0.5,
                    dy: -(Math.random() * 0.4 + 0.1), // mostly drift upward
                    alpha: Math.random() * 0.35 + 0.05,
                    color: color,
                    twinkleSpeed: Math.random() * 0.02 + 0.005,
                    twinklePhase: Math.random() * Math.PI * 2
                });
            }

            let frame = 0;
            function drawParticles() {
                if (appStarted) return;
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                frame++;
                particles.forEach(p => {
                    // Twinkle effect
                    const twinkle = Math.sin(frame * p.twinkleSpeed + p.twinklePhase) * 0.15;
                    const alpha = Math.max(0.02, p.alpha + twinkle);

                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                    ctx.fillStyle = 'rgba(' + p.color + ',' + alpha + ')';
                    ctx.fill();

                    p.x += p.dx;
                    p.y += p.dy;

                    // Wrap around
                    if (p.x < -5) p.x = canvas.width + 5;
                    if (p.x > canvas.width + 5) p.x = -5;
                    if (p.y < -5) p.y = canvas.height + 5;
                    if (p.y > canvas.height + 5) p.y = canvas.height + 5;
                });
                particleAnimReq = requestAnimationFrame(drawParticles);
            }

            drawParticles();
        }

        // ── Burst particle effect on page flip ──
        function spawnBurstParticles(intensity) {
            const container = document.getElementById('intro-burst-particles');
            if (!container) return;

            const cx = window.innerWidth / 2;
            const cy = window.innerHeight / 2;
            const count = intensity === 2 ? 30 : 18;
            const colors = ['#60a5fa', '#a78bfa', '#4ade80', '#fbbf24', '#f87171', '#ffffff'];

            for (let i = 0; i < count; i++) {
                const el = document.createElement('div');
                el.className = 'burst-particle';

                const size = Math.random() * 6 + 2;
                const angle = (Math.random() * 360) * Math.PI / 180;
                const dist = (Math.random() * 200 + 80) * (intensity === 2 ? 1.5 : 1);
                const tx = Math.cos(angle) * dist;
                const ty = Math.sin(angle) * dist;
                const color = colors[Math.floor(Math.random() * colors.length)];
                const delay = Math.random() * 0.3;
                const dur = Math.random() * 0.6 + 0.8;

                el.style.cssText = [
                    'width:' + size + 'px',
                    'height:' + size + 'px',
                    'background:' + color,
                    'left:' + (cx - size/2) + 'px',
                    'top:' + (cy - size/2) + 'px',
                    '--tx:' + tx + 'px',
                    '--ty:' + ty + 'px',
                    'animation-duration:' + dur + 's',
                    'animation-delay:' + delay + 's',
                    'box-shadow: 0 0 ' + (size * 2) + 'px ' + color
                ].join(';');

                container.appendChild(el);
                setTimeout(() => el.remove(), (dur + delay + 0.2) * 1000);
            }
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

        // Respect real-time changes
        motionQuery.addEventListener('change', (e) => {
            if (e.matches && !appStarted) forceStartApp();
        });

        window.addEventListener('load', () => {
            if (reducedMotion) {
                forceStartApp();
                return;
            }

            document.body.style.overflow = 'hidden';
            initParticles();

            // ── Animation timeline (8 seconds total) ──
            // T=0.5s : bg gradient fades in
            // T=1.0s : book appears with entrance animation
            // T=2.2s : page 1 flips → BOOKLYFI + burst particles
            // T=4.2s : page 2 flips → TURBO CHARGED + more burst particles
            // T=6.2s : glow pulse blooms
            // T=7.8s : fade to UI

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
                spawnBurstParticles(1);
                setTimeout(() => {
                    const t = document.getElementById('intro-text-1');
                    if (t) t.classList.add('visible');
                }, 600);
            }, 2200);

            setTimeout(() => {
                const page = document.getElementById('intro-page-2');
                if (page) page.classList.add('flipped');
                spawnBurstParticles(2);
                setTimeout(() => {
                    const t = document.getElementById('intro-text-2');
                    if (t) t.classList.add('visible');
                }, 600);
            }, 4200);

            setTimeout(() => {
                const glow = document.getElementById('intro-glow-pulse');
                if (glow) {
                    glow.classList.add('pulse');
                    spawnBurstParticles(1);
                    setTimeout(() => {
                        glow.style.transition = 'opacity 0.8s ease';
                        glow.style.opacity = '0';
                    }, 800);
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

