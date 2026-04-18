FROM python:3.11-alpine

# Non-root user for safer execution
RUN adduser -D -s /bin/sh dztest

COPY app.py /app/app.py
RUN chmod +r /app/app.py

USER dztest
WORKDIR /work

ENTRYPOINT ["python3", "/app/app.py"]
