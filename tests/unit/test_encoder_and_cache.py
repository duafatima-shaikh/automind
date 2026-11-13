import numpy as np

from automind.embeddings.cache import CachedEncoder, EmbeddingCache
from automind.embeddings.encoder import HashingEncoder


def test_hash_encoder_is_deterministic_and_normalised():
    encoder = HashingEncoder(128)
    a = encoder.encode(["solar panels make electricity"])
    b = encoder.encode(["solar panels make electricity"])
    assert np.allclose(a, b)
    assert abs(np.linalg.norm(a[0]) - 1) < 1e-5


def test_similar_text_is_closer_than_different_text():
    encoder = HashingEncoder(256)
    q, near, far = encoder.encode(
        ["how long does coffee steep", "coffee should steep for four minutes", "bicycles dock here"]
    )
    assert q @ near > q @ far


def test_cache_avoids_recomputing(tmp_path):
    cache = EmbeddingCache(tmp_path / "c.db")
    encoder = CachedEncoder(HashingEncoder(64), cache)
    first = encoder.encode(["alpha beta", "gamma delta"])
    second = encoder.encode(["alpha beta", "new text"])
    assert encoder.hits == 1 and encoder.misses == 3
    assert np.allclose(first[0], second[0])
