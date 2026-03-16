web: uvicorn pdf_engine.main:app --host 0.0.0.0 --port $PORT
worker: python -m arq pdf_engine.worker.WorkerSettings