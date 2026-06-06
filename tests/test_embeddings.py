import math

from paper_rag.embeddings import HashEmbeddingClient


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    client = HashEmbeddingClient(dimensions=16)

    first, second = client.embed_texts(["alpha beta retrieval", "alpha beta retrieval"])

    assert first == second
    assert len(first) == 16
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_hash_embedding_handles_empty_text() -> None:
    client = HashEmbeddingClient(dimensions=8)

    assert client.embed_texts(["   "]) == [[0.0] * 8]

