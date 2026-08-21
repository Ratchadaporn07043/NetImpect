FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# --- System packages ---
# iproute2  -> ให้คำสั่ง `tc` (Traffic Control / NetEm)
# iputils-ping, net-tools, curl -> ใช้ debug connection ไปหา Ollama บน host
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    iproute2 \
    iputils-ping \
    net-tools \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# --- Python deps ---
COPY requirements.txt /workspace/requirements.txt
RUN pip3 install --no-cache-dir -r /workspace/requirements.txt

# โค้ดจริงจะถูก mount เข้ามาทับตรงนี้ผ่าน docker-compose volumes
COPY . /workspace

CMD ["/bin/bash"]