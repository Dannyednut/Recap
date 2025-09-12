import asyncio
from dataclasses import asdict
from quart import Quart, jsonify, request
from datetime import datetime

# Custom imports
from cex.config import Config
from cex.models import TradeResult
from cex.arbitrage import ArbitrageApp, logger
from shared_telegram_manager import telegram_manager

# DEX imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'dex'))

# Import the multi-chain DEX service
try:
    from dex.dex_service import MultiChainDEXService
    DEX_AVAILABLE = True
except ImportError as e:
    logger.warning(f"DEX imports failed: {e}")
    DEX_AVAILABLE = False


# --- Quart App and Global App Instance ---
app = Quart(__name__)
arbitrage_app = ArbitrageApp(Config())

# Global DEX service
multi_chain_dex_service = None

# Simple API key auth header name
API_KEY_HEADER = "X-API-KEY"


@app.route('/')
async def index():
    return "Hello there, I'm busy working"


@app.route('/balances', methods=['GET'])
async def get_balances():
    cex_balances = arbitrage_app.engine.account_balances or {}
    
    # Get DEX balances if available
    dex_balances = {}
    if multi_chain_dex_service:
        try:
            dex_status = await multi_chain_dex_service.get_status()
            dex_balances = dex_status.get("chains", {})
        except Exception as e:
            logger.warning(f"Failed to get DEX balances: {e}")
    
    return jsonify({
        "cex": cex_balances,
        "dex": dex_balances,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/execute', methods=['POST'])
async def execute_trade_endpoint():
    # Require API key header for API-triggered execution
    api_key = request.headers.get(API_KEY_HEADER) or request.args.get('api_key')
    if not api_key:
        return jsonify({"status": "error", "message": "API key required"}), 401
    
    data = await request.get_json()
    if not data or not all(k in data for k in ['opportunity_id', 'type', 'strategy']):
        return jsonify({"status": "error", "message": "Missing required parameters"}), 400

    # Pass the auth key into execute_trade_logic which performs auth validation
    try:
        result = await arbitrage_app.execute_trade_logic(data, auth_key=api_key)
        status_code = 200 if result.status == 'success' else 400

        if 'chat_id' in data and arbitrage_app.notifier:
            await arbitrage_app.notifier.send_trade_result(int(data['chat_id']), result)

        return jsonify(asdict(result)), status_code

    except asyncio.TimeoutError:
        return jsonify({"status": "error", "message": "Trade execution timed out."}), 504
    except Exception as e:
        logger.error(f"API endpoint error: {e}")
        return jsonify({"status": "error", "message": "An internal server error occurred."}), 500


# DISABLED: Insecure telegram webhook - requires signature verification
# @app.route('/telegram-webhook', methods=['POST'])
async def _disabled_telegram_webhook():
    data = await request.get_json()

    if 'callback_query' in data:
        callback = data['callback_query']
        chat_id = callback['message']['chat']['id']
        if str(chat_id) != str(Config.TELEGRAM_CHAT_ID):
            return jsonify(ok=True)  # ignore non-whitelisted chats

        data_str = callback['data']  # expecting format like "exec|instant|opid"
        parts = data_str.split('|')
        if len(parts) != 3:
            return jsonify(ok=True)

        action, subtype, opportunity_id = parts
        if action == "exec":
            exec_payload = {
                "type": "cross" if subtype in ("instant", "transfer") else "triangular",
                "strategy": subtype,
                "opportunity_id": opportunity_id,
                "chat_id": chat_id
            }
            try:
                result = await arbitrage_app.execute_trade_logic(exec_payload, auth_key=Config.BASE44_APP_TOKEN)
                if result.status != "success":
                    logger.error(f"Trade execution from Telegram button failed: {result.message}")
                    result = TradeResult("error", f"Trade execution failed: {result.message}")
            except Exception as e:
                logger.error(f"Error executing trade from Telegram button: {e}")
                result = TradeResult("error", "Failed to execute trade from Telegram button.")

            if arbitrage_app.notifier:
                await arbitrage_app.notifier.send_trade_result(chat_id, result)

    return jsonify(ok=True)


@app.route('/dex/status', methods=['GET'])
async def get_dex_status():
    """Get status of the DEX service"""
    if not multi_chain_dex_service:
        return jsonify({"status": "unavailable", "message": "DEX service not available"}), 503
    
    try:
        status = await multi_chain_dex_service.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting DEX status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/dex/opportunities', methods=['GET'])
async def get_dex_opportunities():
    """Get current DEX arbitrage opportunities"""
    if not multi_chain_dex_service:
        return jsonify({"status": "unavailable", "message": "DEX service not available"}), 503
    
    try:
        chain_id = request.args.get('chain_id')
        opportunities = await multi_chain_dex_service.get_opportunities(chain_id)
        return jsonify({
            "status": "success",
            "opportunities": opportunities,
            "count": len(opportunities),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting DEX opportunities: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/dex/execute', methods=['POST'])
async def execute_dex_opportunity():
    """Execute a DEX arbitrage opportunity"""
    # Require API key header for API-triggered execution
    api_key = request.headers.get(API_KEY_HEADER) or request.args.get('api_key')
    if not api_key:
        return jsonify({"status": "error", "message": "API key required"}), 401
    
    if not multi_chain_dex_service:
        return jsonify({"status": "unavailable", "message": "DEX service not available"}), 503
    
    try:
        data = await request.get_json()
        if not data or not all(k in data for k in ['opportunity_id', 'chain_id']):
            return jsonify({"status": "error", "message": "Missing required parameters"}), 400
        
        opportunity_id = data['opportunity_id']
        chain_id = data['chain_id']
        
        result = await multi_chain_dex_service.execute_opportunity(opportunity_id, chain_id)
        status_code = 200 if result.get('status') == 'success' else 400
        
        return jsonify(result), status_code
    
    except asyncio.TimeoutError:
        return jsonify({"status": "error", "message": "Execution timed out"}), 504
    except Exception as e:
        logger.error(f"Error executing DEX opportunity: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/dex/chains', methods=['GET'])
async def get_dex_chains():
    """Get supported and active chains"""
    if not multi_chain_dex_service:
        return jsonify({"status": "unavailable", "message": "DEX service not available"}), 503
    
    try:
        supported_chains = await multi_chain_dex_service.get_supported_chains()
        status = await multi_chain_dex_service.get_status()
        active_chains = status.get("active_chains", [])
        
        return jsonify({
            "status": "success",
            "supported_chains": supported_chains,
            "active_chains": active_chains
        })
    except Exception as e:
        logger.error(f"Error getting DEX chains: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/dex/chain/<chain_id>', methods=['GET'])
async def get_dex_chain_status(chain_id):
    """Get status of a specific chain"""
    if not multi_chain_dex_service:
        return jsonify({"status": "unavailable", "message": "DEX service not available"}), 503
    
    try:
        status = await multi_chain_dex_service.get_status()
        chains = status.get("chains", {})
        
        if chain_id not in chains:
            return jsonify({"status": "error", "message": f"Chain {chain_id} not found"}), 404
        
        return jsonify({
            "status": "success",
            "chain": chains[chain_id]
        })
    except Exception as e:
        logger.error(f"Error getting chain status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/system/status', methods=['GET'])
async def get_system_status():
    """Get comprehensive system status"""
    cex_status = {
        "running": True,
        "exchanges": len(arbitrage_app.engine.exchanges),
        "balances_loaded": bool(arbitrage_app.engine.account_balances)
    }
    
    dex_status = {"initialized": False, "available": DEX_AVAILABLE}
    if multi_chain_dex_service:
        try:
            dex_status = await multi_chain_dex_service.get_status()
            dex_status["initialized"] = True
        except Exception as e:
            dex_status = {"error": str(e)}
    
    return jsonify({
        "cex": cex_status,
        "dex": dex_status,
        "timestamp": datetime.now().isoformat()
    })


# --- Main Entry Point ---
if __name__ == "__main__":

    async def main():
        global multi_chain_dex_service
        try:
            # Initialize DEX system
            if DEX_AVAILABLE:
                logger.info("Initializing Multi-Chain DEX service...")
                try:
                    multi_chain_dex_service = MultiChainDEXService()
                    await multi_chain_dex_service.initialize()
                    logger.info("Multi-Chain DEX service initialized successfully")
                except Exception as e:
                    logger.warning(f"Multi-Chain DEX initialization failed (continuing with CEX only): {e}")
                    multi_chain_dex_service = None
            
            # Start the CEX scanner tasks
            scanner_task = asyncio.create_task(arbitrage_app.run_scanners())
            
            # Start DEX service if available
            dex_task = None
            if multi_chain_dex_service:
                dex_task = asyncio.create_task(multi_chain_dex_service.start())
                logger.info("Started Multi-Chain DEX service")
            
            # Start Quart API server and wait for all services
            if dex_task:
                await asyncio.gather(
                    app.run_task(host=Config.FLASK_HOST, port=Config.FLASK_PORT),
                    scanner_task,
                    dex_task
                )
            else:
                await app.run_task(host=Config.FLASK_HOST, port=Config.FLASK_PORT)
                await scanner_task
        except KeyboardInterrupt:
            logger.info("Shutdown signal received. Exiting.")
        finally:
            # Shutdown both systems
            await arbitrage_app.engine.stop()
            if multi_chain_dex_service:
                try:
                    await multi_chain_dex_service.stop()
                except Exception as e:
                    logger.warning(f"Error stopping Multi-Chain DEX service: {e}")
            logger.info("Application shut down gracefully.")

    asyncio.run(main())


async def startup():
    """Startup tasks"""
    # Initialize shared Telegram manager first
    if telegram_manager.is_available():
        logger.info("Starting shared Telegram bot manager...")
        try:
            # Start the shared Telegram bot polling
            asyncio.create_task(telegram_manager.start_polling())
            logger.info("Shared Telegram bot manager started successfully")
        except Exception as e:
            logger.error(f"Error starting Telegram manager: {e}")
    else:
        logger.warning("Telegram manager not available - notifications disabled")
    
    # Start CEX arbitrage
    await arbitrage_app.startup()
    
    # Start DEX arbitrage if available
    global multi_chain_dex_service
    if DEX_AVAILABLE:
        try:
            multi_chain_dex_service = MultiChainDEXService()
            if await multi_chain_dex_service.initialize():
                await multi_chain_dex_service.start()
                logger.info("DEX service started successfully")
            else:
                logger.error("Failed to initialize DEX service")
        except Exception as e:
            logger.error(f"Error starting DEX service: {e}")


async def shutdown():
    """Shutdown tasks"""
    # Stop shared Telegram manager
    try:
        await telegram_manager.close()
        logger.info("Shared Telegram manager stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping Telegram manager: {e}")
    
    # Stop CEX arbitrage
    await arbitrage_app.shutdown()
    
    # Stop DEX arbitrage if available
    global multi_chain_dex_service
    if multi_chain_dex_service:
        try:
            await multi_chain_dex_service.stop()
            logger.info("DEX service stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping DEX service: {e}")


@app.before_serving
async def before_serving():
    await startup()


@app.after_serving
async def after_serving():
    await shutdown()
