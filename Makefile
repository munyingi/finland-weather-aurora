# Run everything from the repo root.
PY ?= python
DBT = dbt --no-send-anonymous-usage-stats
DBT_ARGS = --project-dir transform --profiles-dir transform
DEMO_DB = data/demo.duckdb

.PHONY: install demo live build publish app test lint clean demo-data

install:
	$(PY) -m pip install -r requirements.txt

## Offline end-to-end run on synthetic data (what CI runs)
demo:
	rm -f $(DEMO_DB)
	FWA_WAREHOUSE=$(DEMO_DB) $(PY) -m ingest demo
	FWA_WAREHOUSE=$(DEMO_DB) $(DBT) build $(DBT_ARGS)
	FWA_WAREHOUSE=$(DEMO_DB) $(PY) -m ingest publish --out data/published-demo --mode demo

## Refresh the demo files bundled with the dashboard
demo-data: demo
	cp data/published-demo/* dashboard/demo_data/

## Live run against FMI, NOAA SWPC and Open-Meteo
live:
	$(PY) -m ingest run
	$(DBT) source freshness $(DBT_ARGS) || true
	$(DBT) build $(DBT_ARGS)
	$(PY) -m ingest publish

app:
	streamlit run dashboard/app.py

test:
	$(PY) -m pytest -q

lint:
	ruff check .
	ruff format --check .

clean:
	rm -rf data/*.duckdb data/published* transform/target transform/logs
