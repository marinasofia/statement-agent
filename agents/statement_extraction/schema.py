from pydantic import BaseModel
from typing import List, Optional, Any

class Transaction(BaseModel):
    date: str
    description: str
    amount: float
 
class StatementData(BaseModel):
    account_holder: Optional[str] = None
    account_number: Optional[str] = None
    statement_date: Optional[str] = None
    closing_balance: Optional[float] = None
    transactions: Optional[List[Transaction]] = None

class AgentState(dict):
    file_path: Optional[str] = None
    raw_text: Optional[str] = None
    extracted_json: Optional[dict] = None
    validated_data: Optional[Any] = None
    output_path: Optional[str] = None
    job_id: Optional[str] = None
    error: Optional[str] = None
