# 构建阶段
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# 生产阶段
FROM node:18-alpine

WORKDIR /app

# 安装 MySQL 客户端
RUN apk add --no-cache mysql-client

# 复制后端代码
COPY server/ ./server/
COPY api/ ./api/
COPY package*.json ./
RUN cd server && npm install --production

# 复制前端构建产物
COPY --from=builder /app/dist ./dist

# 暴露端口
EXPOSE 80 3001

# 启动脚本
COPY docker-start.sh ./
RUN chmod +x docker-start.sh

CMD ["./docker-start.sh"]
