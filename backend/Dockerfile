FROM python:3.12-slim

WORKDIR /app

# lxml benötigt keine Build-Tools mehr (Wheels), aber bcrypt/rust ggf. – slim reicht.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
# Ein Worker: die ODS-Datei wird prozessintern per Lock serialisiert.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
