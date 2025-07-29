const express = require('express');
const cors = require('cors');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Health check endpoint - production ready
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    pid: process.pid
  });
});

// CPU-intensive computation endpoint that naturally blocks event loop
app.post('/compute', (req, res) => {
  const { iterations = 500000000, complexity = 'extreme' } = req.body; // 500 million iterations
  
  console.log(`Starting CPU-intensive computation with ${iterations} iterations...`);
  const startTime = Date.now();
  
  let result = 0;
  
  // Extremely complex mathematical computation designed to block for ~100 seconds
  for (let i = 0; i < iterations; i++) {
    // Heavy trigonometric operations
    result += Math.sqrt(i) * Math.sin(i) * Math.cos(i) * Math.tan(i / 1000);
    result += Math.pow(Math.log(i + 1), 2) + Math.exp(i / 10000000);
    
    if (complexity === 'extreme' && i % 10000 === 0) {
      // Very heavy array operations every 10k iterations
      const arr = new Array(5000).fill(0).map((_, idx) => {
        let val = Math.pow(Math.random() * idx, 3);
        val += Math.sqrt(Math.abs(Math.sin(idx))) * Math.cos(idx);
        return val + Math.log(idx + 1) * Math.exp(idx / 100000);
      });
      
      // Multiple reduce operations
      result += arr.reduce((sum, val) => sum + Math.sqrt(Math.abs(val)), 0);
      result += arr.reduce((sum, val) => sum + Math.pow(val, 0.5), 0);
      
      // Heavy string operations
      const str = JSON.stringify(arr.slice(0, 500));
      const processed = str.split('').map(c => c.charCodeAt(0)).reduce((a, b) => a + b, 0);
      result += processed;
      
      // Matrix-like operations
      for (let j = 0; j < 100; j++) {
        for (let k = 0; k < 100; k++) {
          result += Math.sin(j * k) * Math.cos(j + k);
        }
      }
    }
  }
  
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

// Stock analysis endpoint
app.get('/analyze/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    
    // Simulate stock analysis logic
    const analysis = await performStockAnalysis(symbol);
    
    res.json({
      symbol: symbol.toUpperCase(),
      analysis,
      prediction: {
        timeframe: '2 months',
        confidence: Math.random() * 100,
        direction: Math.random() > 0.5 ? 'bullish' : 'bearish',
        targetPrice: (Math.random() * 200 + 50).toFixed(2)
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      error: 'Failed to analyze stock',
      message: error.message
    });
  }
});

async function performStockAnalysis(symbol) {
  // Simulate analysis of news and trends
  const newsAnalysis = {
    sentiment: Math.random() > 0.5 ? 'positive' : 'negative',
    newsCount: Math.floor(Math.random() * 50) + 10,
    keyTopics: ['earnings', 'market trends', 'industry outlook']
  };
  
  const technicalAnalysis = {
    trend: Math.random() > 0.5 ? 'upward' : 'downward',
    volatility: (Math.random() * 0.5 + 0.1).toFixed(3),
    support: (Math.random() * 100 + 50).toFixed(2),
    resistance: (Math.random() * 100 + 150).toFixed(2)
  };
  
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  return {
    news: newsAnalysis,
    technical: technicalAnalysis,
    recommendation: Math.random() > 0.5 ? 'BUY' : 'SELL'
  };
}

// Basic info endpoint
app.get('/', (req, res) => {
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

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Stock analysis server running on port ${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('SIGINT received, shutting down gracefully');
  process.exit(0);
});