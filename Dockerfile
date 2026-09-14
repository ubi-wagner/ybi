# --- stage 1: build the UI -------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

# --- stage 2: the app ------------------------------------------------------
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
# Bootstrap scripts ship with the image so seeding runs inside the deployment,
# against the private database URL, rather than requiring someone to open the
# database to the internet and run them from a laptop.
COPY scripts/ ./scripts/
# The documents ship with the image for the same reason the scripts do. They
# did not, and a rebuilt database came back with an empty document register
# and no way to refill it from inside the deployment: `seed_documents.py` was
# in the container and the eighteen documents it files were not. The guides
# come with them, so a link in the run sheet resolves where the run sheet is.
COPY docs/ ./docs/
COPY --from=web /web/dist ./web/dist
# Evidence lands here. On Railway this path must be a mounted volume — a
# container filesystem is discarded on every deploy, and an audit record whose
# documents disappear on redeploy is not an audit record.
RUN mkdir -p storage

ENV PYTHONPATH=/srv
EXPOSE 8000
# --proxy-headers so the address in the record is the client's, not Railway's
# edge. The only route into the container is that proxy, so trusting the
# forwarded header from any peer is trusting the one peer there is.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
