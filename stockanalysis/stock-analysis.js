// Advanced Stock Analysis Engine
// Implements sophisticated financial analysis algorithms

const { 
  STOCK_UNIVERSE, 
  generateHistoricalPrices, 
  calculateTechnicalIndicators, 
  generateNewsSentiment 
} = require('./stock-data');

// Price prediction using multiple models
function generatePricePrediction(symbol, technicalData, sentimentData, timeframe = 60) {
  const stock = STOCK_UNIVERSE[symbol] || STOCK_UNIVERSE['AAPL'];
  const currentPrice = stock.basePrice;
  
  // Model 1: Technical Analysis Based Prediction
  const technicalPrediction = calculateTechnicalPrediction(technicalData, currentPrice);
  
  // Model 2: Sentiment-Driven Prediction
  const sentimentPrediction = calculateSentimentPrediction(sentimentData, currentPrice);
  
  // Model 3: Mean Reversion Model
  const meanReversionPrediction = calculateMeanReversionPrediction(stock, technicalData);
  
  // Model 4: Monte Carlo Simulation
  const monteCarloResults = runMonteCarloSimulation(stock, timeframe);
  
  // Ensemble prediction (weighted average)
  const weights = { technical: 0.3, sentiment: 0.2, meanReversion: 0.25, monteCarlo: 0.25 };
  
  const ensemblePrediction = (
    technicalPrediction.target * weights.technical +
    sentimentPrediction.target * weights.sentiment +
    meanReversionPrediction.target * weights.meanReversion +
    monteCarloResults.expectedPrice * weights.monteCarlo
  );
  
  // Calculate confidence based on model agreement
  const predictions = [
    technicalPrediction.target,
    sentimentPrediction.target, 
    meanReversionPrediction.target,
    monteCarloResults.expectedPrice
  ];
  
  const variance = calculateVariance(predictions);
  const confidence = Math.max(0, Math.min(100, 100 - (variance / currentPrice * 100)));
  
  return {
    targetPrice: parseFloat(ensemblePrediction.toFixed(2)),
    confidence: parseFloat(confidence.toFixed(1)),
    direction: ensemblePrediction > currentPrice ? 'bullish' : 'bearish',
    timeframe: `${timeframe} days`,
    models: {
      technical: technicalPrediction,
      sentiment: sentimentPrediction,
      meanReversion: meanReversionPrediction,
      monteCarlo: monteCarloResults
    },
    scenarios: {
      bull: parseFloat((ensemblePrediction * 1.15).toFixed(2)),
      base: parseFloat(ensemblePrediction.toFixed(2)),
      bear: parseFloat((ensemblePrediction * 0.85).toFixed(2))
    }
  };
}

// Technical analysis based prediction
function calculateTechnicalPrediction(technicalData, currentPrice) {
  const { sma, ema, rsi, macd, bollingerBands } = technicalData;
  
  let technicalScore = 0;
  let signals = [];
  
  // Moving Average Signals
  if (sma[20] && sma[50]) {
    if (currentPrice > sma[20] && sma[20] > sma[50]) {
      technicalScore += 0.2;
      signals.push('MA_BULLISH');
    } else if (currentPrice < sma[20] && sma[20] < sma[50]) {
      technicalScore -= 0.2;
      signals.push('MA_BEARISH');
    }
  }
  
  // RSI Signals
  if (rsi) {
    if (rsi < 30) {
      technicalScore += 0.15; // Oversold - bullish
      signals.push('RSI_OVERSOLD');
    } else if (rsi > 70) {
      technicalScore -= 0.15; // Overbought - bearish
      signals.push('RSI_OVERBOUGHT');
    }
  }
  
  // MACD Signals
  if (macd && macd.histogram > 0) {
    technicalScore += 0.1;
    signals.push('MACD_BULLISH');
  } else if (macd && macd.histogram < 0) {
    technicalScore -= 0.1;
    signals.push('MACD_BEARISH');
  }
  
  // Bollinger Bands Signals
  if (bollingerBands) {
    if (currentPrice < bollingerBands.lower) {
      technicalScore += 0.1; // Near lower band - oversold
      signals.push('BB_OVERSOLD');
    } else if (currentPrice > bollingerBands.upper) {
      technicalScore -= 0.1; // Near upper band - overbought  
      signals.push('BB_OVERBOUGHT');
    }
  }
  
  // Convert technical score to price target
  const priceChange = technicalScore * currentPrice * 0.1; // Max 10% move
  const target = currentPrice + priceChange;
  
  return {
    target: parseFloat(target.toFixed(2)),
    score: parseFloat(technicalScore.toFixed(3)),
    signals: signals,
    strength: Math.abs(technicalScore) > 0.3 ? 'strong' : Math.abs(technicalScore) > 0.1 ? 'moderate' : 'weak'
  };
}

// Sentiment based prediction
function calculateSentimentPrediction(sentimentData, currentPrice) {
  const { score, averageImpact, newsCount } = sentimentData;
  
  // Convert sentiment score to price impact
  const sentimentMultiplier = (score - 0.5) * 2; // Convert 0-1 to -1 to 1
  const newsVolumeMultiplier = Math.min(newsCount / 10, 1); // Cap at 10 news items
  const impactMultiplier = Math.min(averageImpact * 5, 1); // Scale impact
  
  const totalImpact = sentimentMultiplier * newsVolumeMultiplier * impactMultiplier;
  const priceChange = totalImpact * currentPrice * 0.08; // Max 8% move from sentiment
  const target = currentPrice + priceChange;
  
  return {
    target: parseFloat(target.toFixed(2)),
    impact: parseFloat(totalImpact.toFixed(3)),
    sentiment: score > 0.6 ? 'bullish' : score < 0.4 ? 'bearish' : 'neutral',
    newsVolume: newsCount > 7 ? 'high' : newsCount > 4 ? 'moderate' : 'low'
  };
}

// Mean reversion prediction model
function calculateMeanReversionPrediction(stock, technicalData) {
  const { basePrice, volatility } = stock;
  const currentPrice = basePrice;
  
  // Calculate distance from long-term average
  const longTermSMA = technicalData.sma[200] || basePrice;
  const deviation = (currentPrice - longTermSMA) / longTermSMA;
  
  // Mean reversion strength based on volatility
  const reversionSpeed = 0.1 / volatility; // Higher volatility = slower reversion
  const targetDeviation = deviation * (1 - reversionSpeed);
  const target = longTermSMA * (1 + targetDeviation);
  
  return {
    target: parseFloat(target.toFixed(2)),  
    deviation: parseFloat((deviation * 100).toFixed(2)) + '%',
    reversionStrength: reversionSpeed > 0.3 ? 'strong' : reversionSpeed > 0.15 ? 'moderate' : 'weak',
    longTermAverage: parseFloat(longTermSMA.toFixed(2))
  };
}

// Monte Carlo price simulation
function runMonteCarloSimulation(stock, days, simulations = 1000) {
  const { basePrice, volatility } = stock;
  const annualDrift = 0.08; // 8% annual expected return
  const dailyDrift = annualDrift / 252;
  const dailyVolatility = volatility / Math.sqrt(252);
  
  const finalPrices = [];
  
  // Run simulations (CPU intensive for realistic blocking)
  for (let sim = 0; sim < simulations; sim++) {
    let price = basePrice;
    
    for (let day = 0; day < days; day++) {
      const randomShock = gaussianRandom(); // Box-Muller for normal distribution
      const dailyReturn = dailyDrift + dailyVolatility * randomShock;
      price = price * Math.exp(dailyReturn);
    }
    
    finalPrices.push(price);
  }
  
  // Calculate statistics
  finalPrices.sort((a, b) => a - b);
  const expectedPrice = finalPrices.reduce((sum, price) => sum + price, 0) / simulations;
  const var5 = finalPrices[Math.floor(simulations * 0.05)]; // 5% VaR
  const var95 = finalPrices[Math.floor(simulations * 0.95)]; // 95% confidence
  
  return {
    expectedPrice: parseFloat(expectedPrice.toFixed(2)),
    confidenceInterval: {
      lower: parseFloat(var5.toFixed(2)),
      upper: parseFloat(var95.toFixed(2))
    },
    probabilityUp: finalPrices.filter(p => p > basePrice).length / simulations,
    simulations: simulations
  };
}

// Risk assessment calculations
function calculateRiskMetrics(symbol, technicalData, historicalPrices) {
  const stock = STOCK_UNIVERSE[symbol] || STOCK_UNIVERSE['AAPL'];
  const { volatility, beta } = stock;
  
  // Value at Risk calculation
  const var5d = calculateVaR(historicalPrices, 0.05, 5);
  const var1d = calculateVaR(historicalPrices, 0.05, 1);
  
  // Sharpe Ratio estimation
  const sharpeRatio = calculateSharpeRatio(historicalPrices);
  
  // Maximum Drawdown
  const maxDrawdown = calculateMaxDrawdown(historicalPrices);
  
  // Volatility metrics
  const historicalVolatility = calculateHistoricalVolatility(historicalPrices);
  
  return {
    valueAtRisk: {
      oneDay: parseFloat(var1d.toFixed(2)),
      fiveDay: parseFloat(var5d.toFixed(2)),
      interpretation: var5d < -10 ? 'high_risk' : var5d < -5 ? 'moderate_risk' : 'low_risk'
    },
    volatility: {
      annualized: parseFloat((historicalVolatility * 100).toFixed(2)) + '%',
      rating: historicalVolatility > 0.4 ? 'very_high' : historicalVolatility > 0.3 ? 'high' : 
               historicalVolatility > 0.2 ? 'moderate' : 'low'
    },
    beta: {
      value: beta,
      interpretation: beta > 1.5 ? 'very_aggressive' : beta > 1 ? 'aggressive' : 
                     beta > 0.5 ? 'defensive' : 'very_defensive'
    },
    sharpeRatio: {
      value: parseFloat(sharpeRatio.toFixed(3)),
      rating: sharpeRatio > 1 ? 'excellent' : sharpeRatio > 0.5 ? 'good' : 
               sharpeRatio > 0 ? 'poor' : 'very_poor'
    },
    maxDrawdown: {
      value: parseFloat((maxDrawdown * 100).toFixed(2)) + '%',
      severity: maxDrawdown > 0.3 ? 'severe' : maxDrawdown > 0.2 ? 'moderate' : 'mild'
    }
  };
}

// Helper functions for complex calculations

function calculateVariance(values) {
  const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
  const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
  return squaredDiffs.reduce((sum, diff) => sum + diff, 0) / values.length;
}

function gaussianRandom() {
  // Box-Muller transformation for normal distribution
  let u = 0, v = 0;
  while(u === 0) u = Math.random(); // Converting [0,1) to (0,1)
  while(v === 0) v = Math.random();
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

function calculateVaR(prices, confidence, days) {
  const returns = [];
  for (let i = 1; i < prices.length; i++) {
    returns.push((prices[i].close - prices[i-1].close) / prices[i-1].close);
  }
  
  returns.sort((a, b) => a - b);
  const varIndex = Math.floor(returns.length * confidence);
  const dailyVaR = returns[varIndex];
  
  return dailyVaR * Math.sqrt(days) * prices[prices.length - 1].close;
}

function calculateSharpeRatio(prices) {
  const returns = [];
  for (let i = 1; i < prices.length; i++) {
    returns.push((prices[i].close - prices[i-1].close) / prices[i-1].close);
  }
  
  const avgReturn = returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
  const variance = calculateVariance(returns);
  const stdDev = Math.sqrt(variance);
  
  const riskFreeRate = 0.02 / 252; // 2% annual risk-free rate
  return (avgReturn - riskFreeRate) / stdDev * Math.sqrt(252); // Annualized
}

function calculateMaxDrawdown(prices) {
  let maxDrawdown = 0;
  let peak = prices[0].close;
  
  for (let i = 1; i < prices.length; i++) {
    if (prices[i].close > peak) {
      peak = prices[i].close;
    }
    
    const drawdown = (peak - prices[i].close) / peak;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }
  
  return maxDrawdown;
}

function calculateHistoricalVolatility(prices) {
  const returns = [];
  for (let i = 1; i < prices.length; i++) {
    returns.push(Math.log(prices[i].close / prices[i-1].close));
  }
  
  const variance = calculateVariance(returns);
  return Math.sqrt(variance * 252); // Annualized volatility
}

module.exports = {
  generatePricePrediction,
  calculateRiskMetrics,
  calculateTechnicalPrediction,
  calculateSentimentPrediction,
  runMonteCarloSimulation
};