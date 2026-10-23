setup:
	pip install -r requirements.txt
bosch-sample:
	python -m backend.ml.bosch
train:
	python -m backend.ml.pipeline
train-quick:
	python -m backend.ml.pipeline --quick
api:
	uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
test:
	pytest backend/tests -q
