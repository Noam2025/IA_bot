from pydantic import BaseModel, Field, validator
from typing import List, Optional

class TakeProfit(BaseModel):
    price: float
    size_pct: float
    reduce_only: bool = True

class RiskModel(BaseModel):
    risk_per_trade_pct: float
    stop_loss: float
    take_profits: List[TakeProfit]

class OrderModel(BaseModel):
    type: str
    price: Optional[float]
    quantity_usdt: float

class DecisionModel(BaseModel):
    symbol: str
    action: str
    order: OrderModel
    risk: RiskModel

def validate_decision_json(data: dict):
    DecisionModel(**data)
