#!/bin/bash

# Porter Hot Reload Demo Script
# This demonstrates hot reload capabilities for the txx app

echo "🚀 Porter Hot Reload Demo for txx app"
echo "======================================"

source ~/.zshrc

# Step 1: Ensure we're in the right Porter context
echo "📋 Step 1: Checking Porter context..."
pctx local
if [ $? -ne 0 ]; then
    echo "❌ Failed to switch to local context"
    exit 1
fi
echo "✅ Porter context: local"

# Step 2: Check credential helper
echo ""
echo "🔐 Step 2: Verifying Docker credential helper..."
docker-credential-porter --version
if [ $? -ne 0 ]; then
    echo "❌ Porter credential helper not found"
    exit 1
fi
echo "✅ Docker credential helper ready"

# Step 3: Check Docker config
echo ""
echo "🐳 Step 3: Verifying Docker registry configuration..."
if grep -q "992382605253.dkr.ecr.us-east-1.amazonaws.com.*porter" ~/.docker/config.json; then
    echo "✅ ECR credential helper configured"
else
    echo "⚠️  ECR credential helper not configured, but continuing..."
fi

# Step 4: Show current app status
echo ""
echo "📊 Step 4: Current txx app status..."
kubectl get pods -l app.kubernetes.io/name=txx-web --no-headers 2>/dev/null | head -1
echo "ℹ️  Production app is running ☝️"

echo ""
echo "🎯 Ready to start hot reload demo!"
echo ""
echo "Next steps:"
echo "1. Run: cd $(pwd) && tilt up"
echo "2. Open Tilt UI in browser"
echo "3. Edit server.py and watch changes appear instantly"
echo "4. Access app at: http://localhost:3000"
echo ""
echo "🔥 Hot reload features:"
echo "   • Python file changes: ~2-3 seconds"
echo "   • Dependency changes: ~30-60 seconds (full rebuild)"
echo "   • Same authentication as 'porter app build'"
echo "   • Side-by-side with production app"
echo ""
echo "Run this to start:"
echo "  tilt up"