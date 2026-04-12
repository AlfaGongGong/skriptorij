# ============================================================================
# KINEMATSKI UVOD (MATRIX TO NEON QUILL) - Zasebna Komponenta
# ============================================================================

INTRO_HTML = """
    <style>
        /* [X] PRESKOČI - Gornji lijevi ćošak */
        .skip-intro-btn {
            position: absolute; top: 25px; left: 25px; z-index: 9999999;
            color: #ff2a00; background: rgba(20,0,0,0.6); border: 2px solid #ff2a00;
            padding: 10px 20px; font-family: monospace; font-weight: 900; cursor: pointer; 
            text-transform: uppercase; letter-spacing: 2px; border-radius: 6px; 
            transition: all 0.3s ease; font-size: 14px;
            box-shadow: 0 0 10px rgba(255,42,0,0.4);
            backdrop-filter: blur(2px);
        }
        .skip-intro-btn:hover { 
            background: #ff2a00; color: #000; 
            box-shadow: 0 0 25px #ff2a00, inset 0 0 10px #fff; 
            transform: scale(1.05);
        }
        
        /* Glavni kontejner */
        #intro-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: #000000; z-index: 999999; display: flex; flex-direction: column;
            align-items: center; justify-content: center; overflow: hidden;
            transition: opacity 1.5s ease-in-out, visibility 1.5s;
        }
        #matrix-canvas {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            z-index: 999999; filter: blur(0.5px);
        }
        
        #intro-content {
            position: relative; z-index: 9999999; display: flex; flex-direction: column;
            align-items: center; justify-content: center; opacity: 0; transition: opacity 2s ease;
        }
        
        /* Finalni SVG Vektorski logo */
        #intro-quill-final {
            width: 220px; height: 220px;
            filter: drop-shadow(0 0 20px rgba(0,243,255,0.7));
            stroke: url(#neonGradIntro); stroke-width: 0.7;
            opacity: 0; transition: opacity 1.5s ease;
        }
        .show-quill { opacity: 1 !important; }
        
        #tw-text {
            margin-top: 2.5rem; font-family: 'Courier New', monospace; font-weight: 900; font-size: 1.4rem;
            color: #00f3ff; text-shadow: 0 0 15px rgba(0,243,255,0.9); text-align: center;
            min-height: 2em; letter-spacing: 4px;
        }
    </style>

    <div id="intro-overlay">
       <canvas id="matrix-canvas"></canvas>
       
       <div id="intro-content">
           <svg id="intro-quill-final" viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">
               <defs>
                   <linearGradient id="neonGradIntro" x1="0%" y1="0%" x2="100%" y2="100%">
                       <stop offset="0%" stop-color="#00f3ff"/>
                       <stop offset="25%" stop-color="#ff2a00"/>
                       <stop offset="50%" stop-color="#e000ff"/>
                       <stop offset="75%" stop-color="#f59e0b"/>
                       <stop offset="100%" stop-color="#10b981"/>
                   </linearGradient>
               </defs>
               <path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"></path>
               <line x1="16" y1="8" x2="2" y2="22"></line>
               <line x1="17.5" y1="15" x2="9" y2="15"></line>
           </svg>
           <div id="tw-text"></div>
       </div>
       
       <button class="skip-intro-btn" onclick="forceStartApp()">[X] PRESKOČI</button>
    </div>

    <script>
        let canvas, ctx, columns, drops, quillPath2D;
        let frame = 0;
        let animReq;
        let appStarted = false;
        
        let isScreenFull = false;
        let fullFrameStart = 0;
        let matrixLogoOpacity = 1.0;
        
        const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$+-*/=%&<>!@#".split("");
        const fontSize = 16;
        const neonColors = ["#00f3ff", "#ff2a00", "#e000ff", "#f59e0b", "#10b981", "#00FF41"];
        const frozenChars = [];

        function isInsideQuill(x, y) {
            if(!quillPath2D) return false;
            ctx.save();
            ctx.translate(canvas.width / 2, canvas.height / 2.3);
            ctx.scale(10, 10);
            ctx.translate(-12, -12);
            ctx.lineWidth = 1.5;
            let inside = ctx.isPointInPath(quillPath2D, x, y) || ctx.isPointInStroke(quillPath2D, x, y);
            ctx.restore();
            return inside;
        }

        function initMatrix() {
            if(appStarted) return;
            canvas = document.getElementById('matrix-canvas');
            if(!canvas) return;
            ctx = canvas.getContext('2d');
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            
            columns = Math.floor(canvas.width / fontSize);
            let delayFactor = canvas.width > 768 ? 1.5 : 2.5; 
            drops = Array(columns).fill(0).map((_, i) => -Math.floor(i * delayFactor));
            
            quillPath2D = new Path2D("M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z M16 8L2 22 M17.5 15L9 15");
            
            document.body.style.overflow = "hidden";
            requestAnimationFrame(drawMatrix);
        }

        function drawMatrix() {
            if (appStarted) return;
            
            ctx.fillStyle = "rgba(0, 0, 0, 0.05)"; 
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.font = fontSize + "px monospace";
            
            if (!isScreenFull && drops[columns - 1] * fontSize > canvas.height) {
                isScreenFull = true;
                fullFrameStart = frame;
                // Odmah redistribuiraj sve kapljice nasumično po visini ekrana
                // za ravnomjeran kontinuiran tok u fazi normalnog pada
                for (let k = 0; k < columns; k++) {
                    drops[k] = -Math.floor(Math.random() * canvas.height / fontSize);
                }
            }
            
            let glitchStart = isScreenFull ? fullFrameStart + 180 : 999999; 
            let quillStart = glitchStart + 60;
            let exitStart = quillStart + 180; 
            let evolutionStart = exitStart + Math.floor(columns * 1.5) + 60; 
            
            if (frame > evolutionStart) {
                matrixLogoOpacity -= 0.015;
                if (matrixLogoOpacity < 0) matrixLogoOpacity = 0;
            }
            
            if (matrixLogoOpacity > 0 && frozenChars.length > 0) {
                ctx.save();
                ctx.globalAlpha = matrixLogoOpacity;
                ctx.shadowBlur = 8;
                
                frozenChars.forEach(fc => {
                    ctx.fillStyle = fc.color;
                    ctx.shadowColor = fc.color;
                    if(Math.random() > 0.98) {
                        ctx.fillText(chars[Math.floor(Math.random() * chars.length)], fc.x, fc.y);
                    } else {
                        ctx.fillText(fc.char, fc.x, fc.y);
                    }
                });
                ctx.restore();
            }
            
            drops.forEach((y, i) => {
                if (y < 0 && !isScreenFull) {
                    drops[i] += 0.5; 
                    return; 
                } 
                if (y === -999) return; 
                
                const x = i * fontSize;
                const yPos = y * fontSize;
                const text = chars[Math.floor(Math.random() * chars.length)];
                
                let color = "#00FF41"; 
                
                if (frame > glitchStart && frame < exitStart && Math.random() > 0.8) {
                    color = neonColors[Math.floor(Math.random() * neonColors.length)];
                }
                
                if (frame > quillStart && frame < exitStart) {
                    if (isInsideQuill(x, yPos)) {
                        color = neonColors[Math.floor(frame / 10) % neonColors.length];
                        ctx.fillStyle = color;
                        ctx.shadowBlur = 10;
                        ctx.shadowColor = color;
                        if (Math.random() > 0.7) {
                            frozenChars.push({ x: x, y: yPos, char: text, color: color });
                        }
                    } else {
                        ctx.shadowBlur = 0;
                        ctx.fillStyle = "#003311"; 
                    }
                } else {
                    ctx.fillStyle = color;
                    ctx.shadowBlur = 0;
                }

                ctx.fillText(text, x, yPos);
                
                if (yPos > canvas.height) {
                    if (frame > exitStart) {
                        // Izlazni val lijevo → desno: kolona 0 izlazi prva
                        let waveDelay = canvas.width > 768 ? 1.0 : 1.5;
                        let myExitFrame = exitStart + i * waveDelay;
                        
                        if (frame > myExitFrame && !isInsideQuill(x, 0)) {
                            drops[i] = -999; 
                        } else {
                            drops[i] = Math.random() * -20; 
                        }
                    } else if (!isScreenFull) {
                        // Faza 1 — jedinstven ulazni val: parkiraj kolonu daleko iznad
                        // ekrana da se ne pojavi ponovo dok traje dijagonalni prolaz
                        drops[i] = -500;
                    } else {
                        // Faza 2/3 — normalni pad: kratko čekanje za kontinuiran tok
                        drops[i] = Math.random() * -10; 
                    }
                } else {
                    drops[i] += (frame > exitStart) ? 1.5 : 0.8;
                }
            });
            
            frame++;
            
            if (frame === Math.floor(evolutionStart)) {
                document.getElementById('intro-content').style.opacity = "1";
                document.getElementById('intro-quill-final').classList.add('show-quill');
            }
            
            if (frame === Math.floor(evolutionStart + 60)) {
                startTypewriter();
            }
            
            if (frame < 3000) {
                animReq = requestAnimationFrame(drawMatrix);
            }
        }
        
        let textToType = "SKRIPTORIJ AI EPUB REFINERY";
        let typeIndex = 0;
        function startTypewriter() {
            if(appStarted) return;
            const tw = document.getElementById('tw-text');
            if(typeIndex < textToType.length) {
                tw.innerHTML += textToType.charAt(typeIndex);
                typeIndex++;
                setTimeout(startTypewriter, 100); 
            } else {
                setTimeout(forceStartApp, 3000); 
            }
        }

        function forceStartApp() {
            if(appStarted) return;
            appStarted = true;
            if (animReq) cancelAnimationFrame(animReq);
            
            const overlay = document.getElementById('intro-overlay');
            const ui = document.getElementById('main-ui-wrapper');
            
            if (ui) {
                ui.style.display = "block";
                void ui.offsetWidth; // Forsira preglednik da primijeni promjenu prije animacije
                ui.style.opacity = "1";
            }
            
            if (overlay) {
                overlay.style.opacity = "0";
                setTimeout(() => {
                    document.body.style.overflow = "auto";
                    overlay.remove();
                }, 1000);
            }
        }

        window.addEventListener('load', initMatrix);
        
        // APSOLUTNI FAIL-SAFE (Garantovano otvara UI nakon 12 sekundi)
        setTimeout(() => {
            if (!appStarted) forceStartApp();
        }, 12000);

    </script>
"""
