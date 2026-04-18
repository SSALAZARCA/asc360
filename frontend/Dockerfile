# ==== STAGE 1: Dependencias ====
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

# ==== STAGE 2: Build ====
FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=https://asc360.online/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ==== STAGE 3: Runtime de producción ====
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
