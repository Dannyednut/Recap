"""
Orchestration configuration for multi-chain arbitrage
Defines capabilities, priorities, and coordination settings
"""
import os
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

class OrchestrationMode(Enum):
    """Orchestration layer modes"""
    SIMPLE = "simple"      # Uses ArbitrageManager directly
    ADVANCED = "advanced"  # Uses DEXArbitrageOrchestrator
    AUTO = "auto"         # Automatically selects best layer

@dataclass
class OrchestrationConfig:
    """Configuration for orchestration layer selection"""
    mode: OrchestrationMode
    max_concurrent_executions: int
    min_profit_threshold_usd: float
    max_position_size_usd: float
    execution_timeout: int
    health_check_interval: int
    risk_management_enabled: bool
    cross_chain_arbitrage_enabled: bool
    mempool_monitoring_enabled: bool
    
    @classmethod
    def from_environment(cls) -> 'OrchestrationConfig':
        """Create configuration from environment variables"""
        # Get orchestration mode from environment
        orchestrator_mode = os.getenv('ORCHESTRATOR_MODE', 'auto').lower()
        
        try:
            mode = OrchestrationMode(orchestrator_mode)
        except ValueError:
            mode = OrchestrationMode.AUTO
        
        return cls(
            mode=mode,
            max_concurrent_executions=int(os.getenv('MAX_CONCURRENT_EXECUTIONS', '3')),
            min_profit_threshold_usd=float(os.getenv('MIN_PROFIT_THRESHOLD_USD', '50.0')),
            max_position_size_usd=float(os.getenv('MAX_POSITION_SIZE_USD', '10000.0')),
            execution_timeout=int(os.getenv('EXECUTION_TIMEOUT', '300')),
            health_check_interval=int(os.getenv('HEALTH_CHECK_INTERVAL', '30')),
            risk_management_enabled=os.getenv('RISK_MANAGEMENT_ENABLED', 'true').lower() == 'true',
            cross_chain_arbitrage_enabled=os.getenv('CROSS_CHAIN_ARBITRAGE_ENABLED', 'false').lower() == 'true',
            mempool_monitoring_enabled=os.getenv('MEMPOOL_MONITORING_ENABLED', 'true').lower() == 'true'
        )

def get_orchestration_config() -> OrchestrationConfig:
    """Get the current orchestration configuration"""
    return OrchestrationConfig.from_environment()

def get_chain_capabilities(chains: List[str]) -> Dict[str, Dict[str, Any]]:
    """Detect capabilities of each chain service"""
    capabilities = {}
    
    for chain in chains:
        caps = {
            'has_pipeline': False,
            'has_mempool_monitor': False,
            'has_token_discovery': False,
            'has_protocol_adapters': False,
            'has_contract_deployment': False,
            'sophistication_level': 'basic'
        }
        
        if chain == 'ethereum':
            caps.update({
                'has_pipeline': True,
                'has_mempool_monitor': True,
                'has_token_discovery': True,
                'has_protocol_adapters': True,
                'has_contract_deployment': True,
                'sophistication_level': 'advanced'
            })
        elif chain in ['bsc', 'polygon']:
            caps.update({
                'has_pipeline': True,
                'has_mempool_monitor': False,
                'has_token_discovery': True,
                'has_protocol_adapters': True,
                'has_contract_deployment': True,
                'sophistication_level': 'advanced'
            })
        elif chain == 'solana':
            caps.update({
                'has_pipeline': False,
                'has_mempool_monitor': False,
                'has_token_discovery': True,
                'sophistication_level': 'intermediate'
            })
        
        capabilities[chain] = caps
    
    return capabilities

def determine_optimal_mode(config: OrchestrationConfig, chain_count: int, chain_capabilities: Dict[str, Dict[str, Any]] = None) -> OrchestrationMode:
    """Automatically determine the optimal orchestration mode based on chain capabilities"""
    if config.mode != OrchestrationMode.AUTO:
        return config.mode
    
    # Auto mode logic with chain capability awareness
    if chain_capabilities is None:
        chain_capabilities = get_chain_capabilities([])
    
    # Check if any chains have sophisticated pipeline capabilities
    has_pipeline_chains = any(
        caps.get('has_pipeline', False) for caps in chain_capabilities.values()
    )
    
    # Check if any chains have only basic arbitrage services
    has_basic_chains = any(
        not caps.get('has_pipeline', False) for caps in chain_capabilities.values()
    )
    
    if chain_count == 1:
        # Single chain - use simple mode regardless of sophistication
        return OrchestrationMode.SIMPLE
    elif config.risk_management_enabled or config.cross_chain_arbitrage_enabled:
        # Advanced features requested - use advanced mode
        return OrchestrationMode.ADVANCED
    elif has_pipeline_chains and not has_basic_chains:
        # All chains have pipelines - can use either, prefer simple for efficiency
        return OrchestrationMode.SIMPLE
    elif has_basic_chains and not has_pipeline_chains:
        # All chains are basic - advanced layer can handle them better
        return OrchestrationMode.ADVANCED
    elif chain_count > 2:
        # Multiple chains with mixed capabilities - use advanced mode for coordination
        return OrchestrationMode.ADVANCED
    else:
        # Default to simple for basic multi-chain
        return OrchestrationMode.SIMPLE

def get_layer_description(mode: OrchestrationMode) -> str:
    """Get human-readable description of orchestration layer"""
    descriptions = {
        OrchestrationMode.SIMPLE: "Simple Layer (ArbitrageManager) - Fast, lightweight, single-chain focused",
        OrchestrationMode.ADVANCED: "Advanced Layer (DEXArbitrageOrchestrator) - Full-featured, multi-chain, risk management",
        OrchestrationMode.AUTO: "Auto Selection - Chooses optimal layer based on configuration"
    }
    return descriptions.get(mode, "Unknown mode")

def validate_config(config: OrchestrationConfig) -> Dict[str, Any]:
    """Validate orchestration configuration and return status"""
    issues = []
    recommendations = []
    
    # Check for conflicting settings
    if config.mode == OrchestrationMode.SIMPLE and config.cross_chain_arbitrage_enabled:
        issues.append("Cross-chain arbitrage requires ADVANCED mode")
        recommendations.append("Set ORCHESTRATOR_MODE=advanced or disable cross-chain arbitrage")
    
    if config.mode == OrchestrationMode.SIMPLE and config.risk_management_enabled:
        recommendations.append("Risk management works better with ADVANCED mode")
    
    if config.max_concurrent_executions > 5 and config.mode == OrchestrationMode.SIMPLE:
        recommendations.append("High concurrency works better with ADVANCED mode")
    
    # Check resource requirements
    if config.execution_timeout < 60:
        issues.append("Execution timeout too low - may cause failed trades")
    
    if config.min_profit_threshold_usd < 10:
        recommendations.append("Very low profit threshold may increase gas costs")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "recommendations": recommendations,
        "mode_description": get_layer_description(config.mode)
    }

# Configuration presets
SIMPLE_PRESET = {
    "ORCHESTRATOR_MODE": "simple",
    "MAX_CONCURRENT_EXECUTIONS": "2",
    "MIN_PROFIT_THRESHOLD_USD": "25.0",
    "RISK_MANAGEMENT_ENABLED": "false",
    "CROSS_CHAIN_ARBITRAGE_ENABLED": "false",
    "MEMPOOL_MONITORING_ENABLED": "true"
}

ADVANCED_PRESET = {
    "ORCHESTRATOR_MODE": "advanced",
    "MAX_CONCURRENT_EXECUTIONS": "5",
    "MIN_PROFIT_THRESHOLD_USD": "50.0",
    "RISK_MANAGEMENT_ENABLED": "true",
    "CROSS_CHAIN_ARBITRAGE_ENABLED": "true",
    "MEMPOOL_MONITORING_ENABLED": "true"
}

CONSERVATIVE_PRESET = {
    "ORCHESTRATOR_MODE": "advanced",
    "MAX_CONCURRENT_EXECUTIONS": "1",
    "MIN_PROFIT_THRESHOLD_USD": "100.0",
    "MAX_POSITION_SIZE_USD": "5000.0",
    "RISK_MANAGEMENT_ENABLED": "true",
    "CROSS_CHAIN_ARBITRAGE_ENABLED": "false"
}

def apply_preset(preset_name: str) -> Dict[str, str]:
    """Apply a configuration preset"""
    presets = {
        "simple": SIMPLE_PRESET,
        "advanced": ADVANCED_PRESET,
        "conservative": CONSERVATIVE_PRESET
    }
    
    preset = presets.get(preset_name.lower())
    if not preset:
        raise ValueError(f"Unknown preset: {preset_name}")
    
    # Apply to environment
    for key, value in preset.items():
        os.environ[key] = value
    
    return preset
