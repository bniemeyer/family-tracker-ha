FROM python:3.12-alpine
RUN apk add --no-cache tzdata
WORKDIR /app
COPY app/ /app/
ENV PYTHONUNBUFFERED=1
EXPOSE 8099 8100
CMD ["python3", "/app/server.py"]
