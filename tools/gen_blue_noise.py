#!/usr/bin/env python3
"""Vygeneruje masku modrého šumu (void-and-cluster, Ulichney 1993) pro dithering „Modrý šum“.

Výstup: server/src/inka_server/assets/bluenoise64.npy – pořadí prahů 0..N-1 (uint16), 64×64, dlaždicové.
Deterministické (pevné semínko); stačí spustit jednou, výsledek je v gitu.
"""
import sys
from pathlib import Path

import numpy as np

SIZE = 64
SIGMA = 1.5


def gaussian_kernel_fft(n, sigma):
    ax = np.minimum(np.arange(n), n - np.arange(n))  # periodické vzdálenosti
    g = np.exp(-(ax[:, None] ** 2 + ax[None, :] ** 2) / (2 * sigma**2))
    return np.fft.rfft2(g)


def energy(pattern, kernel):
    return np.fft.irfft2(np.fft.rfft2(pattern) * kernel, s=pattern.shape)


def tightest_cluster(p, k):
    e = energy(p, k)
    e[p == 0] = -np.inf
    return np.unravel_index(np.argmax(e), p.shape)


def largest_void(p, k):
    e = energy(p, k)
    e[p == 1] = np.inf
    return np.unravel_index(np.argmin(e), p.shape)


def generate(n=SIZE, sigma=SIGMA, seed=1):
    rng = np.random.default_rng(seed)
    k = gaussian_kernel_fft(n, sigma)
    total = n * n
    ones = total // 10
    p = np.zeros((n, n), dtype=np.float64)
    p.flat[rng.choice(total, ones, replace=False)] = 1
    while True:  # rovnoměrné počáteční rozmístění
        c = tightest_cluster(p, k)
        p[c] = 0
        v = largest_void(p, k)
        if v == c:
            p[c] = 1
            break
        p[v] = 1
    ranks = np.zeros((n, n), dtype=np.int64)
    initial = p.copy()
    q = initial.copy()
    for r in range(ones - 1, -1, -1):  # fáze 1: odebírat z hustých míst
        c = tightest_cluster(q, k)
        q[c] = 0
        ranks[c] = r
    q = initial.copy()
    for r in range(ones, total):  # fáze 2 a 3: doplňovat do největších děr
        v = largest_void(q, k)
        q[v] = 1
        ranks[v] = r
    return ranks.astype(np.uint16)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "server/src/inka_server/assets/bluenoise64.npy"
    mask = generate()
    assert sorted(mask.ravel().tolist()) == list(range(SIZE * SIZE))
    np.save(out, mask)
    print(f"saved {out} {mask.shape}", file=sys.stderr)
