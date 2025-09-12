// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

// PancakeSwap V2 interfaces
interface IPancakeRouter {
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

// PancakeSwap V3 interfaces  
interface IPancakeV3Router {
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

// Venus (Aave-like) flash loan interface for BSC
interface IVenusPool {
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

contract BSCArbitrageExecutor is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;
    
    // BSC DEX router addresses
    address public constant PANCAKESWAP_V2_ROUTER = 0x10ED43C718714eb63d5aA57B78B54704E256024E;
    address public constant PANCAKESWAP_V3_ROUTER = 0x1b81D678ffb9C0263b24A97847620C99d213eB14;
    address public constant BISWAP_ROUTER = 0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8;
    address public constant APESWAP_ROUTER = 0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7;
    
    // Flash loan providers on BSC
    address public constant VENUS_POOL = 0xfD36E2c2a6789Db23113685031d7F16329158384;
    
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
        if (params.flashLoanProvider == VENUS_POOL) {
            _executeVenusFlashLoan(params);
        } else {
            revert("Unsupported flash loan provider");
        }
    }
    
    /**
     * @dev Execute Venus flash loan
     */
    function _executeVenusFlashLoan(ArbitrageParams memory params) internal {
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
        
        IVenusPool(VENUS_POOL).flashLoan(
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
     * @dev Venus flash loan callback
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == VENUS_POOL, "Unauthorized");
        require(initiator == address(this), "Invalid initiator");
        
        FlashLoanData memory flashData = abi.decode(params, (FlashLoanData));
        
        // Execute arbitrage
        uint256 profit = _performArbitrageTrade(flashData.params);
        
        // Repay flash loan
        uint256 totalRepayment = amounts[0] + premiums[0];
        require(profit > totalRepayment, "Arbitrage not profitable");
        
        IERC20(assets[0]).safeTransfer(VENUS_POOL, totalRepayment);
        
        emit FlashLoanExecuted(assets[0], amounts[0], profit - totalRepayment);
        
        return true;
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
            params.buyFee
        );
        
        // Step 2: Sell on expensive DEX (tokenB -> tokenA)
        uint256 tokenAReceived = _executeTrade(
            params.tokenB,
            params.tokenA,
            tokenBReceived,
            params.sellRouter,
            params.sellFee
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
     * @dev Execute trade on specified router
     */
    function _executeTrade(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        address router,
        uint24 fee
    ) internal returns (uint256) {
        IERC20(tokenIn).safeApprove(router, amountIn);
        
        if (router == PANCAKESWAP_V3_ROUTER) {
            // PancakeSwap V3 trade
            IPancakeV3Router.ExactInputSingleParams memory params = IPancakeV3Router.ExactInputSingleParams({
                tokenIn: tokenIn,
                tokenOut: tokenOut,
                fee: fee,
                recipient: address(this),
                deadline: block.timestamp + 300,
                amountIn: amountIn,
                amountOutMinimum: 0,
                sqrtPriceLimitX96: 0
            });
            
            return IPancakeV3Router(router).exactInputSingle(params);
        } else {
            // PancakeSwap V2 or other V2-compatible DEX trade
            address[] memory path = new address[](2);
            path[0] = tokenIn;
            path[1] = tokenOut;
            
            uint[] memory amounts = IPancakeRouter(router).swapExactTokensForTokens(
                amountIn,
                0, // Accept any amount of tokens out
                path,
                address(this),
                block.timestamp + 300
            );
            
            return amounts[1];
        }
    }
    
    /**
     * @dev Get router name for events
     */
    function _getRouterName(address router) internal pure returns (string memory) {
        if (router == PANCAKESWAP_V2_ROUTER) return "PancakeSwapV2";
        if (router == PANCAKESWAP_V3_ROUTER) return "PancakeSwapV3";
        if (router == BISWAP_ROUTER) return "BiSwap";
        if (router == APESWAP_ROUTER) return "ApeSwap";
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
        if (buyRouter == PANCAKESWAP_V3_ROUTER) {
            // For V3, would need quoter contract (simplified here)
            tokenBOut = amountIn; // Placeholder
        } else {
            address[] memory buyPath = new address[](2);
            buyPath[0] = tokenA;
            buyPath[1] = tokenB;
            uint[] memory buyAmounts = IPancakeRouter(buyRouter).getAmountsOut(amountIn, buyPath);
            tokenBOut = buyAmounts[1];
        }
        
        // Get amount out from sell router
        uint256 tokenAOut;
        if (sellRouter == PANCAKESWAP_V3_ROUTER) {
            // For V3, would need quoter contract (simplified here)
            tokenAOut = tokenBOut; // Placeholder
        } else {
            address[] memory sellPath = new address[](2);
            sellPath[0] = tokenB;
            sellPath[1] = tokenA;
            uint[] memory sellAmounts = IPancakeRouter(sellRouter).getAmountsOut(tokenBOut, sellPath);
            tokenAOut = sellAmounts[1];
        }
        
        expectedProfit = tokenAOut > amountIn ? tokenAOut - amountIn : 0;
    }
    
    receive() external payable {}
}