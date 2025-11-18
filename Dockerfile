# Étape 1 : Build Frontend
FROM node:18-alpine as build-stage
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Étape 2 : Runtime Backend
FROM python:3.10-slim
WORKDIR /app

# Copie des requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code Backend
COPY backend/ .

# Copie du build Frontend depuis l'étape 1 vers un dossier 'static'
COPY --from=build-stage /app/frontend/dist /app/static

# ENV pour Cloud Run
ENV PORT=8080

# Commande de lancement (FastAPI)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]