// ============================================================================
// BOOKLYFI INTRO — Digital Rain Post-Processing Effect
// ============================================================================
// Renders a Matrix-style digital rain on a 2-D canvas layered over the
// Three.js viewport.  Used by IntroAnimation during Phase 1 (0-2 s).

class DigitalRain {
    constructor(canvasEl) {
        this.canvas = canvasEl;
        this.ctx    = canvasEl.getContext('2d');
        this.cols   = [];
        this.active = true;

        // Character set: technical symbols + digits for the cyber aesthetic
        this.CHARS = '@#$%*01234⚡∞≡→∆Ω∑∏√π';
        this._resize();
    }

    _resize() {
        this.canvas.width  = window.innerWidth;
        this.canvas.height = window.innerHeight;
        const colW = 18;
        const count = Math.floor(this.canvas.width / colW);
        this.cols = Array.from({ length: count }, (_, i) => ({
            x:     i * colW + 9,
            y:     Math.random() * -400,
            speed: 1.5 + Math.random() * 2.5,
            chars: Array.from({ length: 20 }, () =>
                this.CHARS[Math.floor(Math.random() * this.CHARS.length)]
            ),
        }));
    }

    resize() {
        this._resize();
    }

    /**
     * Draw one rain frame.
     * @param {number} elapsed - Milliseconds since animation start
     */
    render(elapsed) {
        if (!this.active) return;

        this.ctx.fillStyle = 'rgba(2,6,23,0.18)';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Fade out between ~800 ms and ~2200 ms
        const alpha = Math.max(0, 1 - (elapsed - 800) / 1400);
        if (alpha <= 0) {
            if (this.active) {
                this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
                this.active = false;
            }
            return;
        }

        this.ctx.font = '14px "JetBrains Mono", monospace';
        for (const col of this.cols) {
            col.y += col.speed;
            if (col.y > this.canvas.height) col.y = -240;
            for (let j = 0; j < col.chars.length; j++) {
                const cy = col.y - j * 16;
                if (cy < -20 || cy > this.canvas.height + 20) continue;
                const fade = j === 0 ? 1 : (1 - j / col.chars.length) * 0.7;
                this.ctx.fillStyle = j === 0
                    ? `rgba(224,242,254,${fade * alpha})`
                    : `rgba(96,165,250,${fade * alpha * 0.8})`;
                if (Math.random() < 0.01)
                    col.chars[j] = this.CHARS[Math.floor(Math.random() * this.CHARS.length)];
                this.ctx.fillText(col.chars[j], col.x, cy);
            }
        }
    }
}
