# Stage 1: Build the frontend SPA
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend-app
COPY frontend-app/package*.json ./
RUN npm ci
COPY frontend-app/ .
RUN npm run build


# Stage 2: Build the backend application
FROM node:20-alpine AS backend-builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build


# Stage 3: Production image
FROM node:20-alpine AS production

WORKDIR /app

ENV NODE_ENV=production

# Copy production dependencies from backend-builder
COPY --from=backend-builder /app/package*.json ./
RUN npm ci --only=production

# Copy built backend and frontend
COPY --from=backend-builder /app/dist ./dist
COPY --from=frontend-builder /app/frontend-app/dist ./dist/frontend-app/dist

# Create a non-root user
RUN addgroup -g 1001 -S nodejs && adduser -S nodejs -u 1001
RUN chown -R nodejs:nodejs /app
USER nodejs

EXPOSE 3000

CMD ["node", "dist/server.js"]