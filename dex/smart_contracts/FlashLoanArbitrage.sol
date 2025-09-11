// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@aave/core-v3/contracts/flashloan/base/FlashLoanSimpleReceiverBase.sol";
import "@aave/core-v3/contracts/interfaces/IPoolAddressesProvider.sol";
import "@aave/core-v3/contracts/dependencies/openzeppelin/contracts/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

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

contract FlashLoanArbitrage is FlashLoanSimpleReceiverBase, Ownable, ReentrancyGuard {
    
    // DEX router addresses
    address public constant UNISWAP_V2_ROUTER = 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;
    address public constant SUSHISWAP_ROUTER = 0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F;
    address public constant UNISWAP_V3_ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
    
    // Events
    event ArbitrageExecuted(
        address indexed asset,
        uint256 amount,
        uint256 profit,
        string strategy
    );
    
    event FlashLoanReceived(address asset, uint256 amount, uint256 premium);
    
    // Arbitrage parameters
    struct ArbitrageParams {
        address tokenA;
        address tokenB;
        address tokenC;
        uint256 amountIn;
        string strategy; // "cross" or "triangular"
        bytes routerData;
    }
    
    constructor(address _addressProvider) 
        FlashLoanSimpleReceiverBase(IPoolAddressesProvider(_addressProvider)) 
    {}
    
    /**
     * @dev Execute cross-DEX arbitrage with flash loan
     */
    function executeCrossArbitrage(
        address asset,
        uint256 amount,
        address buyDex,
        address sellDex,
        address tokenB,
        uint256 minProfit
    ) external onlyOwner nonReentrant {
        
        ArbitrageParams memory params = ArbitrageParams({
            tokenA: asset,
            tokenB: tokenB,
            tokenC: address(0),
            amountIn: amount,
            strategy: "cross",
            routerData: abi.encode(buyDex, sellDex, minProfit)
        });
        
        // Request flash loan
        POOL.flashLoanSimple(
            address(this),
            asset,
            amount,
            abi.encode(params),
            0 // referralCode
        );
    }
    
    /**
     * @dev Execute triangular arbitrage with flash loan
     */
    function executeTriangularArbitrage(
        address tokenA,
        address tokenB, 
        address tokenC,
        uint256 amount,
        address dexRouter,
        uint256 minProfit
    ) external onlyOwner nonReentrant {
        
        ArbitrageParams memory params = ArbitrageParams({
            tokenA: tokenA,
            tokenB: tokenB,
            tokenC: tokenC,
            amountIn: amount,
            strategy: "triangular",
            routerData: abi.encode(dexRouter, minProfit)
        });
        
        // Request flash loan
        POOL.flashLoanSimple(
            address(this),
            tokenA,
            amount,
            abi.encode(params),
            0 // referralCode
        );
    }
    
    /**
     * @dev Aave flash loan callback
     */
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        
        emit FlashLoanReceived(asset, amount, premium);
        
        // Decode parameters
        ArbitrageParams memory arbParams = abi.decode(params, (ArbitrageParams));
        
        uint256 initialBalance = IERC20(asset).balanceOf(address(this));
        uint256 profit = 0;
        
        if (keccak256(bytes(arbParams.strategy)) == keccak256(bytes("cross"))) {
            profit = _executeCrossArbitrageLogic(arbParams);
        } else if (keccak256(bytes(arbParams.strategy)) == keccak256(bytes("triangular"))) {
            profit = _executeTriangularArbitrageLogic(arbParams);
        }
        
        // Ensure we have enough to repay the loan
        uint256 amountToRepay = amount + premium;
        uint256 finalBalance = IERC20(asset).balanceOf(address(this));
        
        require(finalBalance >= amountToRepay, "Insufficient funds to repay loan");
        
        // Calculate actual profit
        if (finalBalance > amountToRepay) {
            profit = finalBalance - amountToRepay;
        }
        
        // Approve repayment
        IERC20(asset).approve(address(POOL), amountToRepay);
        
        emit ArbitrageExecuted(asset, amount, profit, arbParams.strategy);
        
        return true;
    }
    
    /**
     * @dev Execute cross-DEX arbitrage logic
     */
    function _executeCrossArbitrageLogic(ArbitrageParams memory params) 
        internal returns (uint256 profit) {
        
        (address buyDex, address sellDex, uint256 minProfit) = 
            abi.decode(params.routerData, (address, address, uint256));
        
        uint256 initialAmount = params.amountIn;
        
        // Step 1: Buy on cheaper DEX (tokenA -> tokenB)
        uint256 tokenBAmount = _swapOnDex(
            buyDex,
            params.tokenA,
            params.tokenB,
            initialAmount,
            0 // minAmountOut will be calculated
        );
        
        // Step 2: Sell on more expensive DEX (tokenB -> tokenA)
        uint256 finalTokenAAmount = _swapOnDex(
            sellDex,
            params.tokenB,
            params.tokenA,
            tokenBAmount,
            initialAmount + minProfit // Ensure minimum profit
        );
        
        profit = finalTokenAAmount > initialAmount ? finalTokenAAmount - initialAmount : 0;
        
        return profit;
    }
    
    /**
     * @dev Execute triangular arbitrage logic
     */
    function _executeTriangularArbitrageLogic(ArbitrageParams memory params) 
        internal returns (uint256 profit) {
        
        (address dexRouter, uint256 minProfit) = 
            abi.decode(params.routerData, (address, uint256));
        
        uint256 initialAmount = params.amountIn;
        
        // Step 1: tokenA -> tokenB
        uint256 tokenBAmount = _swapOnDex(
            dexRouter,
            params.tokenA,
            params.tokenB,
            initialAmount,
            0
        );
        
        // Step 2: tokenB -> tokenC
        uint256 tokenCAmount = _swapOnDex(
            dexRouter,
            params.tokenB,
            params.tokenC,
            tokenBAmount,
            0
        );
        
        // Step 3: tokenC -> tokenA (complete the triangle)
        uint256 finalTokenAAmount = _swapOnDex(
            dexRouter,
            params.tokenC,
            params.tokenA,
            tokenCAmount,
            initialAmount + minProfit // Ensure minimum profit
        );
        
        profit = finalTokenAAmount > initialAmount ? finalTokenAAmount - initialAmount : 0;
        
        return profit;
    }
    
    /**
     * @dev Execute swap on specified DEX
     */
    function _swapOnDex(
        address router,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut
    ) internal returns (uint256 amountOut) {
        
        // Approve token spending
        IERC20(tokenIn).approve(router, amountIn);
        
        if (router == UNISWAP_V2_ROUTER || router == SUSHISWAP_ROUTER) {
            // Use V2 router
            address[] memory path = new address[](2);
            path[0] = tokenIn;
            path[1] = tokenOut;
            
            uint[] memory amounts = IUniswapV2Router(router).swapExactTokensForTokens(
                amountIn,
                minAmountOut,
                path,
                address(this),
                block.timestamp + 300 // 5 minutes deadline
            );
            
            amountOut = amounts[amounts.length - 1];
            
        } else if (router == UNISWAP_V3_ROUTER) {
            // Use V3 router
            IUniswapV3Router.ExactInputSingleParams memory swapParams = 
                IUniswapV3Router.ExactInputSingleParams({
                    tokenIn: tokenIn,
                    tokenOut: tokenOut,
                    fee: 3000, // 0.3% fee tier
                    recipient: address(this),
                    deadline: block.timestamp + 300,
                    amountIn: amountIn,
                    amountOutMinimum: minAmountOut,
                    sqrtPriceLimitX96: 0
                });
            
            amountOut = IUniswapV3Router(router).exactInputSingle(swapParams);
        }
        
        return amountOut;
    }
    
    /**
     * @dev Withdraw profits (owner only)
     */
    function withdrawToken(address token, uint256 amount) external onlyOwner {
        IERC20(token).transfer(owner(), amount);
    }
    
    /**
     * @dev Withdraw ETH (owner only)
     */
    function withdrawETH(uint256 amount) external onlyOwner {
        payable(owner()).transfer(amount);
    }
    
    /**
     * @dev Emergency function to recover stuck funds
     */
    function emergencyWithdraw(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        if (balance > 0) {
            IERC20(token).transfer(owner(), balance);
        }
    }
    
    // Receive ETH
    receive() external payable {}
}