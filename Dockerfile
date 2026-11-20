# ==============================================================================
# Stage 1: Build React + Vite TypeScript Frontend
# ==============================================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ==============================================================================
# Stage 2: Python FastAPI Application
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Create a non-root system user and group
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Install pinned Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and fixtures
COPY . .

# Copy built frontend assets from stage 1 into app
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# Ensure cache directory exists and non-root user owns the application directory
RUN mkdir -p /app/cache && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8080

# Cloud Run injects $PORT at runtime (defaults to 8080)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
