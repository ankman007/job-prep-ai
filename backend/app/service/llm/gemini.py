import json
from os import getenv
from loguru import logger
from google import genai
from google.genai import types

from app.service.llm.base import BaseLLM


class GeminiLLM(BaseLLM):
    def __init__(self):
        GEMINI_API_KEY = getenv('GEMINI_API_KEY')
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not found in environment variables.")
            raise ValueError("GEMINI_API_KEY not found")

        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = getenv('GEMINI_MODEL', 'gemini-2.5-flash')

    def generate(self, prompt: str, schema: dict) -> dict:
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=16000,
                temperature=0.1,
                response_mime_type='application/json',
                response_json_schema=schema,
            ),
        )
        return json.loads(response.text)
