FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY server.js build.sh ./

# Porter passes PORTER_-prefixed args from the GHA env, so set
# PORTER_BUILD_ID: ${{ github.sha }} in your workflow to get a new
# asset hash per commit. Falls back to "local" for ad-hoc builds.
ARG PORTER_BUILD_ID=local
ENV BUILD_ID=${PORTER_BUILD_ID}
RUN sh build.sh

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/server.js    ./server.js
COPY --from=build /app/build        ./build
ARG PORTER_BUILD_ID=local
ENV BUILD_ID=${PORTER_BUILD_ID}
EXPOSE 3000
CMD ["node", "server.js"]
