# 使用轻量级Python基础镜像
FROM api-base:0.1.0

# 设置工作目录
WORKDIR /app

# 复制项目配置文件
COPY ../backend/pyproject.toml /app/pyproject.toml
COPY ../backend/.python-version /app/.python-version
COPY ../backend/uv.lock /app/uv.lock

# 先复制 package 目录，因为 pyproject.toml 中 yuxi = { path = "package", editable = true }
COPY ../backend/package /app/package

# 如果网络还是不好，可以在后面添加 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --group test --no-dev --frozen

# 激活虚拟环境并添加到PATH
ENV PATH="/app/.venv/bin:$PATH"

# 复制 server 代码
COPY ../backend/server /app/server
