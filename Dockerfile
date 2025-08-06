FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序文件
COPY "agent core.py" ./
COPY README.md ./

# 创建配置文件目录
RUN mkdir -p /app/config

# 创建数据目录（用于保存生成的文件）
RUN mkdir -p /app/data
RUN mkdir -p /app/folder_scan_results
RUN mkdir -p /app/word_extracted_data

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 暴露端口（如果需要Web界面）
# EXPOSE 8080

# 创建启动脚本
RUN echo '#!/bin/bash\n\
if [ ! -f "/app/config/agent_config.json" ]; then\n\
    echo "首次运行，请配置API密钥..."\n\
    echo "请将配置文件挂载到 /app/config/agent_config.json"\n\
    exit 1\n\
fi\n\
cp /app/config/agent_config.json /app/\n\
python "agent core.py" "$@"' > /app/start.sh && chmod +x /app/start.sh

# 设置默认命令
CMD ["/app/start.sh"]