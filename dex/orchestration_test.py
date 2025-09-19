#!/usr/bin/env python3
"""
Test script for orchestration layer switching functionality
"""
import asyncio
import os
import sys
import logging

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from dex.dex_service import MultiChainDEXService
from dex.shared.orchestration_config import (
    OrchestrationMode, 
    get_orchestration_config,
    apply_preset,
    validate_config
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_orchestration_layers():
    """Test orchestration layer switching"""
    
    print("=== ArbitrageWise Orchestration Layer Test ===\n")
    
    # Test configuration validation
    print("1. Testing Configuration Validation...")
    config = get_orchestration_config()
    validation = validate_config(config)
    print(f"   Config Valid: {validation['valid']}")
    print(f"   Mode: {validation['mode_description']}")
    if validation['recommendations']:
        for rec in validation['recommendations']:
            print(f"   Recommendation: {rec}")
    print()
    
    # Test preset application
    print("2. Testing Configuration Presets...")
    presets = ["simple", "advanced", "conservative"]
    for preset in presets:
        try:
            preset_config = apply_preset(preset)
            print(f"   ✓ {preset.title()} preset applied")
            print(f"     Mode: {preset_config.get('ORCHESTRATOR_MODE')}")
            print(f"     Concurrent Executions: {preset_config.get('MAX_CONCURRENT_EXECUTIONS')}")
        except Exception as e:
            print(f"   ✗ {preset.title()} preset failed: {e}")
    print()
    
    # Test DEX service initialization
    print("3. Testing DEX Service Initialization...")
    
    # Test with simple mode
    os.environ['ORCHESTRATOR_MODE'] = 'simple'
    try:
        dex_service = MultiChainDEXService()
        success = await dex_service.initialize()
        if success:
            status = await dex_service.get_orchestration_status()
            print(f"   ✓ Simple layer initialized")
            print(f"     Mode: {status.get('orchestration_mode')}")
            print(f"     Running: {status.get('running')}")
            await dex_service.stop()
        else:
            print(f"   ✗ Simple layer initialization failed")
    except Exception as e:
        print(f"   ✗ Simple layer error: {e}")
    
    # Test with advanced mode
    os.environ['ORCHESTRATOR_MODE'] = 'advanced'
    try:
        dex_service = MultiChainDEXService()
        success = await dex_service.initialize()
        if success:
            status = await dex_service.get_orchestration_status()
            print(f"   ✓ Advanced layer initialized")
            print(f"     Mode: {status.get('orchestration_mode')}")
            print(f"     Running: {status.get('running')}")
            await dex_service.stop()
        else:
            print(f"   ✗ Advanced layer initialization failed")
    except Exception as e:
        print(f"   ✗ Advanced layer error: {e}")
    
    # Test auto mode
    os.environ['ORCHESTRATOR_MODE'] = 'auto'
    try:
        dex_service = MultiChainDEXService()
        success = await dex_service.initialize()
        if success:
            status = await dex_service.get_orchestration_status()
            print(f"   ✓ Auto mode selected: {status.get('orchestration_mode')}")
            await dex_service.stop()
        else:
            print(f"   ✗ Auto mode initialization failed")
    except Exception as e:
        print(f"   ✗ Auto mode error: {e}")
    
    print()
    
    # Test runtime switching
    print("4. Testing Runtime Mode Switching...")
    try:
        dex_service = MultiChainDEXService()
        await dex_service.initialize()
        
        initial_status = await dex_service.get_orchestration_status()
        initial_mode = initial_status.get('orchestration_mode')
        print(f"   Initial mode: {initial_mode}")
        
        # Switch to opposite mode
        target_mode = 'advanced' if initial_mode == 'simple' else 'simple'
        success = await dex_service.switch_orchestration_mode(target_mode)
        
        if success:
            new_status = await dex_service.get_orchestration_status()
            new_mode = new_status.get('orchestration_mode')
            print(f"   ✓ Successfully switched to: {new_mode}")
        else:
            print(f"   ✗ Failed to switch to {target_mode}")
        
        await dex_service.stop()
        
    except Exception as e:
        print(f"   ✗ Runtime switching error: {e}")
    
    print()
    print("=== Test Complete ===")

def print_usage():
    """Print usage information"""
    print("""
ArbitrageWise Orchestration Layer Configuration

Environment Variables:
  ORCHESTRATOR_MODE=simple|advanced|auto
    - simple: Lightweight ArbitrageManager
    - advanced: Full DEXArbitrageOrchestrator with risk management
    - auto: Automatically select optimal layer

  MAX_CONCURRENT_EXECUTIONS=3
  MIN_PROFIT_THRESHOLD_USD=50.0
  MAX_POSITION_SIZE_USD=10000.0
  EXECUTION_TIMEOUT=300
  HEALTH_CHECK_INTERVAL=30
  RISK_MANAGEMENT_ENABLED=true
  CROSS_CHAIN_ARBITRAGE_ENABLED=false
  MEMPOOL_MONITORING_ENABLED=true

API Endpoints:
  GET /dex/orchestration/status - Get orchestration layer status
  POST /dex/orchestration/switch - Switch orchestration mode
    Body: {"mode": "simple|advanced"}

Examples:
  # Use simple layer
  export ORCHESTRATOR_MODE=simple
  
  # Use advanced layer with risk management
  export ORCHESTRATOR_MODE=advanced
  export RISK_MANAGEMENT_ENABLED=true
  
  # Auto-select optimal layer
  export ORCHESTRATOR_MODE=auto
  
  # Switch at runtime via API
  curl -X POST http://localhost:5001/dex/orchestration/switch \\
    -H "Content-Type: application/json" \\
    -d '{"mode": "advanced"}'
""")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print_usage()
    else:
        asyncio.run(test_orchestration_layers())
