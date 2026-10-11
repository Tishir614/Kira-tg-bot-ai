FROM python:3.12-slim-trixie
ARG COMFYUI_VERSION=v0.36.0
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN git clone --depth 1 --branch ${COMFYUI_VERSION} https://github.com/Comfy-Org/ComfyUI.git comfyui
WORKDIR /opt/comfyui
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8188
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--cpu"]
