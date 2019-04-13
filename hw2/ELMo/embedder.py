import numpy as np
from .elmo import Embedder as ELMoEmbedder

class Embedder:
    """
    The class responsible for loading a pre-trained ELMo model and provide the ``embed``
    functionality for downstream BCN model.

    You can modify this class however you want, but do not alter the class name and the
    signature of the ``embed`` function. Also, ``__init__`` function should always have
    the ``ctx_emb_dim`` parameter.
    """

    def __init__(self, n_ctx_embs, ctx_emb_dim):
        """
        The value of the parameters should also be specified in the BCN model config.
        """
        self.n_ctx_embs = n_ctx_embs
        self.ctx_emb_dim = ctx_emb_dim
        # TODO
        self.e = ELMoEmbedder('./ELMo/144')

    def __call__(self, sentences, max_sent_len):
        """
        Generate the contextualized embedding of tokens in ``sentences``.

        Parameters
        ----------
        sentences : ``List[List[str]]``
            A batch of tokenized sentences.
        max_sent_len : ``int``
            All sentences must be truncated to this length.

        Returns
        -------
        ``np.ndarray``
            The contextualized embedding of the sentence tokens.

            The ndarray shape must be
            ``(len(sentences), min(max(map(len, sentences)), max_sent_len), self.n_ctx_embs, self.ctx_emb_dim)``
            and dtype must be ``np.float32``.
        """
        # TODO
        results = np.zeros((len(sentences), min(max(map(len, sentences)), max_sent_len), self.n_ctx_embs, self.ctx_emb_dim), dtype=np.float32)
        embeddings = self.e.sents2elmo(sentences, output_layer=-2)
        for i, embedding in enumerate(embeddings):
            embedding = np.transpose(embedding, (1, 0, 2))
            results[i, :embedding.shape[0], :, :] = embedding

        return results
