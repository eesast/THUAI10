ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.13-slim
FROM ${BASE_IMAGE}
LABEL org.thuai10.mujoco.environment="arena-python-v1"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN pip install --no-cache-dir numpy==2.5.5 Pillow==13.0.0 onnxruntime==1.32.0
COPY embodied_arena/platform/protocol.py embodied_arena/platform/agent.py /runtime/
WORKDIR /submission
USER 65532:65532
ENTRYPOINT ["python", "-I", "-B", "/runtime/agent.py"]
