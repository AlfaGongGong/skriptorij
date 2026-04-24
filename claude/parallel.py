# processing/parallel.py
import asyncio
import random
import time
from collections import defaultdict

class AdaptiveParallelism:
    """
    Upravlja paralelnom obradom chunkova uz poštovanje rate limita.
    """
    def __init__(self, engine):
        self.engine = engine
        self.provider_semaphores = {}
        self._last_batch_time = 0
        self._human_delay = (2.0, 5.0)  # raspon pauze između batch-eva (sekunde)

    def _get_max_concurrent_for_provider(self, prov_upper: str) -> int:
        """
        Izračunava koliko paralelnih poziva možemo poslati provideru.
        """
        fleet = self.engine.fleet
        keys = fleet.fleet.get(prov_upper, [])
        active_keys = [k for k in keys if k.available]
        if not active_keys:
            return 0

        # Konzervativno: 1 poziv po aktivnom ključu
        # Možemo povećati ako RPM dozvoljava, ali bolje biti siguran
        base_concurrency = len(active_keys)

        # Dodatno ograničenje na osnovu RPM
        rpm_limit = fleet.get_effective_rpm_limit(prov_upper, active_keys[0].key)
        if rpm_limit > 0:
            # Pretpostavimo da jedan poziv traje ~10 sekundi
            est_duration = 10.0
            max_by_rpm = max(1, int(rpm_limit / (60 / est_duration)))
            base_concurrency = min(base_concurrency, max_by_rpm)

        # Maksimalno 5 paralelnih poziva po provideru (da ne izgleda kao DDoS)
        return min(base_concurrency, 5)

    async def _acquire_provider_slot(self, prov_upper: str):
        """
        Dobavlja semaphore slot za dati provider.
        """
        if prov_upper not in self.provider_semaphores:
            max_conc = self._get_max_concurrent_for_provider(prov_upper)
            if max_conc <= 0:
                max_conc = 1  # fallback
            self.provider_semaphores[prov_upper] = asyncio.Semaphore(max_conc)
        return self.provider_semaphores[prov_upper]

    async def process_chunks_parallel(self, chunks, file_name, p_ctx_func, n_ctx_func):
        """
        Obrađuje listu chunkova paralelno, ali uz poštovanje limita.
        """
        results = [None] * len(chunks)
        tasks = []

        # Grupišemo chunkove po provajderu koji će ih obraditi (na osnovu uloge)
        # Za sada, svi chunkovi koriste istu ulogu (PREVODILAC/LEKTOR), pa će ih
        # Fleet Manager rasporediti. Mi samo ograničavamo ukupnu konkurentnost.
        
        # Izračunaj globalni maksimum paralelnih poziva
        total_active_keys = self.engine.fleet.get_total_active_keys()
        max_global = min(total_active_keys, 8)  # maksimalno 8 istovremenih poziva ukupno
        global_semaphore = asyncio.Semaphore(max_global)

        async def process_one(idx, chunk):
            async with global_semaphore:
                # Dodaj malu nasumičnu pauzu da ne krenu svi u istom trenutku
                await asyncio.sleep(random.uniform(0.1, 1.5))
                
                p_ctx = p_ctx_func(chunks, idx)
                n_ctx = n_ctx_func(chunks, idx)
                res, eng = await self.engine.process_chunk_with_ai(
                    chunk, p_ctx, n_ctx, idx, file_name
                )
                return idx, res, eng

        for i, chunk in enumerate(chunks):
            tasks.append(asyncio.create_task(process_one(i, chunk)))

        # Sačekaj sve taskove
        for task in asyncio.as_completed(tasks):
            idx, res, eng = await task
            results[idx] = (res, eng)
            self.engine.log(f"📦 Blok {idx} završen ({eng})", "tech")

        # Humanizovana pauza između batch-eva
        delay = random.uniform(*self._human_delay)
        await asyncio.sleep(delay)

        return results
