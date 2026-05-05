FROM node:22-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY src ./src
COPY index.html .
COPY favicon.svg .
COPY tsconfig.json .
COPY vite.config.ts .

EXPOSE 3000

CMD ["npm", "run", "dev"]
