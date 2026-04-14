// ============================================================================
// BOOKLYFI INTRO — Particle System Target Generators
// ============================================================================
// Generates target position arrays for the Three.js particle morph phases.
// Called by IntroAnimation in intro-animation.js.

/**
 * Generates PARTICLE_COUNT * 3 positions forming a 3-D book silhouette.
 * @param {number} count - Total particle count
 * @returns {number[]} Flat [x,y,z, x,y,z, …] array
 */
function genBookTargets(count) {
    const pts = [];
    const W = 30, H = 40, D = 10;
    for (let i = 0; i < count; i++) {
        let x, y, z;
        const r = Math.random();

        if (r < 0.18) {
            // --- Okvir prednje korice (jasna pravougaona silueta) ---
            const side = Math.min(Math.floor(r / 0.18 * 4), 3);
            if (side === 0) {          // gornji rub
                x = (Math.random() - 0.5) * W;
                y = H / 2 + (Math.random() - 0.5) * 0.7;
                z = D / 2;
            } else if (side === 1) {   // donji rub
                x = (Math.random() - 0.5) * W;
                y = -H / 2 + (Math.random() - 0.5) * 0.7;
                z = D / 2;
            } else if (side === 2) {   // desni rub (fore-edge)
                x = W / 2 + (Math.random() - 0.5) * 0.7;
                y = (Math.random() - 0.5) * H;
                z = D / 2;
            } else {                    // lijevi rub (uz hrpat)
                x = -W / 2 + (Math.random() - 0.5) * 0.7;
                y = (Math.random() - 0.5) * H;
                z = D / 2;
            }
        } else if (r < 0.50) {
            // --- Prednja korica: horizontalni redovi (simulacija teksta/naslova) ---
            const LINES = 14;
            const line  = Math.floor(Math.random() * LINES);
            // Prva 3 reda = gušći naslovni blok (vrh korice)
            const yBase = line < 3
                ? H / 2 - 4 - line * 3.8
                : -H / 2 + 6 + (line - 3) * (H - 14) / (LINES - 3);
            x = (Math.random() - 0.5) * W * 0.86;
            y = yBase + (Math.random() - 0.5) * 0.9;
            z = D / 2 + (Math.random() - 0.5) * 0.4;
        } else if (r < 0.72) {
            // --- Hrpat (lijeva ploha) — uska, vertikalna traka ---
            x = -W / 2 + (Math.random() - 0.5) * 1.4;
            y = (Math.random() - 0.5) * H;
            z = (Math.random() - 0.5) * D;
        } else if (r < 0.87) {
            // --- Rub stranica (desna ploha) — horizontalne linije stranica ---
            const PAGE_LINES = 24;
            const pl = Math.floor(Math.random() * PAGE_LINES);
            x = W / 2 + (Math.random() - 0.5) * 0.9;
            y = -H / 2 + (pl / (PAGE_LINES - 1)) * H + (Math.random() - 0.5) * 0.5;
            z = (Math.random() - 0.5) * D;
        } else if (r < 0.94) {
            // --- Zadnja korica ---
            x = (Math.random() - 0.5) * W;
            y = (Math.random() - 0.5) * H;
            z = -D / 2 + (Math.random() - 0.5) * 0.4;
        } else {
            // --- Gornji i donji rub (bridovi) ---
            const top = Math.random() < 0.5;
            x = (Math.random() - 0.5) * W;
            y = (top ? H / 2 : -H / 2) + (Math.random() - 0.5) * 0.7;
            z = (Math.random() - 0.5) * D;
        }
        pts.push(x, y, z);
    }
    return pts;
}

/**
 * Generates PARTICLE_COUNT * 3 positions forming the text "BOOKLYFI"
 * using a 7-row pixel-font bitmap for each letter.
 * All particles are placed on ON pixels for dense, clear letter formation.
 * @param {number} count - Total particle count
 * @returns {number[]} Flat [x,y,z, x,y,z, …] array
 */
function genLogoTargets(count) {
    const pts = [];
    const letW = 10, letH = 18, spacing = 14;
    const totalW = 8 * spacing;
    const startX = -totalW / 2 + spacing / 2;

    // 7-row bitmaps for clearer, denser letter formation
    const FONT = {
        B: [[1,1,1,1,0],[1,0,0,0,1],[1,0,0,0,1],[1,1,1,1,0],[1,0,0,0,1],[1,0,0,0,1],[1,1,1,1,0]],
        O: [[0,1,1,1,0],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[0,1,1,1,0]],
        K: [[1,0,0,0,1],[1,0,0,1,0],[1,0,1,0,0],[1,1,0,0,0],[1,0,1,0,0],[1,0,0,1,0],[1,0,0,0,1]],
        L: [[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0],[1,1,1,1,1]],
        Y: [[1,0,0,0,1],[1,0,0,0,1],[0,1,0,1,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0],[0,0,1,0,0]],
        F: [[1,1,1,1,1],[1,0,0,0,0],[1,0,0,0,0],[1,1,1,1,0],[1,0,0,0,0],[1,0,0,0,0],[1,0,0,0,0]],
        I: [[1,1,1],[0,1,0],[0,1,0],[0,1,0],[0,1,0],[0,1,0],[1,1,1]],
    };
    const letters = ['B','O','O','K','L','Y','F','I'];
    const ppLetter = Math.floor(count / letters.length);

    for (let li = 0; li < letters.length; li++) {
        const lx = startX + li * spacing;
        const bitmap = FONT[letters[li]];
        const rows = bitmap.length;
        const cols = bitmap[0].length;

        // Collect all ON pixel positions for this letter
        const onPixels = [];
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                if (bitmap[r][c]) onPixels.push([r, c]);
            }
        }
        if (onPixels.length === 0) continue;

        // Place all particles for this letter on ON pixels only → dense, clear letters
        for (let p = 0; p < ppLetter; p++) {
            const [ri, ci] = onPixels[Math.floor(Math.random() * onPixels.length)];
            pts.push(
                lx + (ci / (cols - 1) - 0.5) * letW + (Math.random() - 0.5) * 0.6,
                (0.5 - ri / (rows - 1)) * letH   + (Math.random() - 0.5) * 0.6,
                (Math.random() - 0.5) * 1.5
            );
        }
    }
    // Fill any remaining particles with subtle scatter around the logo area
    while (pts.length < count * 3) {
        pts.push(
            (Math.random() - 0.5) * totalW * 1.5,
            (Math.random() - 0.5) * letH * 1.5,
            (Math.random() - 0.5) * 20
        );
    }
    return pts.slice(0, count * 3);
}
