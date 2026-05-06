FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync

COPY src/ src/
COPY data/ data/

CMD ["uv", "run", "uvicorn", "cv_evaluator.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]