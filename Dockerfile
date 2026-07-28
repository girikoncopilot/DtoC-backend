FROM node:20-alpine

WORKDIR /app

COPY package.json ./
COPY .env.example ./
COPY bundled-framework ./bundled-framework
COPY scripts ./scripts
COPY src ./src

EXPOSE 8787

CMD ["node", "src/server.mjs"]
