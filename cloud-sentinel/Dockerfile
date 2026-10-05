FROM python:3.14-slim
WORKDIR /cloud-sentinel
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -m app
USER app
COPY app.py .
# CMD ["python", "app.py"]
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout","120","app:app"]