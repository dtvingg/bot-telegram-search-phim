# Base image
FROM python:3.12-slim

# Cài uv
RUN pip install --no-cache-dir uv

# Tạo thư mục làm việc
WORKDIR /app

# Copy file dependency trước để tận dụng cache
COPY pyproject.toml uv.lock ./

# Tạo virtual environment và cài deps
RUN uv sync --frozen

# Copy toàn bộ source code
COPY . .

# Thiết lập biến môi trường
ENV PYTHONPATH=/app

# Lệnh chạy bot
CMD ["uv", "run", "python", "-m", "src.bot"]
