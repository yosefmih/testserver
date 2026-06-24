const express = require('express');
const cors = require('cors');
const axios = require('axios');

// Import comprehensive stock analysis modules
const { 
  STOCK_UNIVERSE, 
  generateHistoricalPrices, 
  calculateTechnicalIndicators, 
  generateNewsSentiment 
} = require('./stock-data');
const { 
  generatePricePrediction, 
  calculateRiskMetrics 
} = require('./stock-analysis');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Health check endpoint - production ready
app.get('/health', function healthCheckHandler(req, res) {
  res.status(200).json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    pid: process.pid
  });
});

// CPU-intensive computation endpoint that naturally blocks event loop
app.post('/compute', function computeHandler(req, res) {
  const { iterations = 500000000, complexity = 'extreme' } = req.body;
  
  console.log(`Starting CPU-intensive computation with ${iterations} iterations...`);
  const startTime = Date.now();
  
  const result = performHeavyComputation(iterations, complexity);
  
  const duration = Date.now() - startTime;
  console.log(`Computation completed in ${duration}ms, result:`, result);
  
  res.json({
    message: 'CPU-intensive computation completed',
    result: result,
    duration: `${duration}ms`,
    iterations,
    complexity
  });
});

// Named function for heavy computation to show in profiler
function performHeavyComputation(iterations, complexity) {
  let result = 0;
  
  // Main computation loop
  for (let i = 0; i < iterations; i++) {
    result += trigonometricCalculations(i);
    
    if (complexity === 'extreme' && i % 10000 === 0) {
      result += heavyArrayOperations();
      result += matrixCalculations();
    }
  }
  
  return result;
}

// Named trigonometric calculation function
function trigonometricCalculations(i) {
  const basicTrig = Math.sqrt(i) * Math.sin(i) * Math.cos(i) * Math.tan(i / 1000);
  const advancedMath = Math.pow(Math.log(i + 1), 2) + Math.exp(i / 10000000);
  return basicTrig + advancedMath;
}

// Named heavy array operations function
function heavyArrayOperations() {
  const arr = new Array(5000).fill(0).map(function arrayMapper(_, idx) {
    let val = Math.pow(Math.random() * idx, 3);
    val += Math.sqrt(Math.abs(Math.sin(idx))) * Math.cos(idx);
    return val + Math.log(idx + 1) * Math.exp(idx / 100000);
  });
  
  // Named reducer functions
  const sum1 = arr.reduce(function sqrtReducer(sum, val) {
    return sum + Math.sqrt(Math.abs(val));
  }, 0);
  
  const sum2 = arr.reduce(function powReducer(sum, val) {
    return sum + Math.pow(val, 0.5);
  }, 0);
  
  // Heavy string processing
  const stringResult = processHeavyStrings(arr);
  
  return sum1 + sum2 + stringResult;
}

// Named string processing function
function processHeavyStrings(arr) {
  const str = JSON.stringify(arr.slice(0, 500));
  const processed = str.split('').map(function charMapper(c) {
    return c.charCodeAt(0);
  }).reduce(function charReducer(a, b) {
    return a + b;
  }, 0);
  return processed;
}

// Named matrix calculations function
function matrixCalculations() {
  let result = 0;
  for (let j = 0; j < 100; j++) {
    for (let k = 0; k < 100; k++) {
      result += Math.sin(j * k) * Math.cos(j + k);
    }
  }
  return result;
}

// Stock analysis endpoint
app.get('/analyze/:symbol', async function stockAnalysisHandler(req, res) {
  try {
    const { symbol } = req.params;
    
    // Perform comprehensive stock analysis
    const analysis = await performStockAnalysis(symbol);
    
    // Comprehensive response with all analysis components
    res.json({
      symbol: symbol.toUpperCase(),
      currentPrice: (STOCK_UNIVERSE[symbol.toUpperCase()] || STOCK_UNIVERSE['AAPL']).basePrice,
      analysis: {
        technical: analysis.technical,
        sentiment: analysis.sentiment,
        prediction: analysis.prediction,
        risk: analysis.risk,
        recommendation: analysis.recommendation
      },
      metadata: {
        ...analysis.metadata,
        timestamp: new Date().toISOString(),
        version: '2.0-comprehensive'
      }
    });
  } catch (error) {
    res.status(500).json({
      error: 'Failed to analyze stock',
      message: error.message
    });
  }
});

// This function is now replaced by the comprehensive analysis above
// Keeping for backward compatibility but not used
function generateStockPrediction() {
  return {
    timeframe: '2 months',
    confidence: Math.random() * 100,
    direction: Math.random() > 0.5 ? 'bullish' : 'bearish',
    targetPrice: (Math.random() * 200 + 50).toFixed(2)
  };
}

async function performStockAnalysis(symbol) {
  console.log(`Starting comprehensive analysis for ${symbol}...`);
  const startTime = Date.now();
  
  // Step 1: Generate realistic historical price data (CPU intensive)
  const historicalPrices = generateRealisticPriceData(symbol);
  
  // Step 2: Calculate technical indicators (computationally expensive)
  const technicalIndicators = calculateComprehensiveTechnicalAnalysis(historicalPrices);
  
  // Step 3: Perform news sentiment analysis (CPU intensive text processing)
  const sentimentAnalysis = performAdvancedSentimentAnalysis(symbol);
  
  // Step 4: Generate price predictions using multiple models (very CPU intensive)
  const pricePrediction = generateAdvancedPricePrediction(symbol, technicalIndicators, sentimentAnalysis);
  
  // Step 5: Calculate comprehensive risk metrics (Monte Carlo heavy)
  const riskAssessment = calculateAdvancedRiskMetrics(symbol, technicalIndicators, historicalPrices);
  
  // Step 6: Generate investment recommendation
  const recommendation = generateInvestmentRecommendation(technicalIndicators, sentimentAnalysis, pricePrediction, riskAssessment);
  
  const analysisTime = Date.now() - startTime;
  console.log(`Analysis completed in ${analysisTime}ms for ${symbol}`);
  
  return {
    technical: technicalIndicators,
    sentiment: sentimentAnalysis,
    prediction: pricePrediction,
    risk: riskAssessment,
    recommendation: recommendation,
    metadata: {
      analysisTime: `${analysisTime}ms`,
      dataPoints: historicalPrices.length,
      complexity: 'comprehensive'
    }
  };
}

// Generate realistic historical price data (CPU intensive)
function generateRealisticPriceData(symbol) {
  const daysOfData = 252; // 1 year of trading data
  console.log(`Generating ${daysOfData} days of price data for ${symbol}...`);
  
  return generateHistoricalPrices(symbol, daysOfData);
}

// Calculate comprehensive technical analysis (CPU intensive)
function calculateComprehensiveTechnicalAnalysis(historicalPrices) {
  console.log('Calculating technical indicators...');
  
  // This is computationally expensive - calculates multiple indicators
  const indicators = calculateTechnicalIndicators(historicalPrices);
  
  // Add additional CPU-intensive calculations
  const supportResistanceLevels = calculateSupportResistanceLevels(historicalPrices);
  const trendAnalysis = performTrendAnalysis(historicalPrices);
  
  return {
    ...indicators,
    supportResistance: supportResistanceLevels,
    trend: trendAnalysis,
    strength: calculateTechnicalStrength(indicators)
  };
}

// Advanced sentiment analysis with CPU-intensive text processing
function performAdvancedSentimentAnalysis(symbol) {
  console.log(`Performing sentiment analysis for ${symbol}...`);
  
  // Generate comprehensive sentiment data (CPU intensive)
  const sentimentData = generateNewsSentiment(symbol);
  
  // Additional CPU-intensive sentiment processing
  const sectorSentiment = calculateSectorSentiment(symbol);
  const marketSentiment = calculateMarketSentiment();
  
  return {
    ...sentimentData,
    sector: sectorSentiment,
    market: marketSentiment,
    composite: calculateCompositeSentiment(sentimentData, sectorSentiment, marketSentiment)
  };
}

// Generate advanced price prediction (very CPU intensive)
function generateAdvancedPricePrediction(symbol, technicalData, sentimentData) {
  console.log('Running price prediction models...');
  
  // This runs Monte Carlo simulations and is very CPU intensive
  return generatePricePrediction(symbol, technicalData, sentimentData, 60);
}

// Calculate advanced risk metrics (Monte Carlo heavy)
function calculateAdvancedRiskMetrics(symbol, technicalData, historicalPrices) {
  console.log('Calculating risk metrics...');
  
  // CPU-intensive risk calculations
  return calculateRiskMetrics(symbol, technicalData, historicalPrices);
}

// Helper functions for additional CPU-intensive calculations

function calculateSupportResistanceLevels(prices) {
  // CPU-intensive support/resistance calculation
  const recentPrices = prices.slice(-50).map(p => p.close);
  const pivotPoints = [];
  
  // Find local maxima and minima (computationally expensive)
  for (let i = 2; i < recentPrices.length - 2; i++) {
    const isLocalMax = recentPrices[i] > recentPrices[i-1] && recentPrices[i] > recentPrices[i+1] &&
                      recentPrices[i] > recentPrices[i-2] && recentPrices[i] > recentPrices[i+2];
    const isLocalMin = recentPrices[i] < recentPrices[i-1] && recentPrices[i] < recentPrices[i+1] &&
                      recentPrices[i] < recentPrices[i-2] && recentPrices[i] < recentPrices[i+2];
    
    if (isLocalMax || isLocalMin) {
      pivotPoints.push({ price: recentPrices[i], type: isLocalMax ? 'resistance' : 'support' });
    }
  }
  
  // Cluster similar levels (more CPU work)
  const clusteredLevels = clusterPivotPoints(pivotPoints);
  
  return {
    support: clusteredLevels.filter(l => l.type === 'support').slice(0, 3),
    resistance: clusteredLevels.filter(l => l.type === 'resistance').slice(0, 3),
    pivotCount: pivotPoints.length
  };
}

function clusterPivotPoints(pivots) {
  // CPU-intensive clustering algorithm
  const clusters = [];
  const threshold = 0.02; // 2% clustering threshold
  
  for (const pivot of pivots) {
    let addedToCluster = false;
    
    for (const cluster of clusters) {
      if (Math.abs(pivot.price - cluster.price) / cluster.price < threshold) {
        cluster.count++;
        cluster.price = (cluster.price * (cluster.count - 1) + pivot.price) / cluster.count;
        addedToCluster = true;
        break;
      }
    }
    
    if (!addedToCluster) {
      clusters.push({ price: pivot.price, type: pivot.type, count: 1 });
    }
  }
  
  return clusters.sort((a, b) => b.count - a.count);
}

function performTrendAnalysis(prices) {
  // CPU-intensive trend analysis
  const shortTerm = prices.slice(-20).map(p => p.close);
  const mediumTerm = prices.slice(-50).map(p => p.close);
  const longTerm = prices.slice(-200).map(p => p.close);
  
  // Calculate trend strength using linear regression (CPU intensive)
  const shortTrend = calculateLinearRegression(shortTerm);
  const mediumTrend = calculateLinearRegression(mediumTerm);
  const longTrend = calculateLinearRegression(longTerm);
  
  return {
    short: { slope: shortTrend.slope, strength: Math.abs(shortTrend.correlation) },
    medium: { slope: mediumTrend.slope, strength: Math.abs(mediumTrend.correlation) },
    long: { slope: longTrend.slope, strength: Math.abs(longTrend.correlation) },
    overall: shortTrend.slope > 0 && mediumTrend.slope > 0 ? 'upward' : 
             shortTrend.slope < 0 && mediumTrend.slope < 0 ? 'downward' : 'sideways'
  };
}

function calculateLinearRegression(values) {
  // CPU-intensive linear regression calculation
  const n = values.length;
  const x = Array.from({ length: n }, (_, i) => i);
  const y = values;
  
  const sumX = x.reduce((a, b) => a + b, 0);
  const sumY = y.reduce((a, b) => a + b, 0);
  const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
  const sumXX = x.reduce((sum, xi) => sum + xi * xi, 0);
  const sumYY = y.reduce((sum, yi) => sum + yi * yi, 0);
  
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  
  // Calculate correlation coefficient
  const correlation = (n * sumXY - sumX * sumY) / 
    Math.sqrt((n * sumXX - sumX * sumX) * (n * sumYY - sumY * sumY));
  
  return { slope, intercept, correlation };
}

function calculateTechnicalStrength(indicators) {
  // Aggregate technical strength score
  let strength = 0;
  let signals = 0;
  
  if (indicators.rsi) {
    if (indicators.rsi < 30) strength += 1; // Oversold - bullish
    else if (indicators.rsi > 70) strength -= 1; // Overbought - bearish
    signals++;
  }
  
  if (indicators.macd && indicators.macd.histogram > 0) {
    strength += 1;
    signals++;
  } else if (indicators.macd && indicators.macd.histogram < 0) {
    strength -= 1;
    signals++;
  }
  
  return signals > 0 ? strength / signals : 0;
}

function calculateSectorSentiment(symbol) {
  // CPU-intensive sector analysis
  const stock = STOCK_UNIVERSE[symbol] || STOCK_UNIVERSE['AAPL'];
  const sector = stock.sector;
  
  // Simulate sector sentiment calculation (CPU intensive)
  let sectorScore = 0;
  for (let i = 0; i < 1000; i++) {
    sectorScore += Math.sin(i) * Math.cos(i * stock.volatility);
  }
  
  const normalizedScore = (Math.sin(sectorScore) + 1) / 2;
  
  return {
    sector: sector,
    score: parseFloat(normalizedScore.toFixed(3)),
    trend: normalizedScore > 0.6 ? 'positive' : normalizedScore < 0.4 ? 'negative' : 'neutral'
  };
}

function calculateMarketSentiment() {
  // CPU-intensive market sentiment calculation
  let marketScore = 0;
  const iterations = 5000;
  
  for (let i = 0; i < iterations; i++) {
    marketScore += Math.sqrt(i) * Math.sin(i / 100) * Math.cos(i / 200);
  }
  
  const normalizedScore = (Math.sin(marketScore / iterations) + 1) / 2;
  
  return {
    score: parseFloat(normalizedScore.toFixed(3)),
    interpretation: normalizedScore > 0.65 ? 'bullish' : normalizedScore < 0.35 ? 'bearish' : 'neutral',
    vix: parseFloat((normalizedScore * 40 + 10).toFixed(2)) // Simulated VIX
  };
}

function calculateCompositeSentiment(stock, sector, market) {
  // Weighted composite sentiment
  const weights = { stock: 0.5, sector: 0.3, market: 0.2 };
  const composite = stock.score * weights.stock + sector.score * weights.sector + market.score * weights.market;
  
  return {
    score: parseFloat(composite.toFixed(3)),
    interpretation: composite > 0.6 ? 'bullish' : composite < 0.4 ? 'bearish' : 'neutral',
    confidence: Math.abs(composite - 0.5) * 2 // Distance from neutral
  };
}

function generateInvestmentRecommendation(technical, sentiment, prediction, risk) {
  // CPU-intensive recommendation algorithm
  let score = 0;
  const factors = [];
  
  // Technical factors
  if (technical.strength > 0.5) {
    score += 0.3;
    factors.push('Strong technical signals');
  } else if (technical.strength < -0.5) {
    score -= 0.3;
    factors.push('Weak technical signals');
  }
  
  // Sentiment factors
  if (sentiment.composite.score > 0.6) {
    score += 0.2;
    factors.push('Positive sentiment');
  } else if (sentiment.composite.score < 0.4) {
    score -= 0.2;
    factors.push('Negative sentiment');
  }
  
  // Prediction factors
  if (prediction.direction === 'bullish' && prediction.confidence > 70) {
    score += 0.3;
    factors.push('Strong upside prediction');
  } else if (prediction.direction === 'bearish' && prediction.confidence > 70) {
    score -= 0.3;
    factors.push('Strong downside prediction');
  }
  
  // Risk factors
  if (risk.volatility.rating === 'very_high') {
    score -= 0.2;
    factors.push('High volatility risk');
  }
  
  // Generate recommendation
  let recommendation, action;
  if (score > 0.3) {
    recommendation = 'BUY';
    action = 'Strong buy recommendation based on positive technical and fundamental factors';
  } else if (score > 0.1) {
    recommendation = 'WEAK_BUY';
    action = 'Cautious buy with close monitoring recommended';
  } else if (score < -0.3) {
    recommendation = 'SELL';
    action = 'Sell recommendation due to negative outlook';
  } else if (score < -0.1) {
    recommendation = 'WEAK_SELL';
    action = 'Consider reducing position';
  } else {
    recommendation = 'HOLD';
    action = 'Hold current position, mixed signals';
  }
  
  return {
    recommendation,
    action,
    confidence: Math.abs(score) * 100,
    score: parseFloat(score.toFixed(3)),
    factors
  };
}

// Basic info endpoint
app.get('/', function rootHandler(req, res) {
  res.json({
    name: 'Stock Analysis Test Server',
    version: '1.0.0',
    endpoints: {
      health: 'GET /health',
      compute: 'POST /compute (CPU-intensive operation)',
      analyze: 'GET /analyze/:symbol'
    }
  });
});

app.listen(PORT, '0.0.0.0', function serverStartCallback() {
  console.log(`Stock analysis server running on port ${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', function sigtermHandler() {
  console.log('SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', function sigintHandler() {
  console.log('SIGINT received, shutting down gracefully');
  process.exit(0);
});