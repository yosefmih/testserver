# N+N-1 asset retention:
#   1. FROM ...:latest AS previous       (pulls the prior deploy)
#   2. build N, stash as build_latest/   (so the NEXT deploy's previous
#                                         stage finds it)
#   3. merge N-1 (previous/build_latest) + N into build/
# Result: this image serves both N and N-1 hashed chunks.
FROM 992382605253.dkr.ecr.us-east-1.amazonaws.com/static-app:latest AS previous
RUN mkdir -p /app/build_latest

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY server.js build.sh ./

ARG PORTER_BUILD_ID=local
ENV BUILD_ID=${PORTER_BUILD_ID}
RUN sh build.sh && mv build build_latest && mkdir -p build
COPY --from=previous /app/build_latest build
RUN cp -r build_latest/. build/

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=build /app/node_modules  ./node_modules
COPY --from=build /app/server.js     ./server.js
COPY --from=build /app/build         ./build
COPY --from=build /app/build_latest  ./build_latest
ARG PORTER_BUILD_ID=local
ENV BUILD_ID=${PORTER_BUILD_ID}
EXPOSE 3000
CMD ["node", "server.js"]
