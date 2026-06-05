# Transitional: no `FROM ...:latest AS previous` stage so the first build
# can succeed without :latest existing. Still produces /app/build_latest in
# the final image so once :latest is pushed (by the workflow's retag step),
# the next build can re-enable the previous stage and N+N-1 kicks in.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY server.js build.sh ./

ARG PORTER_BUILD_ID=local
ENV BUILD_ID=${PORTER_BUILD_ID}
RUN sh build.sh && cp -r build build_latest

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
