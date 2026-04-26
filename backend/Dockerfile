FROM python:3.12-alpine

WORKDIR /app

RUN addgroup -S app && adduser -S -G app app

COPY app.py /app/app.py

EXPOSE 8080

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import sys, urllib.request; body = urllib.request.urlopen('http://127.0.0.1:8080/', timeout=3).read().decode(); sys.exit(0 if body == 'Hello from Effective Mobile!' else 1)"

CMD ["python", "app.py"]
