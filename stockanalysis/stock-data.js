// Stock Market Data Generator - Realistic Financial Data Synthesis
// Generates mathematically sound stock data for analysis

// Stock universe with realistic characteristics
const STOCK_UNIVERSE = {
  'AAPL': { sector: 'Technology', basePrice: 150.25, volatility: 0.25, beta: 1.21, marketCap: 2400 },
  'GOOGL': { sector: 'Technology', basePrice: 2750.80, volatility: 0.28, beta: 1.12, marketCap: 1800 },
  'MSFT': { sector: 'Technology', basePrice: 380.45, volatility: 0.23, beta: 0.95, marketCap: 2800 },
  'TSLA': { sector: 'Automotive', basePrice: 800.33, volatility: 0.45, beta: 2.15, marketCap: 800 },
  'AMZN': { sector: 'E-commerce', basePrice: 3200.15, volatility: 0.31, beta: 1.33, marketCap: 1600 },
  'META': { sector: 'Technology', basePrice: 320.50, volatility: 0.35, beta: 1.28, marketCap: 900 },
  'NVDA': { sector: 'Technology', basePrice: 450.75, volatility: 0.42, beta: 1.65, marketCap: 1100 },
  'JPM': { sector: 'Financial', basePrice: 145.80, volatility: 0.28, beta: 1.15, marketCap: 400 },
  'JNJ': { sector: 'Healthcare', basePrice: 165.90, volatility: 0.18, beta: 0.72, marketCap: 450 },
  'WMT': { sector: 'Retail', basePrice: 155.30, volatility: 0.22, beta: 0.51, marketCap: 420 },
  'XOM': { sector: 'Energy', basePrice: 110.45, volatility: 0.35, beta: 1.45, marketCap: 480 },
  'BRK-A': { sector: 'Conglomerate', basePrice: 520000, volatility: 0.20, beta: 0.88, marketCap: 750 }
};

// Financial news keywords for sentiment analysis
const SENTIMENT_KEYWORDS = {
  positive: [
    'growth', 'profit', 'earnings', 'revenue', 'expansion', 'innovation', 'breakthrough',
    'partnership', 'acquisition', 'upgrade', 'bullish', 'outperform', 'buy', 'strong',
    'beat', 'exceed', 'positive', 'optimistic', 'rise', 'gain', 'surge', 'rally'
  ],
  negative: [
    'loss', 'decline', 'drop', 'fall', 'crash', 'bear', 'sell', 'downgrade', 'weak',
    'miss', 'disappointment', 'concern', 'risk', 'uncertainty', 'volatile', 'struggle',
    'challenge', 'competitive', 'regulatory', 'investigation', 'lawsuit', 'recession'
  ],
  neutral: [
    'report', 'announcement', 'meeting', 'conference', 'update', 'statement', 'data',
    'analysis', 'forecast', 'estimate', 'guidance', 'outlook', 'target', 'consensus'
  ]
};

// Economic events that affect market sentiment
const MARKET_EVENTS = [
  { type: 'earnings', impact: 0.15, frequency: 0.25 },
  { type: 'fed_meeting', impact: 0.25, frequency: 0.08 },
  { type: 'product_launch', impact: 0.12, frequency: 0.15 },
  { type: 'merger_rumor', impact: 0.20, frequency: 0.05 },
  { type: 'analyst_upgrade', impact: 0.08, frequency: 0.20 },
  { type: 'regulatory_news', impact: -0.10, frequency: 0.12 }
];

// Generate realistic historical price data using Geometric Brownian Motion
function generateHistoricalPrices(symbol, days = 252) {
  const stock = STOCK_UNIVERSE[symbol] || STOCK_UNIVERSE['AAPL'];
  const { basePrice, volatility } = stock;
  
  const prices = [];
  let currentPrice = basePrice;
  
  for (let i = 0; i < days; i++) {
    // Geometric Brownian Motion with mean reversion
    const drift = 0.0002; // Small positive drift (5% annual)
    const randomShock = (Math.random() - 0.5) * 2; // Centered random walk
    const meanReversionFactor = 0.001 * (basePrice - currentPrice) / basePrice;
    
    const dailyReturn = drift + meanReversionFactor + volatility * randomShock / Math.sqrt(252);
    currentPrice = currentPrice * (1 + dailyReturn);
    
    // Generate OHLC data
    const open = currentPrice;
    const high = open * (1 + Math.abs(randomShock) * volatility * 0.5 / Math.sqrt(252));
    const low = open * (1 - Math.abs(randomShock) * volatility * 0.5 / Math.sqrt(252));
    const close = currentPrice * (1 + dailyReturn);
    const volume = Math.floor(Math.random() * 10000000 + 1000000); // 1M-11M shares
    
    prices.push({
      date: new Date(Date.now() - (days - i) * 24 * 60 * 60 * 1000),
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)), 
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      volume
    });
    
    currentPrice = close;
  }
  
  return prices;
}

// Calculate technical indicators
function calculateTechnicalIndicators(prices) {
  const closePrices = prices.map(p => p.close);
  const volumes = prices.map(p => p.volume);
  
  return {
    sma: calculateSMA(closePrices),
    ema: calculateEMA(closePrices),
    rsi: calculateRSI(closePrices),
    macd: calculateMACD(closePrices),
    bollingerBands: calculateBollingerBands(closePrices),
    atr: calculateATR(prices),
    stochastic: calculateStochastic(prices),
    volumeProfile: analyzeVolumeProfile(prices)
  };
}

// Simple Moving Average calculation
function calculateSMA(prices) {
  const periods = [5, 10, 20, 50, 200];
  const sma = {};
  
  periods.forEach(period => {
    if (prices.length >= period) {
      const sum = prices.slice(-period).reduce((a, b) => a + b, 0);
      sma[period] = parseFloat((sum / period).toFixed(2));
    }
  });
  
  return sma;
}

// Exponential Moving Average calculation
function calculateEMA(prices) {
  const periods = [12, 26, 50];
  const ema = {};
  
  periods.forEach(period => {
    if (prices.length >= period) {
      const multiplier = 2 / (period + 1);
      let emaValue = prices[0];
      
      for (let i = 1; i < Math.min(prices.length, period * 2); i++) {
        emaValue = (prices[i] * multiplier) + (emaValue * (1 - multiplier));
      }
      
      ema[period] = parseFloat(emaValue.toFixed(2));
    }
  });
  
  return ema;
}

// Relative Strength Index calculation
function calculateRSI(prices, period = 14) {
  if (prices.length < period + 1) return null;
  
  const gains = [];
  const losses = [];
  
  for (let i = 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? Math.abs(change) : 0);
  }
  
  const avgGain = gains.slice(-period).reduce((a, b) => a + b, 0) / period;
  const avgLoss = losses.slice(-period).reduce((a, b) => a + b, 0) / period;
  
  if (avgLoss === 0) return 100;
  
  const rs = avgGain / avgLoss;
  const rsi = 100 - (100 / (1 + rs));
  
  return parseFloat(rsi.toFixed(2));
}

// MACD calculation
function calculateMACD(prices) {
  if (prices.length < 26) return null;
  
  const ema12 = calculateEMA(prices.slice(-50)).ema?.[12] || 0;
  const ema26 = calculateEMA(prices.slice(-50)).ema?.[26] || 0;
  const macdLine = ema12 - ema26;
  
  // Simple signal line (9-period EMA of MACD)
  const signalLine = macdLine * 0.8; // Simplified calculation
  const histogram = macdLine - signalLine;
  
  return {
    macd: parseFloat(macdLine.toFixed(4)),
    signal: parseFloat(signalLine.toFixed(4)),
    histogram: parseFloat(histogram.toFixed(4))
  };
}

// Bollinger Bands calculation
function calculateBollingerBands(prices, period = 20) {
  if (prices.length < period) return null;
  
  const recentPrices = prices.slice(-period);
  const sma = recentPrices.reduce((a, b) => a + b, 0) / period;
  
  const variance = recentPrices.reduce((sum, price) => sum + Math.pow(price - sma, 2), 0) / period;
  const standardDeviation = Math.sqrt(variance);
  
  return {
    middle: parseFloat(sma.toFixed(2)),
    upper: parseFloat((sma + 2 * standardDeviation).toFixed(2)),
    lower: parseFloat((sma - 2 * standardDeviation).toFixed(2)),
    width: parseFloat((4 * standardDeviation).toFixed(2))
  };
}

// Average True Range calculation
function calculateATR(prices, period = 14) {
  if (prices.length < period + 1) return null;
  
  const trueRanges = [];
  
  for (let i = 1; i < prices.length; i++) {
    const current = prices[i];
    const previous = prices[i - 1];
    
    const tr1 = current.high - current.low;
    const tr2 = Math.abs(current.high - previous.close);
    const tr3 = Math.abs(current.low - previous.close);
    
    trueRanges.push(Math.max(tr1, tr2, tr3));
  }
  
  const atr = trueRanges.slice(-period).reduce((a, b) => a + b, 0) / period;
  return parseFloat(atr.toFixed(2));
}

// Stochastic Oscillator calculation
function calculateStochastic(prices, period = 14) {
  if (prices.length < period) return null;
  
  const recentPrices = prices.slice(-period);
  const currentClose = prices[prices.length - 1].close;
  const lowestLow = Math.min(...recentPrices.map(p => p.low));
  const highestHigh = Math.max(...recentPrices.map(p => p.high));
  
  const k = ((currentClose - lowestLow) / (highestHigh - lowestLow)) * 100;
  const d = k * 0.8; // Simplified D% calculation
  
  return {
    k: parseFloat(k.toFixed(2)),
    d: parseFloat(d.toFixed(2))
  };
}

// Volume Profile Analysis
function analyzeVolumeProfile(prices) {
  const recentPrices = prices.slice(-20);
  const avgVolume = recentPrices.reduce((sum, p) => sum + p.volume, 0) / recentPrices.length;
  const currentVolume = prices[prices.length - 1].volume;
  
  return {
    averageVolume: Math.floor(avgVolume),
    currentVolume: currentVolume,
    volumeRatio: parseFloat((currentVolume / avgVolume).toFixed(2)),
    trend: currentVolume > avgVolume * 1.2 ? 'high' : currentVolume < avgVolume * 0.8 ? 'low' : 'normal'
  };
}

// Generate news sentiment analysis
function generateNewsSentiment(symbol) {
  const stock = STOCK_UNIVERSE[symbol] || STOCK_UNIVERSE['AAPL'];
  
  // Simulate news events
  const newsEvents = [];
  const eventCount = Math.floor(Math.random() * 8) + 3; // 3-10 news items
  
  for (let i = 0; i < eventCount; i++) {
    const event = MARKET_EVENTS[Math.floor(Math.random() * MARKET_EVENTS.length)];
    const sentiment = Math.random() > 0.6 ? 'positive' : Math.random() > 0.3 ? 'negative' : 'neutral';
    const keywords = SENTIMENT_KEYWORDS[sentiment];
    
    newsEvents.push({
      type: event.type,
      sentiment: sentiment,
      impact: event.impact * (Math.random() * 0.5 + 0.75), // 75-125% of base impact
      keywords: keywords.slice(0, Math.floor(Math.random() * 3) + 1),
      timestamp: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000) // Last week
    });
  }
  
  // Calculate overall sentiment score
  const totalImpact = newsEvents.reduce((sum, event) => {
    const multiplier = event.sentiment === 'positive' ? 1 : event.sentiment === 'negative' ? -1 : 0;
    return sum + (event.impact * multiplier);
  }, 0);
  
  const sentimentScore = Math.max(-1, Math.min(1, totalImpact)); // Clamp between -1 and 1
  const normalizedScore = (sentimentScore + 1) / 2; // Convert to 0-1 scale
  
  return {
    score: parseFloat(normalizedScore.toFixed(3)),
    interpretation: normalizedScore > 0.6 ? 'bullish' : normalizedScore < 0.4 ? 'bearish' : 'neutral',
    newsCount: newsEvents.length,
    events: newsEvents,
    keyTopics: [...new Set(newsEvents.flatMap(e => e.keywords))].slice(0, 5),
    averageImpact: parseFloat((Math.abs(totalImpact) / newsEvents.length).toFixed(3))
  };
}

module.exports = {
  STOCK_UNIVERSE,
  generateHistoricalPrices,
  calculateTechnicalIndicators,
  generateNewsSentiment,
  SENTIMENT_KEYWORDS,
  MARKET_EVENTS
};