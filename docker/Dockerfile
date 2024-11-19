FROM python:3.10-slim

WORKDIR /app

RUN DEBIAN_FRONTEND=noninteractive apt update --silent && \
  apt install -y net-tools curl && \
  pip install zebra_day

EXPOSE 8118

CMD ["zday_start"]
