FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libasound-dev libportaudio2 libportaudiocpp0 portaudio19-dev python3-all-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ciphercaller

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY ciphercaller-launch.py .
COPY src/ src/

ENTRYPOINT ["python", "ciphercaller-launch.py"]