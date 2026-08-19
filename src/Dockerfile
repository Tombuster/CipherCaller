FROM python:3.12-trixie


RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc cmake git python3-all-dev \ 
    libasound-dev libportaudio2 libportaudiocpp0 portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ciphercaller

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# liboqs installation commands from: https://github.com/open-quantum-safe/liboqs-python/blob/main/Dockerfile
# Get liboqs
RUN git clone --depth 1 --branch main https://github.com/open-quantum-safe/liboqs

# Install liboqs with stateful-signature algorithms enabled
RUN cmake -S liboqs -B liboqs/build \
        -DBUILD_SHARED_LIBS=ON \
        -DOQS_ENABLE_SIG_STFL_LMS=ON \
        -DOQS_ENABLE_SIG_STFL_XMSS=ON \
        -DOQS_HAZARDOUS_EXPERIMENTAL_ENABLE_SIG_STFL_KEY_SIG_GEN=ON && \
    cmake --build liboqs/build --parallel 4 && \
    cmake --build liboqs/build --target install

ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib

COPY ciphercaller-launch.py .
COPY src/ src/
RUN pip install --no-cache-dir -r src/plugins/util/plugin-requirements.txt

ENTRYPOINT ["python", "ciphercaller-launch.py"]