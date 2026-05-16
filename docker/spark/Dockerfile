FROM bitnamilegacy/spark:3.5.6-debian-12-r1

USER root

# Spark ML libleri icin gerekli olan numpy kurulumu
RUN apt-get update && \
    apt-get install -y python3-pip && \
    pip3 install numpy --break-system-packages && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER 1001
