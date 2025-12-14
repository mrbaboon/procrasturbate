# Build stage for CSS (optional - using CDN for now)
# FROM node:20-slim AS css-builder
# WORKDIR /build
# COPY package.json tailwind.config.js ./
# COPY src/procrasturbate/static/input.css ./src/procrasturbate/static/
# COPY src/procrasturbate/templates ./src/procrasturbate/templates
# RUN npm install && npm run css:build

FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy built CSS from builder (when using Tailwind build)
# COPY --from=css-builder /build/src/procrasturbate/static/dist ./src/procrasturbate/static/dist

# Default command
CMD ["uvicorn", "procrasturbate.main:app", "--host", "0.0.0.0", "--port", "8000"]
