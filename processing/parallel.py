import logging
logger = logging.getLogger(__name__)
# processing/parallel.py
import asyncio
import random

# Veličina sliding window-a — max N paralelnih chunkova (svaki = 4 AI poziva).
# 3 chunka × 4 faze = 12 paralelnih poziva — sigurno za free tier.
# Za 8 ključeva to znači 4 paralelna poziva (konzervativno, bez DDoS-a)
_SLIDING_WINDOW_SIZE = 3  # PROBLEM #1 fix: bio 1 (ubijao dinamički algoritam); sada = gornja granica iz _get_window_size (max 6)


# P2.9: ponovni pokusaji kad blok padne (429 oluja); .prevod.chk cache cini ponovni pokusaj jeftinim
_MAX_PONOVNIH = 2
_RETRY_PAUZA = 20


class AdaptiveParallelism:
    """
    Upravlja paralelnom obradom chunkova uz poštovanje rate limita.

    IZMJENA: Umjesto scheduliranja SVIH chunka odjednom (što na 80 chunka i
    8 ključeva kreira 80 taskova koji se svi bore za isti semaphore),
    sada koristimo sliding window od _SLIDING_WINDOW_SIZE aktivnih chunka.
    To znači da je u svakom trenutku aktivno max N konkurentnih AI poziva,
    naredni čeka dok se jedan ne završi — prirodno backpressure.
    """

    def __init__(self, engine):
        self.engine = engine
        self.provider_semaphores = {}
        self._last_batch_time = 0
        self._human_delay = (2.0, 5.0)  # pauza između batcha (sekunde)

    def _get_window_size(self) -> int:
        """
        Dinamički izračunava veličinu sliding window-a na osnovu
        broja ključeva u floti.
        """
        fleet = self.engine.fleet
        total_active = fleet.get_total_active_keys()

        if total_active == 0:
            return 1

        # G40: s jednim aktivnim kljucem samo 1 slot (prije je max(2, ...) davao 2)
        if total_active == 1:
            return 1

        # Konzervativno: 1 slot per 2 ključa, min 2, max 6
        dynamic = max(2, min(total_active // 2, 6))

        return min(dynamic, _SLIDING_WINDOW_SIZE)

    async def process_chunks_parallel(self, chunks, file_name, p_ctx_func, n_ctx_func):
        """
        Obrađuje listu chunkova uz sliding window paralelizam.

        Umjesto da schedulira sve taskove odjednom i pusti semaphore da ih
        reguliše, ovaj pristup eksplicitno kontroliše koji su chunkovi
        u letu u svakom trenutku — efikasnije za scheduler i nema
        thundering herd problema.
        """
        results = [(None, "PENDING")] * len(chunks)
        window_size = self._get_window_size()

        self.engine.log(
            f"🔀 Parallel: {len(chunks)} chunka, window={window_size} "
            f"(aktivnih ključeva: {self.engine.fleet.get_total_active_keys()})",
            "tech",
        )

        # Semaphore koji osigurava max window_size istovremenih poziva
        semaphore = asyncio.Semaphore(window_size)

        async def process_one(idx, chunk):
            async with semaphore:
                try:
                    # L30: dnevna kvota iscrpljena -> bez API poziva za preostale blokove
                    if getattr(self.engine, "kvota_stop", False):
                        return idx, None, "QUOTA_STOP"
                    # ── Stagger — samo za blokove koji idu na API ─────────────
                    # Cache hit (.chk postoji + score ≥ threshold) ne ide na
                    # mrežu pa nema smisla čekati API throttle interval.
                    _is_cache_hit = False
                    try:
                        from core.quality import _QUALITY_RESCUE_THRESHOLD

                        _chk = (
                            self.engine.checkpoint_dir / f"{file_name}_blok_{idx}.chk"
                        )
                        if _chk.exists():
                            _qs = self.engine.shared_stats.get("quality_scores", {})
                            _raw = _qs.get(f"{file_name}_blok_{idx}")
                            _sc = float(_raw) if _raw is not None else None
                            # cache hit ako: score nepoznat (bit će scorovan)
                            # ILI score iznad threshold-a
                            _is_cache_hit = (
                                _sc is None or _sc >= _QUALITY_RESCUE_THRESHOLD
                            )
                    except Exception:
                        logger.exception("[C1_kriticno] parallel.py:88 Exception")

                    if not _is_cache_hit:
                        # Stagger proporcionalan min_gap-u provajdera — ne fiksan 0.1-0.8s.
                        # S window_size=1 i min_gap=7.5s (Gemini 3.5-flash): stagger je 0s
                        # (već serijski). S window_size=2: idx 0 → 0s, idx 1 → 3.75s.
                        # Ovo sprečava thundering herd gdje svi krenu u 0.7s prozoru.
                        try:
                            from config.ai_config import get_min_gap

                            _prov = getattr(self.engine, "_primary_provider", "GEMINI")
                            _gap = get_min_gap(_prov)
                        except Exception:
                            _gap = 7.5
                        stagger = (idx % max(window_size, 1)) * (
                            _gap / max(window_size, 1)
                        )
                        stagger += random.uniform(0.1, 0.5)  # mali jitter
                        await asyncio.sleep(stagger)

                    p_ctx = p_ctx_func(chunks, idx)
                    n_ctx = n_ctx_func(chunks, idx)
                    res, eng = None, "N/A"
                    for _pokusaj in range(1 + _MAX_PONOVNIH):
                        res, eng = await self.engine.process_chunk_with_ai(
                            chunk, p_ctx, n_ctx, idx, file_name
                        )
                        if res is not None:
                            break
                        if eng == "QUOTA_STOP":
                            break
                        if _pokusaj < _MAX_PONOVNIH:
                            _pauza = _RETRY_PAUZA * (_pokusaj + 1)
                            self.engine.log(
                                f"🔄 Blok {idx} nije obrađen ({eng}) — ponovni pokušaj "
                                f"{_pokusaj + 1}/{_MAX_PONOVNIH} za {_pauza}s",
                                "warning",
                            )
                            await asyncio.sleep(_pauza)
                    return idx, res, eng
                except Exception as e:
                    self.engine.log(f"❌ Task greška za blok {idx}: {e}", "error")
                    return idx, None, "ERROR"

        # Kreiraj sve taskove odjednom — semaphore ih prirodno kontroliše
        # (ovo je ispravno za sliding window: taskovi čekaju na acquire,
        #  ne čekaju da prethodni task završi pa tek onda bude kreiran)
        tasks = [
            asyncio.create_task(process_one(i, chunk)) for i, chunk in enumerate(chunks)
        ]

        # Procesuj rezultate čim stignu (ne čekaj na redosljed)
        for completed_task in asyncio.as_completed(tasks):
            try:
                idx, res, eng = await completed_task
                results[idx] = (res, eng)
                self.engine.log(f"📦 Blok {idx} završen ({eng})", "tech")
            except Exception as e:
                self.engine.log(f"❌ Nezabilježena task greška: {e}", "error")

        # Humanizovana pauza nakon cijelog batcha (između poglavlja)
        delay = random.uniform(*self._human_delay)
        await asyncio.sleep(delay)

        # P2.17: ukloni echo konteksta (blok N pocinje kopijom kraja bloka N-1)
        try:
            from core.preklop import skini_preklop

            for _i in range(1, len(results)):
                _pt, _ct = results[_i - 1][0], results[_i][0]
                if isinstance(_pt, str) and isinstance(_ct, str):
                    _novo, _n = skini_preklop(_pt, _ct)
                    if _n:
                        results[_i] = (_novo, results[_i][1])
                        self.engine.log(
                            f"preklop: {file_name} blok {_i}: uklonjeno {_n} ponovljenih odlomaka",
                            "warning",
                        )
        except Exception:
            logger.exception("[P2.17] preklop guard")

        return results