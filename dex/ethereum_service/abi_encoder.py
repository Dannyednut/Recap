import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal
from web3 import Web3
from eth_abi import encode

logger = logging.getLogger(__name__)

class SwapCallDataEncoder:
    """Encode real swap function calls for Uniswap V2/V3"""
    
    # Uniswap V2 Router function selectors
    SWAP_EXACT_TOKENS_FOR_TOKENS = "0x38ed1739"  # swapExactTokensForTokens
    SWAP_TOKENS_FOR_EXACT_TOKENS = "0x8803dbee"  # swapTokensForExactTokens
    
    # Uniswap V3 Router function selectors (corrected)
    EXACT_INPUT_SINGLE = "0x04e45aaf"  # exactInputSingle - SwapRouter
    EXACT_OUTPUT_SINGLE = "0xf28c0498"  # exactOutputSingle - SwapRouter
    MULTICALL = "0xac9650d8"  # multicall(bytes[]) - SwapRouter02
    
    @staticmethod
    def encode_v2_swap_exact_tokens_for_tokens(
        amount_in: int,
        amount_out_min: int, 
        path: List[str],
        to: str,
        deadline: int
    ) -> str:
        """Encode Uniswap V2 swapExactTokensForTokens call"""
        try:
            # Function signature: swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
            encoded_params = encode(
                ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
                [amount_in, amount_out_min, path, to, deadline]
            )
            
            return SwapCallDataEncoder.SWAP_EXACT_TOKENS_FOR_TOKENS + encoded_params.hex()
            
        except Exception as e:
            logger.error(f"Error encoding V2 swap: {e}")
            return ""
    
    @staticmethod
    def encode_v3_exact_input_single(
        token_in: str,
        token_out: str,
        fee: int,
        recipient: str,
        deadline: int,
        amount_in: int,
        amount_out_minimum: int,
        sqrt_price_limit_x96: int = 0
    ) -> str:
        """Encode Uniswap V3 exactInputSingle call"""
        try:
            # ExactInputSingleParams struct encoding
            params_tuple = (
                token_in,
                token_out, 
                fee,
                recipient,
                deadline,
                amount_in,
                amount_out_minimum,
                sqrt_price_limit_x96
            )
            
            encoded_params = encode(
                ['(address,address,uint24,address,uint256,uint256,uint256,uint160)'],
                [params_tuple]
            )
            
            return SwapCallDataEncoder.EXACT_INPUT_SINGLE + encoded_params.hex()
            
        except Exception as e:
            logger.error(f"Error encoding V3 swap: {e}")
            return ""
    
    @staticmethod
    def encode_erc20_approve(spender: str, amount: int) -> str:
        """Encode ERC20 approve call"""
        try:
            # Function signature: approve(address,uint256)
            function_selector = "0x095ea7b3"
            encoded_params = encode(['address', 'uint256'], [spender, amount])
            
            return function_selector + encoded_params.hex()
            
        except Exception as e:
            logger.error(f"Error encoding approve: {e}")
            return ""
    
    @staticmethod
    def encode_multicall(calls: List[str]) -> str:
        """Encode multiple calls into a single multicall transaction (SwapRouter)"""
        try:
            # SwapRouter02 multicall function signature: multicall(bytes[])
            function_selector = "0xac9650d8"
            
            # Convert hex strings to bytes
            call_bytes = [bytes.fromhex(call[2:]) if call.startswith('0x') else bytes.fromhex(call) for call in calls]
            
            encoded_params = encode(['bytes[]'], [call_bytes])
            
            return function_selector + encoded_params.hex()
            
        except Exception as e:
            logger.error(f"Error encoding multicall: {e}")
            return ""
    
    @staticmethod
    def build_v2_swap_transaction(
        router_address: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        amount_out_min: Decimal,
        wallet_address: str,
        token_in_decimals: int = 18,
        token_out_decimals: int = 18,
        deadline_offset: int = 1200
    ) -> Dict[str, Any]:
        """Build complete V2 swap transaction with proper decimal handling"""
        try:
            import time
            
            # Convert to wei amounts with correct decimals
            amount_in_wei = int(amount_in * Decimal(f"1e{token_in_decimals}"))
            amount_out_min_wei = int(amount_out_min * Decimal(f"1e{token_out_decimals}"))
            deadline = int(time.time()) + deadline_offset
            
            # Build path
            path = [Web3.to_checksum_address(token_in), Web3.to_checksum_address(token_out)]
            
            # Encode call data
            call_data = SwapCallDataEncoder.encode_v2_swap_exact_tokens_for_tokens(
                amount_in_wei,
                amount_out_min_wei,
                path,
                Web3.to_checksum_address(wallet_address),
                deadline
            )
            
            return {
                "to": Web3.to_checksum_address(router_address),
                "value": 0,
                "data": call_data,
                "gas": 150000  # Estimated gas
            }
            
        except Exception as e:
            logger.error(f"Error building V2 swap transaction: {e}")
            return {}
    
    @staticmethod
    def build_v3_swap_transaction(
        router_address: str,
        token_in: str,
        token_out: str,
        fee_tier: int,
        amount_in: Decimal,
        amount_out_min: Decimal,
        wallet_address: str,
        token_in_decimals: int = 18,
        token_out_decimals: int = 18,
        deadline_offset: int = 1200
    ) -> Dict[str, Any]:
        """Build complete V3 swap transaction with proper decimal handling"""
        try:
            import time
            
            # Convert to wei amounts with correct decimals
            amount_in_wei = int(amount_in * Decimal(f"1e{token_in_decimals}"))
            amount_out_min_wei = int(amount_out_min * Decimal(f"1e{token_out_decimals}"))
            deadline = int(time.time()) + deadline_offset
            
            # Encode call data
            call_data = SwapCallDataEncoder.encode_v3_exact_input_single(
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out),
                fee_tier,
                Web3.to_checksum_address(wallet_address),
                deadline,
                amount_in_wei,
                amount_out_min_wei,
                0  # No price limit
            )
            
            return {
                "to": Web3.to_checksum_address(router_address),
                "value": 0,
                "data": call_data,
                "gas": 180000  # Estimated gas
            }
            
        except Exception as e:
            logger.error(f"Error building V3 swap transaction: {e}")
            return {}