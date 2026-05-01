from pydantic import BaseModel, field_validator
from typing import List, Optional, TypedDict
from datetime import datetime

class Transaction(BaseModel):
    date: Optional[str] = None
    description: str
    amount: float

    @field_validator('date')
    @classmethod
    def validate_date(cls, v: str) -> str:
        if v is None:
            return v
        
        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%d.%m.%Y",
            "%d %b %Y",
            "%d %B %Y",
        ]
        for fmt in formats:
            try:
                datetime.strptime(v, fmt)
                return v
            except ValueError:
                continue

        raise ValueError(f"Unrecognised date format: '{v}'")

class StatementData(BaseModel):
    account_holder: str        # required
    closing_balance: float     # required
    account_number: Optional[str] = None
    statement_date: Optional[str] = None
    currency: Optional[str] = None
    bank_name: Optional[str] = None
    transactions: Optional[List[Transaction]] = None

class AgentState(TypedDict, total=False):
    file_path: str
    raw_text: str
    format: str           # "text" or "scanned"
    extracted_json: str   # raw JSON string from Claude
    validated_data: dict  # parsed + Pydantic-validated dict
    output_path: str
    job_id: str
    error: str
    statement_month: str
    client_id: str
    format_id: str