FROM python:3.12-slim

#logs appear immediately instead of being buffered
ENV PYTHONUNBUFFERED=1

WORKDIR /app

#copy requirements first so this layer is cached unless deps change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#copy the rest of the backend
COPY . .

#0.0.0.0 so the port is reachable from outside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]