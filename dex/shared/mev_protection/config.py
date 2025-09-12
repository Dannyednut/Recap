"""
MEV Protection Configuration Management
Centralizes MEV-related settings across all supported chains
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class MEVProtectionConfig:
    """Configuration for MEV protection across all chains"""
    
    # Global MEV settings
    use_mev_protection: bool = True
    bundle_timeout: int = 60
    simulation_enabled: bool = True
    fallback_to_mempool: bool = True
    max_retry_attempts: int = 3
    
    # Ethereum/Flashbots settings
    flashbots_relay_url: str = "https://relay.flashbots.net"
    ethereum_max_priority_fee: int = 2_000_000_000  # 2 gwei
    ethereum_max_fee_per_gas: int = 50_000_000_000  # 50 gwei
    
    # BSC settings
    bsc_48club_relay_url: str = "https://rpc.48.club"
    bsc_max_gas_price: int = 20_000_000_000  # 20 gwei
    
    # Polygon settings
    polygon_flashlane_url: str = "https://polygon-mev.flashlane.org"
    polygon_max_priority_fee: int = 30_000_000_000  # 30 gwei
    
    # Solana settings
    solana_jito_relay_url: str = "https://mainnet.block-engine.jito.wtf"
    solana_max_compute_units: int = 1_400_000
    solana_priority_fee: int = 5_000
    
    @classmethod
    def from_env(cls) -> 'MEVProtectionConfig':
        """Create configuration from environment variables"""
        return cls(
            use_mev_protection=os.getenv('USE_MEV_PROTECTION', 'true').lower() == 'true',
            bundle_timeout=int(os.getenv('MEV_BUNDLE_TIMEOUT', '60')),
            simulation_enabled=os.getenv('MEV_SIMULATION_ENABLED', 'true').lower() == 'true',
            fallback_to_mempool=os.getenv('MEV_FALLBACK_TO_MEMPOOL', 'true').lower() == 'true',
            max_retry_attempts=int(os.getenv('MAX_MEV_RETRY_ATTEMPTS', '3')),
            
            flashbots_relay_url=os.getenv('FLASHBOTS_RELAY_URL', 'https://relay.flashbots.net'),
            ethereum_max_priority_fee=int(os.getenv('ETHEREUM_MAX_PRIORITY_FEE', '2000000000')),
            ethereum_max_fee_per_gas=int(os.getenv('ETHEREUM_MAX_FEE_PER_GAS', '50000000000')),
            
            bsc_48club_relay_url=os.getenv('BSC_48CLUB_RELAY_URL', 'https://rpc.48.club'),
            bsc_max_gas_price=int(os.getenv('BSC_MAX_GAS_PRICE', '20000000000')),
            
            polygon_flashlane_url=os.getenv('POLYGON_FLASHLANE_URL', 'https://polygon-mev.flashlane.org'),
            polygon_max_priority_fee=int(os.getenv('POLYGON_MAX_PRIORITY_FEE', '30000000000')),
            
            solana_jito_relay_url=os.getenv('SOLANA_JITO_RELAY_URL', 'https://mainnet.block-engine.jito.wtf'),
            solana_max_compute_units=int(os.getenv('SOLANA_MAX_COMPUTE_UNITS', '1400000')),
            solana_priority_fee=int(os.getenv('SOLANA_PRIORITY_FEE', '5000'))
        )
    
    def get_chain_config(self, chain_id: int) -> Dict[str, Any]:
        """Get chain-specific MEV configuration"""
        if chain_id == 1:  # Ethereum
            return {
                "relay_url": self.flashbots_relay_url,
                "max_priority_fee": self.ethereum_max_priority_fee,
                "max_fee_per_gas": self.ethereum_max_fee_per_gas,
                "use_simulation": self.simulation_enabled
            }
        elif chain_id == 56:  # BSC
            return {
                "relay_url": self.bsc_48club_relay_url,
                "max_gas_price": self.bsc_max_gas_price,
                "use_multi_rpc": True
            }
        elif chain_id == 137:  # Polygon
            return {
                "relay_url": self.polygon_flashlane_url,
                "max_priority_fee": self.polygon_max_priority_fee,
                "use_flashlane": True
            }
        elif chain_id == 101:  # Solana
            return {
                "relay_url": self.solana_jito_relay_url,
                "max_compute_units": self.solana_max_compute_units,
                "priority_fee": self.solana_priority_fee,
                "use_jito": True
            }
        else:
            return {}

# Global MEV configuration instance
mev_config = MEVProtectionConfig.from_env()
