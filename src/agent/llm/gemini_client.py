from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, ValidationError

from google import genai

class GeminiConfig(BaseModel):
    model: str = "gemini-2.0-pro"
    temperature: float = 0.2
    max_output_tokens: int = 1200
    
class GeminiClient:
    def __init__(self, cfg: Optional[GeminiConfig] = None):
        self.cfg = cfg or GeminiConfig()
        self.client = genai.client()
        
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Extract a single JSON object from text (fenced blocks or raw).
        Uses brace matching so nested objects parse correctly.
        """
        if "```" in text:
            parts = [p for p in text.split("```") if p.strip()]
            text = max(parts, key=len)

        start = text.find("{")
        if start == -1:
            raise ValueError(f"Model did not return JSON. RAW: {text[:400]}")
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])
        raise ValueError(f"No matching closing brace for JSON. RAW: {text[:400]}")
    
    def generate_json(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        prompt = f""" System:
        {system}
        USER:
        {user}
        Return ONLY VALID JSON that matches this schema:
        {schema.model_json_schema()}
        """
        resp = self.client.models.generate_content(
            model = self.cfg.model,
            contents=prompt,
            config={
                "temperature": self.cfg.temperature,
                "max_output_tokens": self.cfg.max_output_tokens,
            },
        )
        text = resp.text or ""
        data = self._extract_json(text)
        try:
            return schema(**data)
        except ValidationError as e:
            raise ValueError(f"JSON did not match schema: {e}\n Raw: {text[:400]}")