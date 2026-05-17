#!/usr/bin/env python3
"""
PATCH 2: Kratki cooldown za RPM/TPM 429 — odvojen od RPD
Fajl: network/quota_tracker.py

PROBLEM:
  _handle_429() ima samo dvije grane: dnevna kvota (sati cooldown)
  ili Retry-After cooldown. Ako burst_exhausted ili rpd_exhausted okine
  ali Retry-After nije prisutan, ključ dobije cooldown do slijedećeg reseta
  (20h). Ovo je pogrešno za RPM 429 — trebao bi biti max 2 minute.

ISPRAVKA:
  Dodajemo eksplicitnu granicu: ako je cooldown_s > 300s (5 min) ali
  dnevna kvota NE bi trebala biti iscrpljena (rpm_safe_check), resetujemo
  na kratki cooldown (120s default + margina). Ovo štiti od lažnih
  "dnevnih kvota" koje su zapravo RPM throttle.

  Konkretno: u _handle_429(), ako rpd_exhausted=False I burst < 15
  (koje je sad novi prag iz PATCH1), cooldown se ograničava na max 120s.
"""

import sys
from pathlib import Path

TARGET = Path("network/quota_tracker.py")

# Stari _handle_429 blok (rpd_exhausted or burst_exhausted grana)
OLD = '''\
        if rpd_exhausted or burst_exhausted:
            # Dnevna kvota — hladi se do slijedećeg reseta
            next_reset = _next_reset_timestamp(self._reset_hour)
            cooldown_s = max(0.0, next_reset - time.time())
            reason = "RPD dnevna kvota iscrpljena"
            syslog.warning(
                "[quota] %s ...%s: RPD kvota iscrpljena — hlađenje %.1fh (do reseta)",
                self.provider, self.key[-4:], cooldown_s / 3600,
            )
            logger.warning(
                "[quota] %s ...%s: RPD kvota iscrpljena — hlađenje %.1fh",
                self.provider, self.key[-4:], cooldown_s / 3600,
            )'''

NEW = '''\
        if rpd_exhausted or burst_exhausted:
            # PATCH2: razlikujemo pravu RPD iscrpljenost od RPM bursta
            if rpd_exhausted:
                # Prava dnevna kvota — hladi se do slijedećeg reseta
                next_reset = _next_reset_timestamp(self._reset_hour)
                cooldown_s = max(0.0, next_reset - time.time())
                reason = "RPD dnevna kvota iscrpljena"
                syslog.warning(
                    "[quota] %s ...%s: RPD kvota iscrpljena — hlađenje %.1fh (do reseta)",
                    self.provider, self.key[-4:], cooldown_s / 3600,
                )
                logger.warning(
                    "[quota] %s ...%s: RPD kvota iscrpljena — hlađenje %.1fh",
                    self.provider, self.key[-4:], cooldown_s / 3600,
                )
            else:
                # burst_exhausted ali ne i rpd_exhausted → kratki cooldown (RPM/TPM burst)
                if retry_after and retry_after > 0:
                    cooldown_s = float(retry_after) * 1.05
                else:
                    cooldown_s = 120.0  # 2 minute default za RPM burst
                reason = f"RPM/TPM burst cooldown {cooldown_s:.0f}s"
                syslog.warning(
                    "[quota] %s ...%s: RPM burst (>= 15× 429 danas) — kratki cooldown %.0fs",
                    self.provider, self.key[-4:], cooldown_s,
                )
                logger.warning(
                    "[quota] %s ...%s: RPM burst — kratki cooldown %.0fs",
                    self.provider, self.key[-4:], cooldown_s,
                )'''

def apply(root: Path = Path(".")):
    path = root / TARGET
    if not path.exists():
        print(f"[PATCH2] ❌  Fajl nije nađen: {path}")
        sys.exit(1)

    src = path.read_text(encoding="utf-8")

    if "PATCH2" in src:
        print("[PATCH2] ✅  Već primijenjeno — preskačem.")
        return

    if OLD not in src:
        print("[PATCH2] ❌  Stari kod nije nađen. Provjeri ručno.")
        # Prikaži kontekst gdje bi trebalo biti
        for i, line in enumerate(src.splitlines(), 1):
            if "rpd_exhausted or burst_exhausted" in line:
                print(f"         Linija {i}: {line}")
        sys.exit(1)

    patched = src.replace(OLD, NEW, 1)
    path.write_text(patched, encoding="utf-8")
    print(f"[PATCH2] ✅  Primijenjeno: RPM/RPD cooldown razdvojen  ({path})")

if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    apply(root)
