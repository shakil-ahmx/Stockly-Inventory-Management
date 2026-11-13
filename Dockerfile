FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -r app && chown -R app /srv
USER app
EXPOSE 5000
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-5000} -w 2 --threads 2 --timeout 30 --preload run:app"]
