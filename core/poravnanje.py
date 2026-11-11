"""P2.15: poravnanje EN-HR po recenici (Gale-Church, samo duljine znakova, bez ovisnosti)."""
import math
import re

_PRIOR = {(1, 1): 0.89, (1, 0): 0.01, (0, 1): 0.01, (2, 1): 0.09, (1, 2): 0.09, (2, 2): 0.02}
_C, _S2 = 1.1, 6.8
_SPLIT = re.compile(
    r"""(?:(?<=[.!?…])|(?<=[.!?…][”"»’']))\s+(?=[„“"«‘'(\[—-]*\s*[A-ZČĆŽŠĐ0-9])"""
)


def recenice(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    if not t:
        return []
    return [s.strip() for s in _SPLIT.split(t) if s.strip()]


def _cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _cost(l1, l2, prior):
    if l1 == 0 and l2 == 0:
        return 0.0
    mean = (l1 + l2 / _C) / 2.0
    d = (l2 - l1 * _C) / math.sqrt(max(mean, 1e-9) * _S2)
    p = 2 * (1 - _cdf(abs(d)))
    return -math.log(max(p, 1e-12) * prior)


def poravnaj(en_s, hr_s):
    """Lista zrna ((e0, e1), (h0, h1)); poluotvoreni rasponi indeksa recenica. [] ako ne uspije."""
    n, m = len(en_s), len(hr_s)
    le = [len(s) for s in en_s]
    lh = [len(s) for s in hr_s]
    INF = 1e18
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    B = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if D[i][j] >= INF:
                continue
            for (a, b), pr in _PRIOR.items():
                ni, nj = i + a, j + b
                if ni > n or nj > m:
                    continue
                c = D[i][j] + _cost(sum(le[i:ni]), sum(lh[j:nj]), pr)
                if c < D[ni][nj]:
                    D[ni][nj] = c
                    B[ni][nj] = (i, j)
    if D[n][m] >= INF:
        return []
    out, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj = B[i][j]
        out.append(((pi, i), (pj, j)))
        i, j = pi, pj
    return out[::-1]
