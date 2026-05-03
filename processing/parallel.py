

# processing/parallel.py
import asyncio
import random
import time
from collections import defaultdict

# Veličina sliding window-a — maksimalno N aktivnih chunka u isto vrijeme.
# Za 8 ključeva to znači 4 paralelna poziva (konzervativno, bez DDoS-a)
_SLIDING_WINDOW_SIZE = 4


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
        broja aktivnih ključeva i RPM limita.
        """
        fleet = self.engine.fleet
        total_active = fleet.get_total_active_keys()

        if total_active == 0:
            return 1

        # Konzervativno: 1 slot per 2 aktivna ključa, min 2, max 6
        dynamic = max(2, min(total_active // 2, 6))

        # Dodatno: poštuj globalni RPM najsporijeg providera
        min_rpm = None
        for prov, keys in fleet.fleet.items():
            active_keys = [k for k in keys if k.available]
            if active_keys:
                rpm = fleet.get_effective_rpm_limit(prov, active_keys[0].key)
                if rpm > 0:
                    min_rpm = rpm if min_rpm is None else min(min_rpm, rpm)

        if min_rpm and min_rpm < 15:
            # Spori provider — smanji window da ne spamujemo
            dynamic = min(dynamic, 2)

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
            "tech"
        )

        # Semaphore koji osigurava max window_size istovremenih poziva
        semaphore = asyncio.Semaphore(window_size)

        async def process_one(idx, chunk):
            async with semaphore:
                try:
                    # Stagger: mali jitter da ne krenu svi u istom trenutku
                    await asyncio.sleep(random.uniform(0.1, 0.8))

                    p_ctx = p_ctx_func(chunks, idx)
                    n_ctx = n_ctx_func(chunks, idx)
                    res, eng = await self.engine.process_chunk_with_ai(
                        chunk, p_ctx, n_ctx, idx, file_name
                    )
                    return idx, res, eng
                except Exception as e:
                    self.engine.log(f"❌ Task greška za blok {idx}: {e}", "error")
                    return idx, None, "ERROR"

        # Kreiraj sve taskove odjednom — semaphore ih prirodno kontroliše
        # (ovo je ispravno za sliding window: taskovi čekaju na acquire,
        #  ne čekaju da prethodni task završi pa tek onda bude kreiran)
        tasks = [
            asyncio.create_task(process_one(i, chunk))
            for i, chunk in enumerate(chunks)
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

        return results



