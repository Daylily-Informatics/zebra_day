FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN DEBIAN_FRONTEND=noninteractive apt update --silent && apt install -y net-tools curl
COPY . .
RUN pip install zebra_day

EXPOSE 8118

CMD ["zday_start"]
