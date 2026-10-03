FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY configs/layout.json ./configs/layout.json
COPY docs ./docs
COPY lab/configs ./lab/configs
RUN mkdir -p /app/data
ENV TOPOLOGY_STATE_PATH=/app/data/topology-observed.json
ENV LAYOUT_PATH=/app/configs/layout.json
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
