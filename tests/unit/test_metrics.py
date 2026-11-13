from automind.evaluation.metrics import first_hit_rank, hit_at_k, mean_reciprocal_rank
from automind.utils.metrics import Metrics, percentile


def test_retrieval_metrics():
    ranks = [1, 3, None, 2]
    assert hit_at_k(ranks, 1) == 0.25
    assert hit_at_k(ranks, 3) == 0.75
    assert round(mean_reciprocal_rank(ranks), 3) == round((1 + 1 / 3 + 0.5) / 4, 3)
    assert first_hit_rank(["no", "yes  the   fact"], "The Fact") == 2


def test_metrics_collector():
    metrics = Metrics()
    metrics.incr("x", 2)
    for i in range(1, 101):
        metrics.observe("t", i / 1000)
    snap = metrics.snapshot()
    assert snap["counters"]["x"] == 2
    assert snap["timings"]["t"]["count"] == 100
    assert 90 <= percentile(list(range(1, 101)), 95) <= 96
