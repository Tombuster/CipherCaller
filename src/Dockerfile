FROM python:3.12-trixie

# TODO: install soundcore https://www.alsa-project.org/wiki/Matrix:Module-hda-intel

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc libasound-dev libportaudio2 libportaudiocpp0 \
    portaudio19-dev python3-all-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ciphercaller

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY ciphercaller-launch.py .
COPY src/ src/
RUN pip install --no-cache-dir -r src/plugins/util/plugin-requirements.txt

ENTRYPOINT ["python", "ciphercaller-launch.py"]