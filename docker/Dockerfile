FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY upstream/paperang-cli /opt/paperang-cli
RUN pip install --no-cache-dir /opt/paperang-cli
COPY docker/render.py /opt/render.py
COPY docker/inline_text.py /opt/inline_text.py
COPY web/icons.json /opt/icons.json
USER 65534:65534
ENTRYPOINT ["python", "/opt/render.py"]
