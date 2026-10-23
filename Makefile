setup:
	pip install pandas scikit-learn lightgbm shap plotly streamlit streamlit-autorefresh fastapi uvicorn python-multipart anthropic pytest pillow
train:
	python -m backend.ml.train
api:
	uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
dash:
	streamlit run dashboard/app.py
test:
	pytest backend/tests -q
