import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3

logger = logging.getLogger(__name__)

class UniswapV3QuoterHelper:
    """Helper for Uniswap V3 Quoter contract integration"""
    
    # Quoter V2 ABI (minimal)
    QUOTER_V2_ABI = [
        {
            "inputs": [
                {"name": "tokenIn", "type": "address"},
                {"name": "tokenOut", "type": "address"},
                {"name": "fee", "type": "uint24"},
                {"name": "amountIn", "type": "uint256"},
                {"name": "sqrtPriceLimitX96", "type": "uint160"}
            ],
            "name": "quoteExactInputSingle",
            "outputs": [
                {"name": "amountOut", "type": "uint256"},
                {"name": "sqrtPriceX96After", "type": "uint160"},
                {"name": "initializedTicksCrossed", "type": "uint32"},
                {"name": "gasEstimate", "type": "uint256"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"name": "tokenIn", "type": "address"},
                {"name": "tokenOut", "type": "address"},
                {"name": "fee", "type": "uint24"},
                {"name": "amountOut", "type": "uint256"},
                {"name": "sqrtPriceLimitX96", "type": "uint160"}
            ],
            "name": "quoteExactOutputSingle", 
            "outputs": [
                {"name": "amountIn", "type": "uint256"},
                {"name": "sqrtPriceX96After", "type": "uint160"},
                {"name": "initializedTicksCrossed", "type": "uint32"},
                {"name": "gasEstimate", "type": "uint256"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    
    def __init__(self, w3, quoter_address: str):
        self.w3 = w3
        self.quoter_address = quoter_address
        
        # Initialize quoter contract (async compatible)
        self.quoter = w3.eth.contract(
            address=Web3.to_checksum_address(quoter_address),
            abi=self.QUOTER_V2_ABI
        )
    
    async def quote_exact_input_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_in: int,
        sqrt_price_limit_x96: int = 0
    ) -> Optional[Dict[str, int]]:
        """Get exact input quote from Quoter V2"""
        try:
            result = await self.quoter.functions.quoteExactInputSingle(
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out),
                fee,
                amount_in,
                sqrt_price_limit_x96
            ).call()
            
            amount_out, sqrt_price_x96_after, ticks_crossed, gas_estimate = result
            
            return {
                "amountOut": amount_out,
                "sqrtPriceX96After": sqrt_price_x96_after,
                "initializedTicksCrossed": ticks_crossed,
                "gasEstimate": gas_estimate
            }
            
        except Exception as e:
            logger.error(f"Error getting V3 quote: {e}")
            return None
    
    async def quote_exact_output_single(
        self,
        token_in: str,
        token_out: str,
        fee: int,
        amount_out: int,
        sqrt_price_limit_x96: int = 0
    ) -> Optional[Dict[str, int]]:
        """Get exact output quote from Quoter V2"""
        try:
            result = await self.quoter.functions.quoteExactOutputSingle(
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out),
                fee,
                amount_out,
                sqrt_price_limit_x96
            ).call()
            
            amount_in, sqrt_price_x96_after, ticks_crossed, gas_estimate = result
            
            return {
                "amountIn": amount_in,
                "sqrtPriceX96After": sqrt_price_x96_after,
                "initializedTicksCrossed": ticks_crossed,
                "gasEstimate": gas_estimate
            }
            
        except Exception as e:
            logger.error(f"Error getting V3 output quote: {e}")
            return None
    
    async def get_optimal_amount_out(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        token_in_decimals: int,
        token_out_decimals: int,
        fee_tier: int = 3000
    ) -> Decimal:
        """Get accurate amount out using Quoter with proper decimal handling"""
        try:
            # Convert to wei with proper decimals
            amount_in_wei = int(amount_in * Decimal(f"1e{token_in_decimals}"))
            
            # Get quote from quoter
            quote_result = await self.quote_exact_input_single(
                token_in,
                token_out,
                fee_tier,
                amount_in_wei
            )
            
            if not quote_result:
                return Decimal("0")
            
            # Convert back to decimal units
            amount_out_wei = quote_result["amountOut"]
            amount_out = Decimal(str(amount_out_wei)) / Decimal(f"1e{token_out_decimals}")
            
            return amount_out
            
        except Exception as e:
            logger.error(f"Error getting optimal amount out: {e}")
            return Decimal("0")