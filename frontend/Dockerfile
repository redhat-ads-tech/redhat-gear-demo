FROM registry.access.redhat.com/hi/python:3.12
WORKDIR /app
COPY index.html server.py ./
COPY images/ ./images/
EXPOSE 8080
CMD ["python3", "server.py"]
