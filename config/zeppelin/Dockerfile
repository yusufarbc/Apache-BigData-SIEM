FROM apache/zeppelin:0.11.1

USER root

# ── 1. Python ve Sistem Bağımlılıkları ──────────────────────────
RUN apt-get update && \
    apt-get install -y python3-pip curl wget && \
    pip3 install numpy pandas matplotlib seaborn kafka-python --break-system-packages && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── 2. Spark 3.5.6 Kurulumu ─────────────────────────────────────
ENV SPARK_VERSION=3.5.6
ENV SPARK_HOME=/opt/spark
ENV PATH="${SPARK_HOME}/bin:${PATH}"

RUN wget -qO /tmp/spark.tgz \
    "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz" && \
    mkdir -p /opt/spark && \
    tar -xzf /tmp/spark.tgz -C /opt/spark --strip-components=1 && \
    rm /tmp/spark.tgz

# ── 3. Notebook ve Script Hazırlığı ──────────────────────────────
# Notebook dosyasını imajın içine kopyalıyoruz
RUN mkdir -p /opt/zeppelin/notebook_import
COPY NDR_Streaming_KMeans.zpln /opt/zeppelin/notebook_import/NDR_Streaming_KMeans.zpln
COPY import_notebook.sh /opt/zeppelin/import_notebook.sh
RUN chmod +x /opt/zeppelin/import_notebook.sh

# ── 4. Mac 'Hayalet' Dosyalarını Temizle (Kesin Çözüm) ─────────────
# Build sırasında içeri sızan tüm ._* dosyalarını zorla siliyoruz
RUN find /opt -name "._*" -delete || true

ENV ZEPPELIN_ADDR=0.0.0.0
ENV ZEPPELIN_PORT=8080
ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3

USER 1000
ENTRYPOINT ["/bin/bash", "-c", "/opt/zeppelin/import_notebook.sh & /opt/zeppelin/bin/zeppelin.sh"]
