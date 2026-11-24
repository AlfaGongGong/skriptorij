import asyncio

from network import rate_limiter as rl


def test_cancel_ne_krade_slot():
    """Prekinut acquire_key mora vratiti globalni slot (stari kod ga je gubio)."""
    key = "TESTKEY_CANCEL_0001"
    sem = rl.get_key_semaphore(key)
    n = rl.MAX_CONCURRENT_PER_KEY
    for _ in range(n):
        assert sem.acquire(blocking=False)
    g0 = rl._GLOBAL_SEMAPHORE._value

    async def main():
        t = asyncio.create_task(rl.acquire_key(key))
        await asyncio.sleep(0.5)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.3)

    asyncio.run(main())
    assert rl._GLOBAL_SEMAPHORE._value == g0
    for _ in range(n):
        sem.release()
    assert sem._value == n


def test_acquire_release_normalno():
    key = "TESTKEY_NORMAL_0002"
    g0 = rl._GLOBAL_SEMAPHORE._value
    asyncio.run(rl.acquire_key(key))
    assert rl._GLOBAL_SEMAPHORE._value == g0 - 1
    rl.release_key(key)
    assert rl._GLOBAL_SEMAPHORE._value == g0
