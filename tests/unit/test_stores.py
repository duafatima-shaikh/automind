import numpy as np

from automind.store.bm25_store import BM25Store
from automind.store.vector_store import VectorStore


def unit(*values):
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_vector_search_delete_and_persistence(tmp_path):
    path = tmp_path / "v.npz"
    store = VectorStore(3, path, use_faiss=False)
    store.add(["a", "b", "c"], np.vstack([unit(1, 0, 0), unit(0, 1, 0), unit(1, 1, 0)]))
    assert store.search(unit(1, 0, 0), 2)[0][0] == "a"
    assert [i for i, _ in store.search(unit(1, 0, 0), 5, allowed={"b", "c"})][0] == "c"
    store.save()
    reloaded = VectorStore(3, path, use_faiss=False)
    assert len(reloaded) == 3
    reloaded.delete(["a"])
    assert "a" not in [i for i, _ in reloaded.search(unit(1, 0, 0), 5)]


def test_vector_dimension_mismatch_is_clear(tmp_path):
    path = tmp_path / "v.npz"
    store = VectorStore(3, path, use_faiss=False)
    store.add(["a"], unit(1, 0, 0).reshape(1, -1))
    store.save()
    try:
        VectorStore(5, path, use_faiss=False)
    except ValueError as error:
        assert "size 3" in str(error)
    else:
        raise AssertionError("expected an error")


def test_bm25_ranks_exact_terms_and_removes_documents():
    store = BM25Store()
    store.add("1", "d1", "The monthly pass costs 18 dollars")
    store.add("2", "d2", "Coffee needs hot water")
    store.add("3", "d2", "Sleep needs darkness")
    assert store.search("monthly pass cost", 3)[0][0] == "1"
    assert store.search("coffee", 3, allowed_docs={"d1"}) == []
    store.remove_document("d2")
    assert len(store) == 1
    assert store.search("coffee", 3) == []
