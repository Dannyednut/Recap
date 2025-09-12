"""
Simple test script to check blockchain connections individually
"""
import asyncio
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ethereum_connection():
    """Test Ethereum connection"""
    try:
        from ethereum_service.config import EthereumConfig
        from ethereum_service.engine import EthereumEngine
        
        config = EthereumConfig()
        engine = EthereumEngine(config)
        
        logger.info(f"Testing Ethereum connection to: {config.RPC_URL[:50]}...")
        await engine.initialize()
        
        block_number = await engine.get_block_number()
        logger.info(f"✓ Ethereum connected - Block: {block_number}")
        
        if engine.wallet_address:
            logger.info(f"✓ Wallet: {engine.wallet_address}")
            
        return True, f"Block: {block_number}"
        
    except Exception as e:
        logger.error(f"✗ Ethereum failed: {e}")
        return False, str(e)

async def test_bsc_connection():
    """Test BSC connection"""
    try:
        from bsc_service.config import BSCConfig
        from bsc_service.engine import BSCEngine
        
        config = BSCConfig()
        engine = BSCEngine(config)
        
        logger.info(f"Testing BSC connection to: {config.RPC_URL[:50]}...")
        await engine.initialize()
        
        block_number = await engine.get_block_number()
        logger.info(f"✓ BSC connected - Block: {block_number}")
        
        if engine.wallet_address:
            logger.info(f"✓ Wallet: {engine.wallet_address}")
            
        return True, f"Block: {block_number}"
        
    except Exception as e:
        logger.error(f"✗ BSC failed: {e}")
        return False, str(e)

async def test_polygon_connection():
    """Test Polygon connection"""
    try:
        from polygon_service.config import PolygonConfig
        from polygon_service.engine import PolygonEngine
        
        config = PolygonConfig()
        engine = PolygonEngine(config)
        
        logger.info(f"Testing Polygon connection to: {config.RPC_URL[:50]}...")
        await engine.initialize()
        
        block_number = await engine.get_block_number()
        logger.info(f"✓ Polygon connected - Block: {block_number}")
        
        if engine.wallet_address:
            logger.info(f"✓ Wallet: {engine.wallet_address}")
            
        return True, f"Block: {block_number}"
        
    except Exception as e:
        logger.error(f"✗ Polygon failed: {e}")
        return False, str(e)

async def test_solana_connection():
    """Test Solana connection"""
    try:
        from solana_service.config import SolanaConfig
        from solana_service.engine import SolanaEngine
        
        config = SolanaConfig()
        engine = SolanaEngine(config)
        
        logger.info(f"Testing Solana connection to: {config.RPC_URL[:50]}...")
        await engine.initialize()
        
        # For Solana, we'll try to get slot instead of block
        if hasattr(engine, 'get_slot'):
            slot = await engine.get_slot()
            logger.info(f"✓ Solana connected - Slot: {slot}")
            return True, f"Slot: {slot}"
        else:
            logger.info(f"✓ Solana client initialized")
            return True, "Initialized"
        
    except Exception as e:
        logger.error(f"✗ Solana failed: {e}")
        return False, str(e)

async def main():
    """Test all blockchain connections"""
    print("\n=== Blockchain Connection Test ===")
    print(f"Time: {datetime.now()}")
    
    # Check if secrets are available
    secrets_status = {
        "ETH_RPC_URL": bool(os.getenv("ETH_RPC_URL")),
        "ETH_PRIVATE_KEY": bool(os.getenv("ETH_PRIVATE_KEY")),
        "BSC_RPC_URL": bool(os.getenv("BSC_RPC_URL")),
        "BSC_PRIVATE_KEY": bool(os.getenv("BSC_PRIVATE_KEY")),
        "POLYGON_RPC_URL": bool(os.getenv("POLYGON_RPC_URL")),
        "POLYGON_PRIVATE_KEY": bool(os.getenv("POLYGON_PRIVATE_KEY")),
        "SOLANA_RPC_URL": bool(os.getenv("SOLANA_RPC_URL")),
        "SOLANA_PRIVATE_KEY": bool(os.getenv("SOLANA_PRIVATE_KEY")),
    }
    
    print("\n=== Secret Status ===")
    for key, status in secrets_status.items():
        print(f"{key:20}: {'✓' if status else '✗'}")
    
    # Test connections
    tests = [
        ("Ethereum", test_ethereum_connection),
        ("BSC", test_bsc_connection), 
        ("Polygon", test_polygon_connection),
        ("Solana", test_solana_connection)
    ]
    
    results = {}
    print("\n=== Connection Tests ===")
    
    for chain_name, test_func in tests:
        try:
            success, info = await test_func()
            results[chain_name] = {"success": success, "info": info}
            status = "✓" if success else "✗"
            print(f"{chain_name:10}: {status} {info}")
        except Exception as e:
            results[chain_name] = {"success": False, "info": f"Test failed: {e}"}
            print(f"{chain_name:10}: ✗ Test failed: {e}")
    
    # Summary
    successful = len([r for r in results.values() if r["success"]])
    total = len(results)
    
    print(f"\n=== Summary ===")
    print(f"Connected: {successful}/{total} chains")
    
    if successful > 0:
        print("✓ Ready to proceed with DEX system integration")
    else:
        print("✗ No connections successful - check RPC URLs and network access")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())