FROM python:3.11-slim

WORKDIR /app

# requirements.lock.txt is the full production freeze (direct + transitive),
# so the image installs exactly the versions that were tested.
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY . .

CMD ["python", "-m", "lore.main"]
