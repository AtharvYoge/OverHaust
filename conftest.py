"""Pytest fixtures — keep embeddings off unless test is marked @pytest.mark.embeddings."""
import os
import pytest


@pytest.fixture(autouse=True)
def embeddings_default_off(request):
    if "embeddings" in request.keywords:
        yield
        return
    prev = os.environ.get("OVERHAUST_EMBEDDINGS")
    os.environ["OVERHAUST_EMBEDDINGS"] = "0"
    yield
    if prev is None:
        os.environ.pop("OVERHAUST_EMBEDDINGS", None)
    else:
        os.environ["OVERHAUST_EMBEDDINGS"] = prev
