import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for generating text embeddings via Gemini API.

    Ported from Dart GeminiService in gemini_service.dart.
    Uses the google-genai Python SDK.
    """

    def __init__(self, api_key: str, model: str = 'gemini-embedding-001') -> None:
        self._client: genai.Client = genai.Client(api_key=api_key)
        self._model: str = model

    async def get_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            Exception: If the API call fails.
        """
        logger.info(f'Generating embedding for: "{text[:80]}..."')
        try:
            result = self._client.models.embed_content(
                model=self._model,
                contents=text,
            )
            if result.embeddings and len(result.embeddings) > 0:
                values = result.embeddings[0].values
                if values:
                    logger.info(f'Embedding generated. Vector length: {len(values)}')
                    return list(values)
            logger.warning('Empty embedding returned')
            return []
        except Exception as e:
            logger.error(f'Failed to generate embedding: {e}')
            raise
