const express = require('express');
const cors = require('cors');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

let isBlocked = false;

// Health check endpoint
app.get('/health', (req, res) => {
  if (isBlocked) {
    // Perform CPU-intensive computation to overwhelm event loop
    console.log('Starting CPU-intensive computation...');
    let result = 0;
    const iterations = 50000000; // 50 million iterations
    
    // Complex mathematical computation
    for (let i = 0; i < iterations; i++) {
      result += Math.sqrt(i) * Math.sin(i) * Math.cos(i);
      
      // Add some array operations
      if (i % 100000 === 0) {
        const arr = new Array(1000).fill(0).map((_, idx) => Math.random() * idx);
        result += arr.reduce((sum, val) => sum + val, 0);
      }
    }
    
    console.log('Computation completed, result:', result);
  }
  
  res.status(200).json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime()
  });
});

// Endpoint to toggle event loop blocking
app.post('/block', (req, res) => {
  const { block } = req.body;
  isBlocked = block === true;
  
  res.json({
    message: `Event loop blocking ${isBlocked ? 'enabled' : 'disabled'}`,
    blocked: isBlocked
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
      block: 'POST /block',
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