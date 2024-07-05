FROM python:3.9-alpine AS osv-scanner-builder
WORKDIR /app
# Install osv-scanner
RUN apk update && \
    apk add osv-scanner

# FROM golang:latest
# WORKDIR /app
# RUN go install github.com/google/osv-scanner/cmd/osv-scanner@v1

FROM python:3.9-buster
WORKDIR /app

# Copy osv-scanner binary
COPY --from=osv-scanner-builder /usr/bin/osv-scanner /usr/bin/osv-scanner
COPY --from=osv-scanner-builder /lib/ld-musl-x86_64.so.1 /lib/ld-musl-x86_64.so.1
RUN ln -s /lib/ld-musl-x86_64.so.1 /lib/libc.musl-x86_64.so.1

# Install scancode
ARG SCANCODE_VERSION=32.1.0
RUN apt-get update && apt-get install -y libbz2-1.0 xz-utils zlib1g libxml2-dev libxslt1-dev libpopt0 && \
    curl -L \
    https://github.com/nexB/scancode-toolkit/releases/download/v${SCANCODE_VERSION}/scancode-toolkit-v${SCANCODE_VERSION}_py3.9-linux.tar.gz \
    --output /opt/scancode.tar.gz && \
    cd /opt && tar -xzf scancode.tar.gz && \
    echo "$(which python)" > scancode-toolkit-v${SCANCODE_VERSION}/PYTHON_EXECUTABLE && \
    ln -s /usr/bin/python3 /usr/bin/python3.9 && \
    cd scancode-toolkit-v${SCANCODE_VERSION}/ && ./configure && \
    ln -s /opt/scancode-toolkit-v${SCANCODE_VERSION}/scancode /usr/bin/scancode && \
    rm /opt/scancode.tar.gz

# Install SonarScanner CLI
RUN cd /opt && wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-6.1.0.4477-linux-x64.zip && \
    unzip sonar-scanner-cli-6.1.0.4477-linux-x64.zip && \
    ln -s /opt/sonar-scanner-6.1.0.4477-linux-x64/bin/sonar-scanner /usr/bin/sonar-scanner && \
    rm sonar-scanner-cli-6.1.0.4477-linux-x64.zip

# Install ORT(opensource-review-toolkit)
RUN cd /opt && wget https://github.com/oss-review-toolkit/ort/releases/download/25.0.0/ort-25.0.0.zip && \
    unzip ort-25.0.0.zip && \
    ln -s /opt/ort-25.0.0/bin/ort /usr/bin/ort && \
    rm ort-25.0.0.zip

# Install Java
RUN apt-get update && \
    apt-get install -y openjdk-11-jdk

COPY . .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

CMD ["python", "src/main.py"]
