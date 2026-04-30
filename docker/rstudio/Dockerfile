FROM rocker/rstudio:4.3.2

# Install Java (headless) and system dependencies for R packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-11-jdk-headless \
    libssl-dev \
    libcurl4-openssl-dev \
    libxml2-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Verify Java installation
RUN java -version
