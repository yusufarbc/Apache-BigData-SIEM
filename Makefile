.PHONY: up down build logs run-job shell help

# Default target
help:
	@echo "Apache-BigData-SIEM Makefile"
	@echo ""
	@echo "Commands:"
	@echo "  make up                - Start the entire SIEM platform via docker-compose"
	@echo "  make down              - Tear down the platform and remove containers"
	@echo "  make build             - Rebuild all docker images (e.g., flog generators)"
	@echo "  make logs              - View logs of all containers"
	@echo "  make run-job           - Submit the Spark ETL process to the cluster"
	@echo "  make shell             - Get an interactive shell inside the spark-master"
	@echo "  make clean-volumes     - CAUTION! Tear down and remove associated volumes (data loss)"

up:
	docker compose up -d

build:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

run-job:
	docker exec -it spark-master spark-submit \
		--master spark://spark-master:7077 \
		--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
		/opt/bitnami/spark/jobs/etl_process.py

shell:
	docker exec -it spark-master /bin/bash

clean-volumes:
	docker compose down -v
