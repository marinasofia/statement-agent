"""Record and replay model responses so the eval suite can run without a key.

A cassette entry is keyed by a hash of everything that determines the
model's answer: model id, system prompt, user message, and the output
schema. Change any of those and the key changes, so a stale recording can
never be replayed against a new prompt by accident; replay raises and
tells you to re-record.

Modes, set with LLM_CASSETTE_MODE and LLM_CASSETTE_DIR:
  (unset)  live calls, nothing recorded
  record   live calls, response written to the cassette dir
  replay   no network; missing recording is an error
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Optional


class CassetteMissing(RuntimeError):
    pass


def _key(model: str, system_prompt: str, user_message: str, schema: dict) -> str:
    payload = json.dumps(
        {"model": model, "system": system_prompt, "user": user_message, "schema": schema},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class CassetteStore:
    def __init__(self, directory: str, mode: str):
        self.directory = Path(directory)
        self.mode = mode
        if mode == "record":
            self.directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> Optional["CassetteStore"]:
        mode = os.getenv("LLM_CASSETTE_MODE", "").strip().lower()
        directory = os.getenv("LLM_CASSETTE_DIR", "").strip()
        if mode in ("record", "replay") and directory:
            return cls(directory, mode)
        return None

    def path_for(self, model, system_prompt, user_message, schema) -> Path:
        return self.directory / f"{_key(model, system_prompt, user_message, schema)}.json"

    def load(self, model, system_prompt, user_message, schema) -> dict:
        path = self.path_for(model, system_prompt, user_message, schema)
        if not path.is_file():
            raise CassetteMissing(
                f"No recorded response for model={model} (key {path.stem}). "
                "Run the evals with --mode record to create it."
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, model, system_prompt, user_message, schema, entry: dict) -> None:
        path = self.path_for(model, system_prompt, user_message, schema)
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
