FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 写入启动脚本
COPY start.sh .

EXPOSE 10000

# 启动 JupyterLab
CMD ["./start.sh"]
