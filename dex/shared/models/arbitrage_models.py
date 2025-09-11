from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

@dataclass
class Token:
    address: str
    symbol: str
    decimals: int
    name: str

@dataclass
class DexPair:
    address: str
    token_a: Token
    token_b: Token
    dex_name: str
    protocol_version: str  # "v2" or "v3"
    fee_tier: Optional[int] = None  # For V3 pools

@dataclass
class ArbitrageOpportunity:
    opportunity_id: str
    strategy_type: str  # "cross", "triangular", "mempool_backrun"
    chain: str
    profit_percentage: Decimal
    profit_amount_usd: Decimal
    gas_cost_usd: Decimal
    net_profit_usd: Decimal
    detected_at: datetime
    status: str = "active"
    
    # Cross arbitrage specific
    buy_pair: Optional[DexPair] = None
    sell_pair: Optional[DexPair] = None
    buy_price: Optional[Decimal] = None
    sell_price: Optional[Decimal] = None
    
    # Triangular arbitrage specific
    trading_path: Optional[List[DexPair]] = None
    tokens_path: Optional[List[Token]] = None
    
    # Mempool backrun specific
    target_tx_hash: Optional[str] = None
    backrun_strategy: Optional[str] = None

@dataclass
class FlashLoanParams:
    provider: str  # "aave", "dydx", "balancer"
    asset: str
    amount: Decimal
    callback_data: Dict[str, Any]

@dataclass
class ExecutionResult:
    tx_hash: str
    status: str  # "success", "failed", "pending"
    gas_used: int
    gas_price: int
    profit_realized: Optional[Decimal] = None
    execution_time_ms: Optional[int] = None
    error_message: Optional[str] = None