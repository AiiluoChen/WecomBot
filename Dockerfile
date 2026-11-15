FROM python:3.12-slim

WORKDIR /app

# 设置时区与 Python 无缓冲模式
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

# 安装系统基础库
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖配置并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码与数据文件
COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
