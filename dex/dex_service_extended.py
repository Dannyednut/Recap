"""
Extended methods for MultiChainDEXService to support dual orchestration layers
"""

async def _initialize_simple_layer(self) -> bool:
    """Initialize the simple orchestration layer"""
    try:
        logger.info("Initializing Simple Layer (ArbitrageManager)...")
        self.manager = ArbitrageManager(self.config)
        
        if not await self.manager.initialize():
            logger.error("Failed to initialize arbitrage manager")
            return False
        
        self.is_initialized = True
        logger.info("Simple layer initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing simple layer: {e}")
        return False

async def _start_simple_layer(self) -> bool:
    """Start the simple orchestration layer"""
    if not await self.manager.start():
        logger.error("Failed to start arbitrage manager")
        return False
    return True

async def _stop_simple_layer(self) -> bool:
    """Stop the simple orchestration layer"""
    if self.manager:
        await self.manager.stop()
    return True

async def _initialize_advanced_layer(self) -> bool:
    """Initialize the advanced orchestration layer"""
    try:
        logger.info("Initializing Advanced Layer (DEXArbitrageOrchestrator)...")
        self.orchestrator = DEXArbitrageOrchestrator()
        
        # Configure orchestrator with our settings
        self.orchestrator.config.update({
            "max_concurrent_executions": self.orchestration_config.max_concurrent_executions,
            "min_profit_threshold_usd": self.orchestration_config.min_profit_threshold_usd,
            "max_position_size_usd": self.orchestration_config.max_position_size_usd,
            "execution_timeout": self.orchestration_config.execution_timeout,
            "health_check_interval": self.orchestration_config.health_check_interval
        })
        
        await self.orchestrator.initialize()
        
        self.is_initialized = True
        logger.info("Advanced layer initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing advanced layer: {e}")
        return False

async def _start_advanced_layer(self) -> bool:
    """Start the advanced orchestration layer"""
    # The orchestrator starts automatically during initialization
    return True

async def _stop_advanced_layer(self) -> bool:
    """Stop the advanced orchestration layer"""
    if self.orchestrator:
        await self.orchestrator.shutdown()
    return True

async def get_orchestration_status(self) -> Dict[str, Any]:
    """Get detailed orchestration layer status"""
    base_status = {
        "orchestration_mode": self.orchestration_mode.value if self.orchestration_mode else "unknown",
        "layer_description": self.orchestration_config.__dict__ if self.orchestration_config else {},
        "initialized": self.is_initialized,
        "running": self.is_running
    }
    
    if self.orchestration_mode == OrchestrationMode.SIMPLE and self.manager:
        # Get simple layer status
        base_status.update({
            "active_chains": self.manager.get_active_chains(),
            "stats": await self.manager.get_stats() if self.is_running else {}
        })
    elif self.orchestration_mode == OrchestrationMode.ADVANCED and self.orchestrator:
        # Get advanced layer status
        try:
            system_health = await self.orchestrator.get_system_status()
            base_status.update({
                "system_health": system_health.__dict__,
                "active_chains": system_health.active_chains,
                "inactive_chains": system_health.inactive_chains,
                "total_opportunities": system_health.total_opportunities,
                "execution_success_rate": system_health.execution_success_rate
            })
        except Exception as e:
            base_status["orchestrator_error"] = str(e)
    
    return base_status

async def switch_orchestration_mode(self, new_mode: str) -> bool:
    """Switch orchestration mode at runtime"""
    try:
        # Parse new mode
        try:
            target_mode = OrchestrationMode(new_mode.lower())
        except ValueError:
            logger.error(f"Invalid orchestration mode: {new_mode}")
            return False
        
        if target_mode == self.orchestration_mode:
            logger.info(f"Already using {target_mode.value} mode")
            return True
        
        logger.info(f"Switching from {self.orchestration_mode.value} to {target_mode.value} mode")
        
        # Stop current layer
        was_running = self.is_running
        if was_running:
            await self.stop()
        
        # Update mode
        self.orchestration_mode = target_mode
        
        # Initialize new layer
        if target_mode == OrchestrationMode.SIMPLE:
            success = await self._initialize_simple_layer()
        else:
            success = await self._initialize_advanced_layer()
        
        if not success:
            logger.error(f"Failed to initialize {target_mode.value} layer")
            return False
        
        # Restart if it was running
        if was_running:
            await self.start()
        
        logger.info(f"Successfully switched to {target_mode.value} mode")
        return True
        
    except Exception as e:
        logger.error(f"Error switching orchestration mode: {e}")
        return False

# Add these methods to MultiChainDEXService class
MultiChainDEXService._initialize_simple_layer = _initialize_simple_layer
MultiChainDEXService._start_simple_layer = _start_simple_layer
MultiChainDEXService._stop_simple_layer = _stop_simple_layer
MultiChainDEXService._initialize_advanced_layer = _initialize_advanced_layer
MultiChainDEXService._start_advanced_layer = _start_advanced_layer
MultiChainDEXService._stop_advanced_layer = _stop_advanced_layer
MultiChainDEXService.get_orchestration_status = get_orchestration_status
MultiChainDEXService.switch_orchestration_mode = switch_orchestration_mode
