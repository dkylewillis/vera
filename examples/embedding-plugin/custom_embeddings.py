from sentence_transformers import SentenceTransformer

DIMENSIONS = {"all-MiniLM-L6-v2": 384, "all-mpnet-base-v2": 768}


class CustomEmbedder:
    normalization = "l2"

    def __init__(self, model_id: str):
        self.model_name = f"custom:{model_id}"
        self.dimension = DIMENSIONS[model_id]
        self._model_id = model_id
        self._model = None

    def embed(self, texts: list[str]):
        if self._model is None:
            self._model = SentenceTransformer(self._model_id, device="cpu")
        return self._model.encode(texts, normalize_embeddings=True)
