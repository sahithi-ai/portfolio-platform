FROM python:3.14-slim
WORKDIR /cloud-sentinel
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -m app
RUN mkdir /data && chown app /data
USER app
COPY app.py .
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
# CMD ["python", "app.py"]
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout","120","app:app"]