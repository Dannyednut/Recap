import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)

@dataclass
class ServiceMetadata:
    name: str
    service_type: str
    version: str
    chain_id: int
    capabilities: List[str]
    endpoints: Dict[str, str]
    health_check_url: str
    last_heartbeat: datetime
    status: str

class ServiceRegistry:
    """Registry for managing blockchain microservices"""
    
    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.service_metadata: Dict[str, ServiceMetadata] = {}
        self.service_health: Dict[str, Dict] = {}
        
    async def initialize(self) -> None:
        """Initialize service registry"""
        logger.info("Initializing Service Registry...")
        
        # Start heartbeat monitor
        asyncio.create_task(self._heartbeat_monitor())
        
        logger.info("Service Registry initialized")
    
    async def register_service(
        self, 
        service_name: str, 
        service_instance: Any,
        metadata: Optional[ServiceMetadata] = None
    ) -> None:
        """Register a blockchain service"""
        try:
            self.services[service_name] = service_instance
            
            if metadata:
                self.service_metadata[service_name] = metadata
            else:
                # Create default metadata
                self.service_metadata[service_name] = ServiceMetadata(
                    name=service_name,
                    service_type="blockchain_service",
                    version="1.0.0",
                    chain_id=getattr(service_instance, 'chain_id', 1),
                    capabilities=await self._discover_capabilities(service_instance),
                    endpoints={},
                    health_check_url="",
                    last_heartbeat=datetime.now(),
                    status="registered"
                )
            
            # Initialize health tracking
            self.service_health[service_name] = {
                "status": "healthy",
                "last_check": datetime.now(),
                "response_time": 0.0,
                "error_count": 0,
                "uptime": 100.0
            }
            
            logger.info(f"Registered service: {service_name}")
            
        except Exception as e:
            logger.error(f"Failed to register service {service_name}: {e}")
            raise
    
    async def _discover_capabilities(self, service_instance: Any) -> List[str]:
        """Discover service capabilities"""
        capabilities = []
        
        # Check for common arbitrage capabilities
        if hasattr(service_instance, 'cross_arbitrage'):
            capabilities.append("cross_arbitrage")
        
        if hasattr(service_instance, 'triangular_arbitrage'):
            capabilities.append("triangular_arbitrage")
        
        if hasattr(service_instance, 'flash_loan'):
            capabilities.append("flash_loan")
        
        if hasattr(service_instance, 'mempool_monitor'):
            capabilities.append("mempool_monitoring")
        
        return capabilities
    
    async def get_service(self, service_name: str) -> Optional[Any]:
        """Get a registered service instance"""
        return self.services.get(service_name)
    
    async def get_services_by_capability(self, capability: str) -> List[str]:
        """Get services that support a specific capability"""
        matching_services = []
        
        for service_name, metadata in self.service_metadata.items():
            if capability in metadata.capabilities:
                matching_services.append(service_name)
        
        return matching_services
    
    async def get_healthy_services(self) -> List[str]:
        """Get list of currently healthy services"""
        healthy_services = []
        
        for service_name, health in self.service_health.items():
            if health["status"] == "healthy":
                healthy_services.append(service_name)
        
        return healthy_services
    
    async def update_service_health(
        self, 
        service_name: str, 
        health_data: Dict[str, Any]
    ) -> None:
        """Update service health information"""
        if service_name in self.service_health:
            self.service_health[service_name].update(health_data)
            self.service_health[service_name]["last_check"] = datetime.now()
    
    async def _heartbeat_monitor(self) -> None:
        """Monitor service heartbeats"""
        while True:
            try:
                current_time = datetime.now()
                
                for service_name, metadata in self.service_metadata.items():
                    # Check if service is still responsive
                    try:
                        service = self.services.get(service_name)
                        if service and hasattr(service, 'ping'):
                            start_time = asyncio.get_event_loop().time()
                            await service.ping()
                            response_time = asyncio.get_event_loop().time() - start_time
                            
                            await self.update_service_health(service_name, {
                                "status": "healthy",
                                "response_time": response_time,
                                "error_count": 0
                            })
                            
                    except Exception as e:
                        logger.warning(f"Heartbeat failed for {service_name}: {e}")
                        
                        # Increment error count
                        health = self.service_health.get(service_name, {})
                        error_count = health.get("error_count", 0) + 1
                        
                        await self.update_service_health(service_name, {
                            "status": "unhealthy" if error_count > 3 else "degraded",
                            "error_count": error_count
                        })
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(60)
    
    async def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Get detailed status for a specific service"""
        if service_name not in self.services:
            return {"error": "Service not found"}
        
        metadata = self.service_metadata.get(service_name, {})
        health = self.service_health.get(service_name, {})
        
        return {
            "name": service_name,
            "metadata": metadata.__dict__ if hasattr(metadata, '__dict__') else metadata,
            "health": health,
            "registered": True
        }
    
    async def get_all_services_status(self) -> Dict[str, Any]:
        """Get status for all registered services"""
        all_status = {}
        
        for service_name in self.services.keys():
            all_status[service_name] = await self.get_service_status(service_name)
        
        return all_status
    
    async def unregister_service(self, service_name: str) -> None:
        """Unregister a service"""
        try:
            if service_name in self.services:
                service = self.services[service_name]
                
                # Try to gracefully shutdown the service
                if hasattr(service, 'shutdown'):
                    await service.shutdown()
                
                del self.services[service_name]
            
            if service_name in self.service_metadata:
                del self.service_metadata[service_name]
            
            if service_name in self.service_health:
                del self.service_health[service_name]
            
            logger.info(f"Unregistered service: {service_name}")
            
        except Exception as e:
            logger.error(f"Error unregistering service {service_name}: {e}")
    
    async def restart_service(self, service_name: str) -> bool:
        """Restart a specific service"""
        try:
            if service_name not in self.services:
                return False
            
            service = self.services[service_name]
            
            # Try to restart the service
            if hasattr(service, 'restart'):
                await service.restart()
            elif hasattr(service, 'shutdown') and hasattr(service, 'initialize'):
                await service.shutdown()
                await service.initialize()
            
            # Reset health status
            await self.update_service_health(service_name, {
                "status": "healthy",
                "error_count": 0,
                "response_time": 0.0
            })
            
            logger.info(f"Restarted service: {service_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart service {service_name}: {e}")
            return False