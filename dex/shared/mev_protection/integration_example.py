"""
Example integration showing how to use MEV protection across different chains
"""

import asyncio
import logging
from typing import Dict, Any
from dex.chain_factory import ChainFactory
from dex.shared.mev_protection import UniversalMEVProtection

logger = logging.getLogger(__name__)

class MEVProtectedArbitrageManager:
    """
    Example manager showing how to use MEV protection across chains
    """
    
    def __init__(self):
        self.chain_factory = ChainFactory()
        self.executors = {}
        
    async def initialize_chains(self, chains: list):
        """Initialize contract executors for multiple chains with MEV protection"""
        for chain in chains:
            try:
                executor = self.chain_factory.create_contract_executor(chain)
                await executor.initialize()
                self.executors[chain] = executor
                logger.info(f"Initialized {chain} executor with MEV protection")
            except Exception as e:
                logger.error(f"Failed to initialize {chain} executor: {e}")
    
    async def execute_cross_chain_arbitrage(self, opportunities: Dict[str, Any]):
        """Execute arbitrage opportunities with appropriate MEV protection per chain"""
        
        for chain, params in opportunities.items():
            if chain not in self.executors:
                logger.warning(f"No executor available for {chain}")
                continue
                
            executor = self.executors[chain]
            
            try:
                if params.get("type") == "backrun":
                    # Execute backrun with MEV protection
                    result = await executor.execute_backrun_arbitrage(params)
                    logger.info(f"{chain} backrun result: {result}")
                    
                elif params.get("type") == "arbitrage":
                    # Execute regular arbitrage with MEV protection
                    result = await executor.execute_arbitrage(params)
                    logger.info(f"{chain} arbitrage result: {result}")
                    
                elif params.get("type") == "triangular":
                    # Execute triangular arbitrage with MEV protection
                    result = await executor.execute_triangular_arbitrage(params)
                    logger.info(f"{chain} triangular result: {result}")
                    
            except Exception as e:
                logger.error(f"Error executing {chain} arbitrage: {e}")

# Example usage
async def main():
    """Example of how to use MEV-protected arbitrage across chains"""
    
    manager = MEVProtectedArbitrageManager()
    
    # Initialize executors for multiple chains
    await manager.initialize_chains(["ethereum", "bsc", "polygon", "solana"])
    
    # Example arbitrage opportunities
    opportunities = {
        "ethereum": {
            "type": "backrun",
            "targetTxHash": "0x123...",
            "path": ["0xA0b86a33E6441E6C7D3E4C2F2B0928d4C4F6C8D1", "0xdAC17F958D2ee523a2206206994597C13D831ec7"],
            "routers": ["0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D", "0xE592427A0AEce92De3Edee1F18E0157C05861564"],
            "fees": [3000, 500],
            "amountIn": 1000000000000000000,  # 1 ETH
            "minProfitAmount": 50000000000000000,  # 0.05 ETH
            "maxGasPrice": 50000000000,  # 50 gwei
            "useFlashbots": True
        },
        "bsc": {
            "type": "arbitrage",
            "tokenA": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
            "tokenB": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",  # BUSD
            "amountIn": 1000000000000000000,  # 1 BNB
            "buyRouter": "0x10ED43C718714eb63d5aA57B78B54704E256024E",  # PancakeSwap
            "sellRouter": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",  # Biswap
            "buyFee": 2500,
            "sellFee": 2500,
            "minProfit": 10000000000000000,  # 0.01 BNB
            "useMEVProtection": True
        },
        "polygon": {
            "type": "triangular",
            "path": [
                "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
                "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
                "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
                "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"   # Back to WMATIC
            ],
            "routers": [
                "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",  # QuickSwap
                "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",  # SushiSwap
                "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"   # QuickSwap
            ],
            "fees": [3000, 3000, 3000],
            "amountIn": 100000000000000000000,  # 100 MATIC
            "minProfitAmount": 1000000000000000000,  # 1 MATIC
            "useMEVProtection": True
        },
        "solana": {
            "type": "arbitrage",
            "input_mint": "So11111111111111111111111111111111111111112",  # SOL
            "intermediate_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "output_mint": "So11111111111111111111111111111111111111112",  # Back to SOL
            "amount_in": 1000000000,  # 1 SOL (in lamports)
            "USE_MEV_PROTECTION": True
        }
    }
    
    # Execute arbitrage opportunities with MEV protection
    await manager.execute_cross_chain_arbitrage(opportunities)

if __name__ == "__main__":
    asyncio.run(main())
