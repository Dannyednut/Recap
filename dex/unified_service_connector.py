"""
Unified Service Connector for All Blockchain Services
Initializes and tests connections across Ethereum, BSC, Polygon, and Solana
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# Import all chain services
import sys
import os
sys.path.append(os.path.dirname(__file__))

from ethereum_service.service import EthereumArbitrageService
from bsc_service.arbitrage import BSCArbitrageService
from polygon_service.arbitrage import PolygonArbitrageService  
from solana_service.arbitrage import SolanaArbitrageService

# Import orchestrator
from orchestrator.main import DEXArbitrageOrchestrator

logger = logging.getLogger(__name__)

@dataclass
class ChainConnectionStatus:
    chain: str
    connected: bool
    block_number: Optional[int] = None
    wallet_address: Optional[str] = None
    error: Optional[str] = None
    rpc_url: Optional[str] = None
    last_check: Optional[datetime] = None

class UnifiedServiceConnector:
    """Unified connector for all blockchain arbitrage services"""
    
    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.connection_status: Dict[str, ChainConnectionStatus] = {}
        self.orchestrator: Optional[DEXArbitrageOrchestrator] = None
        self.is_initialized = False
        
    async def initialize_all_services(self) -> Dict[str, ChainConnectionStatus]:
        """Initialize and test connections for all blockchain services"""
        logger.info("Initializing all blockchain services...")
        
        # Define services to initialize
        services_config = [
            ("ethereum", EthereumArbitrageService),
            ("bsc", BSCArbitrageService), 
            ("polygon", PolygonArbitrageService),
            ("solana", SolanaArbitrageService)
        ]
        
        # Initialize each service
        for chain_name, service_class in services_config:
            status = await self._initialize_chain_service(chain_name, service_class)
            self.connection_status[chain_name] = status
            
        # Initialize orchestrator if any services are connected
        connected_services = [name for name, status in self.connection_status.items() if status.connected]
        if connected_services:
            try:
                await self._initialize_orchestrator()
                logger.info(f"Orchestrator initialized with {len(connected_services)} connected chains")
            except Exception as e:
                logger.error(f"Failed to initialize orchestrator: {e}")
        
        self.is_initialized = True
        return self.connection_status
    
    async def _initialize_chain_service(self, chain_name: str, service_class) -> ChainConnectionStatus:
        """Initialize a single blockchain service"""
        logger.info(f"Initializing {chain_name} service...")
        
        status = ChainConnectionStatus(
            chain=chain_name,
            connected=False,
            last_check=datetime.now()
        )
        
        try:
            # Create service instance
            service = service_class()
            status.rpc_url = getattr(service.config, 'RPC_URL', 'Unknown')
            status.wallet_address = getattr(service.config, 'WALLET_ADDRESS', None)
            
            # Test basic configuration
            if hasattr(service.config, 'validate'):
                try:
                    service.config.validate()
                except Exception as e:
                    status.error = f"Configuration validation failed: {e}"
                    logger.warning(f"{chain_name} config validation failed: {e}")
                    return status
            
            # Attempt to initialize the service
            await service.initialize()
            
            # Test connection and get block info
            if hasattr(service.engine, 'get_block_number'):
                try:
                    block_number = await asyncio.wait_for(
                        service.engine.get_block_number(), 
                        timeout=10.0
                    )
                    status.block_number = block_number
                    status.connected = True
                    self.services[chain_name] = service
                    logger.info(f"{chain_name} connected successfully - Block: {block_number}")
                    
                except asyncio.TimeoutError:
                    status.error = "Connection timeout - RPC endpoint may be slow"
                    logger.warning(f"{chain_name} connection timeout")
                except Exception as e:
                    status.error = f"Block query failed: {e}"
                    logger.warning(f"{chain_name} block query failed: {e}")
            else:
                # For services without block number method, just mark as connected
                status.connected = True
                self.services[chain_name] = service
                logger.info(f"{chain_name} service initialized (no block query available)")
            
        except Exception as e:
            status.error = f"Service initialization failed: {e}"
            logger.error(f"Failed to initialize {chain_name}: {e}")
        
        return status
    
    async def _initialize_orchestrator(self):
        """Initialize the DEX orchestrator with connected services"""
        self.orchestrator = DEXArbitrageOrchestrator()
        await self.orchestrator.initialize()
        
        # Register connected services with orchestrator
        for chain_name, service in self.services.items():
            if hasattr(self.orchestrator, 'service_registry'):
                await self.orchestrator.service_registry.register_service(chain_name, service)
    
    async def test_all_connections(self) -> Dict[str, ChainConnectionStatus]:
        """Test connections for all initialized services"""
        logger.info("Testing all blockchain connections...")
        
        for chain_name, service in self.services.items():
            status = self.connection_status.get(chain_name)
            if not status:
                continue
                
            try:
                # Update connection status
                if hasattr(service.engine, 'get_block_number'):
                    block_number = await asyncio.wait_for(
                        service.engine.get_block_number(), 
                        timeout=10.0
                    )
                    status.block_number = block_number
                    status.connected = True
                    status.error = None
                    logger.info(f"{chain_name} connection test passed - Block: {block_number}")
                else:
                    # Service is available but no block query method
                    status.connected = True
                    status.error = None
                    logger.info(f"{chain_name} connection test passed")
                    
            except Exception as e:
                status.connected = False
                status.error = f"Connection test failed: {e}"
                logger.error(f"{chain_name} connection test failed: {e}")
                
            status.last_check = datetime.now()
        
        return self.connection_status
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all services"""
        if not self.is_initialized:
            return {"status": "not_initialized", "services": {}}
        
        service_statuses = {}
        for chain_name, service in self.services.items():
            try:
                if hasattr(service, 'get_status'):
                    service_statuses[chain_name] = await service.get_status()
                else:
                    connection_status = self.connection_status.get(chain_name)
                    service_statuses[chain_name] = {
                        "connected": connection_status.connected if connection_status else False,
                        "error": connection_status.error if connection_status else None,
                        "last_check": connection_status.last_check.isoformat() if connection_status and connection_status.last_check else None
                    }
            except Exception as e:
                service_statuses[chain_name] = {"status": "error", "error": str(e)}
        
        return {
            "status": "initialized",
            "total_services": len(self.services),
            "connected_services": len([s for s in self.connection_status.values() if s.connected]),
            "services": service_statuses,
            "orchestrator_active": self.orchestrator is not None,
            "last_update": datetime.now().isoformat()
        }
    
    async def scan_all_opportunities(self) -> Dict[str, List[Any]]:
        """Scan for arbitrage opportunities across all connected chains"""
        if not self.is_initialized:
            return {}
        
        all_opportunities = {}
        
        for chain_name, service in self.services.items():
            try:
                if hasattr(service, 'scan_opportunities'):
                    opportunities = await service.scan_opportunities()
                    all_opportunities[chain_name] = opportunities
                    logger.info(f"Found {len(opportunities)} opportunities on {chain_name}")
                else:
                    logger.warning(f"{chain_name} service does not support opportunity scanning")
            except Exception as e:
                logger.error(f"Failed to scan opportunities on {chain_name}: {e}")
                all_opportunities[chain_name] = []
        
        return all_opportunities
    
    async def shutdown_all_services(self):
        """Gracefully shutdown all services"""
        logger.info("Shutting down all blockchain services...")
        
        if self.orchestrator:
            try:
                await self.orchestrator.shutdown()
                logger.info("Orchestrator shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down orchestrator: {e}")
        
        for chain_name, service in self.services.items():
            try:
                if hasattr(service, 'stop'):
                    await service.stop()
                elif hasattr(service, 'shutdown'):
                    await service.shutdown()
                logger.info(f"{chain_name} service shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down {chain_name}: {e}")
        
        self.services.clear()
        self.connection_status.clear()
        self.is_initialized = False

# Global connector instance
unified_connector = UnifiedServiceConnector()

async def main():
    """Test the unified connector"""
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Initialize all services
        statuses = await unified_connector.initialize_all_services()
        
        # Print connection results
        print("\n=== Blockchain Connection Results ===")
        for chain, status in statuses.items():
            print(f"{chain.upper():10}: {'✓' if status.connected else '✗'} "
                  f"Block: {status.block_number or 'N/A':>8} "
                  f"{'| ' + status.error if status.error else ''}")
        
        # Test connections
        print("\n=== Testing Connections ===")
        await unified_connector.test_all_connections()
        
        # Get detailed status
        print("\n=== Service Status ===")
        detailed_status = await unified_connector.get_service_status()
        print(f"Connected Services: {detailed_status['connected_services']}/{detailed_status['total_services']}")
        
        # Keep running for testing
        print("\n=== System Ready ===")
        print("Press Ctrl+C to shutdown...")
        
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await unified_connector.shutdown_all_services()

if __name__ == "__main__":
    asyncio.run(main())