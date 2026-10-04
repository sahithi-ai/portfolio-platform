FROM python:3.14
WORKDIR /ContainerApp
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY handler.py .
CMD ["python", "handler.py"]