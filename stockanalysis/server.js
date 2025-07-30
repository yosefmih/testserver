const express = require('express');
const cors = require('cors');
const axios = require('axios');

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
    
    // Simulate stock analysis logic
    const analysis = await performStockAnalysis(symbol);
    const prediction = generateStockPrediction();
    
    res.json({
      symbol: symbol.toUpperCase(),
      analysis,
      prediction,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      error: 'Failed to analyze stock',
      message: error.message
    });
  }
});

// Named prediction function
function generateStockPrediction() {
  return {
    timeframe: '2 months',
    confidence: Math.random() * 100,
    direction: Math.random() > 0.5 ? 'bullish' : 'bearish',
    targetPrice: (Math.random() * 200 + 50).toFixed(2)
  };
}

async function performStockAnalysis(symbol) {
  // Simulate analysis of news and trends
  const newsAnalysis = generateNewsAnalysis();
  const technicalAnalysis = generateTechnicalAnalysis();
  
  // Simulate API delay
  await simulateApiDelay();
  
  return {
    news: newsAnalysis,
    technical: technicalAnalysis,
    recommendation: Math.random() > 0.5 ? 'BUY' : 'SELL'
  };
}

// Named news analysis function
function generateNewsAnalysis() {
  return {
    sentiment: Math.random() > 0.5 ? 'positive' : 'negative',
    newsCount: Math.floor(Math.random() * 50) + 10,
    keyTopics: ['earnings', 'market trends', 'industry outlook']
  };
}

// Named technical analysis function
function generateTechnicalAnalysis() {
  return {
    trend: Math.random() > 0.5 ? 'upward' : 'downward',
    volatility: (Math.random() * 0.5 + 0.1).toFixed(3),
    support: (Math.random() * 100 + 50).toFixed(2),
    resistance: (Math.random() * 100 + 150).toFixed(2)
  };
}

// Named delay simulation function
function simulateApiDelay() {
  return new Promise(function delayResolver(resolve) {
    setTimeout(resolve, 1000);
  });
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