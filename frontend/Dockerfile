FROM node:20-slim

WORKDIR /app

# Dependencies first — least-changing layer, so it stays cached
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Code last — most-changing layer
COPY app.js .
COPY views/ ./views/

USER node

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "app.js"]
