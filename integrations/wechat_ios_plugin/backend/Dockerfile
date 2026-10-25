FROM node:24-alpine
WORKDIR /app
COPY backend ./backend
COPY package.json ./package.json
USER node
ENV HOST=0.0.0.0 PORT=8787
EXPOSE 8787
CMD ["node", "backend/server.mjs"]
