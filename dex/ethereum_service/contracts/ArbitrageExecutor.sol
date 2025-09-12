// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

// Flash loan interfaces
interface IAavePool {
    function flashLoan(
        address receiverAddress,
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata modes,
        address onBehalfOf,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IBalancerVault {
    function flashLoan(
        address recipient,
        address[] memory tokens,
        uint256[] memory amounts,
        bytes memory userData
    ) external;
}

// Uniswap V2 interfaces
interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
    
    function getAmountsOut(uint amountIn, address[] calldata path)
        external view returns (uint[] memory amounts);
}

// Uniswap V3 interfaces
interface IUniswapV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    
    function exactInputSingle(ExactInputSingleParams calldata params)
        external payable returns (uint256 amountOut);
}

contract ArbitrageExecutor is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;
    
    // Router addresses
    address public constant UNISWAP_V2_ROUTER = 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;
    address public constant UNISWAP_V3_ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
    address public constant SUSHISWAP_ROUTER = 0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F;
    
    // Flash loan providers
    address public constant AAVE_POOL = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2;
    address public constant BALANCER_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    
    // Events
    event ArbitrageExecuted(
        address indexed tokenIn,
        address indexed tokenOut,
        uint256 amountIn,
        uint256 profit,
        string buyDex,
        string sellDex
    );
    
    event FlashLoanExecuted(
        address indexed asset,
        uint256 amount,
        uint256 profit
    );
    
    // Arbitrage parameters
    struct ArbitrageParams {
        address tokenA;
        address tokenB;
        uint256 amountIn;
        address buyRouter;
        address sellRouter;
        uint24 buyFee;      // For V3 pools
        uint24 sellFee;     // For V3 pools
        bool useFlashLoan;
        address flashLoanProvider;
        uint256 minProfit;
    }
    
    // Flash loan callback data
    struct FlashLoanData {
        ArbitrageParams params;
        uint256 flashLoanAmount;
    }
    
    constructor() {}
    
    /**
     * @dev Execute cross-DEX arbitrage with or without flash loan
     */
    function executeArbitrage(ArbitrageParams calldata params) external onlyOwner nonReentrant {
        require(params.tokenA != address(0) && params.tokenB != address(0), "Invalid tokens");
        require(params.amountIn > 0, "Invalid amount");
        
        if (params.useFlashLoan) {
            _executeFlashLoanArbitrage(params);
        } else {
            _executeDirectArbitrage(params);
        }
    }
    
    /**
     * @dev Execute arbitrage with flash loan
     */
    function _executeFlashLoanArbitrage(ArbitrageParams memory params) internal {
        if (params.flashLoanProvider == AAVE_POOL) {
            _executeAaveFlashLoan(params);
        } else if (params.flashLoanProvider == BALANCER_VAULT) {
            _executeBalancerFlashLoan(params);
        } else {
            revert("Unsupported flash loan provider");
        }
    }
    
    /**
     * @dev Execute Aave flash loan
     */
    function _executeAaveFlashLoan(ArbitrageParams memory params) internal {
        address[] memory assets = new address[](1);
        assets[0] = params.tokenA;
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // No debt
        
        FlashLoanData memory flashData = FlashLoanData({
            params: params,
            flashLoanAmount: params.amountIn
        });
        
        IAavePool(AAVE_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            abi.encode(flashData),
            0
        );
    }
    
    /**
     * @dev Execute Balancer flash loan
     */
    function _executeBalancerFlashLoan(ArbitrageParams memory params) internal {
        address[] memory tokens = new address[](1);
        tokens[0] = params.tokenA;
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        FlashLoanData memory flashData = FlashLoanData({
            params: params,
            flashLoanAmount: params.amountIn
        });
        
        IBalancerVault(BALANCER_VAULT).flashLoan(
            address(this),
            tokens,
            amounts,
            abi.encode(flashData)
        );
    }
    
    /**
     * @dev Aave flash loan callback
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == AAVE_POOL, "Unauthorized");
        require(initiator == address(this), "Invalid initiator");
        
        uint256 profit = 0;
        
        // Try to decode as regular arbitrage params
        try this.tryDecodeRegularArbitrage(params) returns (FlashLoanData memory flashData) {
            // Execute regular arbitrage
            profit = _performArbitrageTrade(flashData.params);
        } catch {
            // Try to decode as triangular arbitrage params
            try this.tryDecodeTriangularArbitrage(params) returns (TriangularArbitrageParams memory triangularParams) {
                // Execute triangular arbitrage
                profit = _executeDirectTriangularArbitrage(triangularParams);
            } catch {
                // Try to decode as backrun arbitrage params
                try this.tryDecodeBackrunArbitrage(params) returns (BackrunArbitrageParams memory backrunParams) {
                    // Execute backrun arbitrage
                    profit = _executeDirectBackrunArbitrage(backrunParams);
                } catch {
                    revert("Invalid flash loan parameters");
                }
            }
        }
        
        // Repay flash loan
        uint256 totalRepayment = amounts[0] + premiums[0];
        require(profit > totalRepayment, "Arbitrage not profitable");
        
        IERC20(assets[0]).safeTransfer(AAVE_POOL, totalRepayment);
        
        emit FlashLoanExecuted(assets[0], amounts[0], profit - totalRepayment);
        
        return true;
    }
    
    // Helper functions for decoding flash loan parameters
    function tryDecodeRegularArbitrage(bytes calldata params) external pure returns (FlashLoanData memory) {
        return abi.decode(params, (FlashLoanData));
    }
    
    function tryDecodeTriangularArbitrage(bytes calldata params) external pure returns (TriangularArbitrageParams memory) {
        return abi.decode(params, (TriangularArbitrageParams));
    }
    
    function tryDecodeBackrunArbitrage(bytes calldata params) external pure returns (BackrunArbitrageParams memory) {
        return abi.decode(params, (BackrunArbitrageParams));
    }
    
    /**
     * @dev Balancer flash loan callback
     */
    function receiveFlashLoan(
        address[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external {
        require(msg.sender == BALANCER_VAULT, "Unauthorized");
        
        uint256 profit = 0;
        
        // Try to decode as regular arbitrage params
        try this.tryDecodeRegularArbitrage(userData) returns (FlashLoanData memory flashData) {
            // Execute regular arbitrage
            profit = _performArbitrageTrade(flashData.params);
        } catch {
            // Try to decode as triangular arbitrage params
            try this.tryDecodeTriangularArbitrage(userData) returns (TriangularArbitrageParams memory triangularParams) {
                // Execute triangular arbitrage
                profit = _executeDirectTriangularArbitrage(triangularParams);
            } catch {
                // Try to decode as backrun arbitrage params
                try this.tryDecodeBackrunArbitrage(userData) returns (BackrunArbitrageParams memory backrunParams) {
                    // Execute backrun arbitrage
                    profit = _executeDirectBackrunArbitrage(backrunParams);
                } catch {
                    revert("Invalid flash loan parameters");
                }
            }
        }
        
        // Repay flash loan (Balancer has 0 fees)
        require(profit > 0, "Arbitrage not profitable");
        
        IERC20(tokens[0]).safeTransfer(BALANCER_VAULT, amounts[0]);
        
        emit FlashLoanExecuted(tokens[0], amounts[0], profit);
    }
    
    /**
     * @dev Execute arbitrage without flash loan
     */
    function _executeDirectArbitrage(ArbitrageParams memory params) internal {
        require(IERC20(params.tokenA).balanceOf(address(this)) >= params.amountIn, "Insufficient balance");
        
        uint256 profit = _performArbitrageTrade(params);
        require(profit >= params.minProfit, "Profit below minimum threshold");
    }
    
    /**
     * @dev Perform the actual arbitrage trade
     */
    function _performArbitrageTrade(ArbitrageParams memory params) internal returns (uint256) {
        uint256 initialBalance = IERC20(params.tokenA).balanceOf(address(this));
        
        // Step 1: Buy on cheaper DEX (tokenA -> tokenB)
        uint256 tokenBReceived = _executeTrade(
            params.tokenA,
            params.tokenB,
            params.amountIn,
            params.buyRouter,
            params.buyFee,
            address(this) // Receive tokens in this contract
        );
        
        // Step 2: Sell on expensive DEX (tokenB -> tokenA)
        uint256 tokenAReceived = _executeTrade(
            params.tokenB,
            params.tokenA,
            tokenBReceived,
            params.sellRouter,
            params.sellFee,
            address(this) // Receive tokens in this contract
        );
        
        uint256 finalBalance = IERC20(params.tokenA).balanceOf(address(this));
        uint256 profit = finalBalance > initialBalance ? finalBalance - initialBalance : 0;
        
        emit ArbitrageExecuted(
            params.tokenA,
            params.tokenB,
            params.amountIn,
            profit,
            _getRouterName(params.buyRouter),
            _getRouterName(params.sellRouter)
        );
        
        return profit;
    }
    
    /**
     * @dev Execute trade on specified router with default recipient (this contract)
     */
    function _executeTrade(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        address router,
        uint24 fee
    ) internal returns (uint256) {
        return _executeTrade(tokenIn, tokenOut, amountIn, router, fee, address(this));
    }
    
    /**
     * @dev Execute trade on specified router with custom recipient
     * This overloaded function is necessary for triangular and backrun arbitrage
     */
    function _executeTrade(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        address router,
        uint24 fee,
        address recipient
    ) internal returns (uint256) {
        IERC20(tokenIn).safeApprove(router, amountIn);
        
        if (router == UNISWAP_V3_ROUTER) {
            // Uniswap V3 trade
            IUniswapV3Router.ExactInputSingleParams memory params = IUniswapV3Router.ExactInputSingleParams({
                tokenIn: tokenIn,
                tokenOut: tokenOut,
                fee: fee,
                recipient: recipient,
                deadline: block.timestamp + 300,
                amountIn: amountIn,
                amountOutMinimum: 0,
                sqrtPriceLimitX96: 0
            });
            
            return IUniswapV3Router(router).exactInputSingle(params);
        } else {
            // Uniswap V2 or SushiSwap trade
            address[] memory path = new address[](2);
            path[0] = tokenIn;
            path[1] = tokenOut;
            
            uint[] memory amounts = IUniswapV2Router(router).swapExactTokensForTokens(
                amountIn,
                0, // Accept any amount of tokens out
                path,
                recipient,
                block.timestamp + 300
            );
            
            return amounts[1];
        }
    }
    
    /**
     * @dev Get router name for events
     */
    function _getRouterName(address router) internal pure returns (string memory) {
        if (router == UNISWAP_V2_ROUTER) return "UniswapV2";
        if (router == UNISWAP_V3_ROUTER) return "UniswapV3";
        if (router == SUSHISWAP_ROUTER) return "SushiSwap";
        return "Unknown";
    }
    
    /**
     * @dev Emergency withdraw tokens
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner()).transfer(amount);
        } else {
            IERC20(token).safeTransfer(owner(), amount);
        }
    }
    
    /**
     * @dev Get quote for potential arbitrage
     */
    function getArbitrageQuote(
        address tokenA,
        address tokenB,
        uint256 amountIn,
        address buyRouter,
        address sellRouter,
        uint24 buyFee,
        uint24 sellFee
    ) external view returns (uint256 expectedProfit) {
        // Get amount out from buy router
        uint256 tokenBOut;
        if (buyRouter == UNISWAP_V3_ROUTER) {
            // For V3, we'd need to use the quoter contract
            // Simplified here for demo
            tokenBOut = amountIn; // Placeholder
        } else {
            address[] memory buyPath = new address[](2);
            buyPath[0] = tokenA;
            buyPath[1] = tokenB;
            uint[] memory buyAmounts = IUniswapV2Router(buyRouter).getAmountsOut(amountIn, buyPath);
            tokenBOut = buyAmounts[1];
        }
        
        // Get amount out from sell router
        uint256 tokenAOut;
        if (sellRouter == UNISWAP_V3_ROUTER) {
            // For V3, we'd need to use the quoter contract
            // Simplified here for demo
            tokenAOut = tokenBOut; // Placeholder
        } else {
            address[] memory sellPath = new address[](2);
            sellPath[0] = tokenB;
            sellPath[1] = tokenA;
            uint[] memory sellAmounts = IUniswapV2Router(sellRouter).getAmountsOut(tokenBOut, sellPath);
            tokenAOut = sellAmounts[1];
        }
        
        expectedProfit = tokenAOut > amountIn ? tokenAOut - amountIn : 0;
    }
    
    receive() external payable {}
}

// Add new struct for triangular arbitrage
struct TriangularArbitrageParams {
    address[] path;           // Array of token addresses in the triangular path (must be 3 or 4 tokens)
    address[] routers;        // Array of routers to use for each hop
    uint24[] fees;           // Array of fees for each hop (for Uniswap V3)
    uint256 amountIn;        // Amount of the first token to trade
    uint256 minProfitAmount; // Minimum profit required
    uint8 flashLoanProvider; // Flash loan provider to use
}

// Add new struct for mempool backrun opportunity
struct BackrunArbitrageParams {
    bytes32 targetTxHash;    // Transaction hash to backrun
    address[] path;          // Token path for the backrun
    address[] routers;       // Routers to use
    uint24[] fees;           // Fees for each hop (for Uniswap V3)
    uint256 amountIn;        // Amount to trade
    uint256 minProfitAmount; // Minimum profit required
    uint8 flashLoanProvider; // Flash loan provider
    uint256 maxGasPrice;     // Maximum gas price to use
}

/**
 * @dev Execute triangular arbitrage (e.g., ETH -> USDC -> DAI -> ETH)
 */
function executeTriangularArbitrage(
    TriangularArbitrageParams calldata params
) external onlyOwner nonReentrant returns (uint256 profit) {
    require(params.path.length >= 3, "Invalid path length");
    require(params.path.length == params.routers.length + 1, "Path/routers length mismatch");
    require(params.routers.length == params.fees.length, "Routers/fees length mismatch");
    require(params.path[0] == params.path[params.path.length - 1], "Start/end tokens must match");
    
    // Record starting balance
    address startToken = params.path[0];
    uint256 startBalance = IERC20(startToken).balanceOf(address(this));
    
    if (params.flashLoanProvider > 0) {
        // Execute with flash loan
        return _executeTriangularFlashLoan(params);
    } else {
        // Execute direct triangular trade
        return _executeDirectTriangularArbitrage(params);
    }
}

/**
 * @dev Execute backrun arbitrage after a target transaction
 */
function executeBackrunArbitrage(
    BackrunArbitrageParams calldata params
) external onlyOwner nonReentrant returns (uint256 profit) {
    require(params.path.length >= 2, "Invalid path length");
    require(params.path.length == params.routers.length + 1, "Path/routers length mismatch");
    require(params.routers.length == params.fees.length, "Routers/fees length mismatch");
    
    // This would be implemented to monitor for the target transaction
    // and execute immediately after it
    // For now, we'll just execute the trade directly
    
    if (params.flashLoanProvider > 0) {
        // Execute with flash loan
        return _executeBackrunFlashLoan(params);
    } else {
        // Execute direct backrun trade
        return _executeDirectBackrunArbitrage(params);
    }
}

/**
 * @dev Execute direct triangular arbitrage without flash loan
 */
function _executeDirectTriangularArbitrage(
    TriangularArbitrageParams calldata params
) internal returns (uint256 profit) {
    address startToken = params.path[0];
    uint256 startBalance = IERC20(startToken).balanceOf(address(this));
    
    require(startBalance >= params.amountIn, "Insufficient balance");
    
    // Execute each swap in the path
    uint256 currentAmount = params.amountIn;
    for (uint i = 0; i < params.routers.length; i++) {
        address tokenIn = params.path[i];
        address tokenOut = params.path[i + 1];
        address router = params.routers[i];
        uint24 fee = params.fees[i];
        
        // Approve router to spend token
        IERC20(tokenIn).safeApprove(router, 0);
        IERC20(tokenIn).safeApprove(router, currentAmount);
        
        // Execute the swap with this contract as recipient for all trades except the last one
        // For the last trade, use this contract as recipient to receive the final tokens
        address recipient = address(this);
        currentAmount = _executeTrade(tokenIn, tokenOut, currentAmount, router, fee, recipient);
    }
    
    // Calculate profit
    uint256 endBalance = IERC20(startToken).balanceOf(address(this));
    profit = endBalance > startBalance ? endBalance - startBalance : 0;
    
    require(profit >= params.minProfitAmount, "Insufficient profit");
    
    emit ArbitrageExecuted(
        "Triangular",
        startToken,
        params.path[1],
        params.amountIn,
        profit,
        _getRouterName(params.routers[0])
    );
    
    return profit;
}

/**
 * @dev Execute triangular arbitrage with flash loan
 */
function _executeTriangularFlashLoan(
    TriangularArbitrageParams calldata params
) internal returns (uint256 profit) {
    // Choose flash loan provider
    if (params.flashLoanProvider == 1) { // Aave
        address[] memory assets = new address[](1);
        assets[0] = params.path[0];
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // No debt
        
        // Encode triangular arbitrage parameters
        bytes memory callbackData = abi.encode(params);
        
        IAavePool(AAVE_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            callbackData,
            0
        );
        
        // Profit will be calculated in the callback
        return 0;
    } 
    else if (params.flashLoanProvider == 2) { // Balancer
        address[] memory tokens = new address[](1);
        tokens[0] = params.path[0];
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        // Encode triangular arbitrage parameters
        bytes memory callbackData = abi.encode(params);
        
        IBalancerVault(BALANCER_VAULT).flashLoan(
            address(this),
            tokens,
            amounts,
            callbackData
        );
        
        // Profit will be calculated in the callback
        return 0;
    }
    else {
        revert("Unsupported flash loan provider");
    }
}

/**
 * @dev Execute direct backrun arbitrage without flash loan
 */
function _executeDirectBackrunArbitrage(
    BackrunArbitrageParams calldata params
) internal returns (uint256 profit) {
    address startToken = params.path[0];
    uint256 startBalance = IERC20(startToken).balanceOf(address(this));
    
    require(startBalance >= params.amountIn, "Insufficient balance");
    
    // Execute each swap in the path
    uint256 currentAmount = params.amountIn;
    for (uint i = 0; i < params.routers.length; i++) {
        address tokenIn = params.path[i];
        address tokenOut = params.path[i + 1];
        address router = params.routers[i];
        uint24 fee = params.fees[i];
        
        // Approve router to spend token
        IERC20(tokenIn).safeApprove(router, 0);
        IERC20(tokenIn).safeApprove(router, currentAmount);
        
        // Execute the swap with this contract as recipient
        // This allows for proper backrun arbitrage execution
        address recipient = address(this);
        currentAmount = _executeTrade(tokenIn, tokenOut, currentAmount, router, fee, recipient);
    }
    
    // Calculate profit
    uint256 endBalance = IERC20(startToken).balanceOf(address(this));
    profit = endBalance > startBalance ? endBalance - startBalance : 0;
    
    require(profit >= params.minProfitAmount, "Insufficient profit");
    
    emit ArbitrageExecuted(
        "Backrun",
        startToken,
        params.path[1],
        params.amountIn,
        profit,
        _getRouterName(params.routers[0])
    );
    
    return profit;
}

/**
 * @dev Execute backrun arbitrage with flash loan
 */
function _executeBackrunFlashLoan(
    BackrunArbitrageParams calldata params
) internal returns (uint256 profit) {
    // Choose flash loan provider
    if (params.flashLoanProvider == 1) { // Aave
        address[] memory assets = new address[](1);
        assets[0] = params.path[0];
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // No debt
        
        // Encode backrun arbitrage parameters
        bytes memory callbackData = abi.encode(params);
        
        IAavePool(AAVE_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            callbackData,
            0
        );
        
        // Profit will be calculated in the callback
        return 0;
    } 
    else if (params.flashLoanProvider == 2) { // Balancer
        address[] memory tokens = new address[](1);
        tokens[0] = params.path[0];
        
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = params.amountIn;
        
        // Encode backrun arbitrage parameters
        bytes memory callbackData = abi.encode(params);
        
        IBalancerVault(BALANCER_VAULT).flashLoan(
            address(this),
            tokens,
            amounts,
            callbackData
        );
        
        // Profit will be calculated in the callback
        return 0;
    }
    else {
        revert("Unsupported flash loan provider");
    }
}