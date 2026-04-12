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
    const W = 28, H = 38, D = 8;
    for (let i = 0; i < count; i++) {
        let x, y, z;
        const r = Math.random();
        if (r < 0.35) {
            // front cover
            x = (Math.random() - 0.5) * W;
            y = (Math.random() - 0.5) * H;
            z = D / 2 + (Math.random() - 0.5) * 1.5;
        } else if (r < 0.55) {
            // spine
            x = -W / 2 + (Math.random() - 0.5) * 2;
            y = (Math.random() - 0.5) * H;
            z = (Math.random() - 0.5) * D;
        } else if (r < 0.70) {
            // back cover
            x = (Math.random() - 0.5) * W;
            y = (Math.random() - 0.5) * H;
            z = -D / 2 + (Math.random() - 0.5) * 1.5;
        } else if (r < 0.85) {
            // pages (right edge)
            x = W / 2 + (Math.random() - 0.5) * 1.5;
            y = (Math.random() - 0.5) * H;
            z = (Math.random() - 0.5) * D;
        } else {
            // top / bottom edges
            const top = Math.random() < 0.5;
            x = (Math.random() - 0.5) * W;
            y = top ? H / 2 : -H / 2;
            z = (Math.random() - 0.5) * D;
        }
        pts.push(x, y, z);
    }
    return pts;
}

/**
 * Generates PARTICLE_COUNT * 3 positions forming the text "BOOKLYFI"
 * using a 5-row pixel-font bitmap for each letter.
 * @param {number} count - Total particle count
 * @returns {number[]} Flat [x,y,z, x,y,z, …] array
 */
function genLogoTargets(count) {
    const pts = [];
    const letW = 8, letH = 14, spacing = 12;
    const totalW = 8 * spacing;
    const startX = -totalW / 2 + spacing / 2;

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
    const ppLetter = Math.floor(count / letters.length);

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
                    lx + (ci / (cols - 1) - 0.5) * letW + (Math.random() - 0.5) * 0.8,
                    (0.5 - ri / (rows - 1)) * letH   + (Math.random() - 0.5) * 0.8,
                    (Math.random() - 0.5) * 2
                );
            } else {
                const sc = 250;
                pts.push(
                    (Math.random() - 0.5) * sc,
                    (Math.random() - 0.5) * sc,
                    (Math.random() - 0.5) * sc * 0.5
                );
            }
        }
    }
    while (pts.length < count * 3) {
        pts.push(
            (Math.random() - 0.5) * 200,
            (Math.random() - 0.5) * 200,
            (Math.random() - 0.5) * 100
        );
    }
    return pts.slice(0, count * 3);
}
