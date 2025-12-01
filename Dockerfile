FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 写入启动脚本
COPY start.sh .

EXPOSE 10000

RUN apt-get update && apt-get install -y \
    libgtk-3-0 \
    libgtk-4-1 \
    libasound2 \
    libnss3 \
    libxss1 \
    libxtst6 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libxshmfence1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libglib2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libatspi2.0-0 \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-libav \
    libgles2 \
    --no-install-recommends


# 启动 JupyterLab
CMD ["./start.sh"]
