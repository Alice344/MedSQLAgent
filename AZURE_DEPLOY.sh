# ============================================================================
# Azure Deployment Guide
# ============================================================================
#
# This guide covers deploying the SQL Agent to Azure using two approaches:
#   A) Azure App Service (simplest – recommended)
#   B) Azure Container Apps (more scalable)
#
# Prerequisites:
#   - Azure CLI installed: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
#   - Docker installed (for container approach)
#   - An Azure subscription
#
# ============================================================================


# ────────────────────────────────────────────────────────────────────────────
# OPTION A: Azure App Service (Docker container)
# ────────────────────────────────────────────────────────────────────────────

# 1. Login to Azure
az login

# 2. Create a resource group
az group create --name sqlagent-rg --location eastus

# 3. Create an Azure Container Registry (ACR)
az acr create --resource-group sqlagent-rg --name sqlagentacr --sku Basic
az acr login --name sqlagentacr

# 4. Build and push the backend image
cd backend
docker build -t sqlagentacr.azurecr.io/sqlagent-backend:latest .
docker push sqlagentacr.azurecr.io/sqlagent-backend:latest

# 5. Build and push the frontend image
cd ../frontend
docker build -t sqlagentacr.azurecr.io/sqlagent-frontend:latest .
docker push sqlagentacr.azurecr.io/sqlagent-frontend:latest

# 6. Create App Service Plan (B2 = 2 cores, 3.5 GB RAM – good for ~100 users)
az appservice plan create \
  --name sqlagent-plan \
  --resource-group sqlagent-rg \
  --sku B2 \
  --is-linux

# 7. Create the backend web app
az webapp create \
  --resource-group sqlagent-rg \
  --plan sqlagent-plan \
  --name sqlagent-backend \
  --deployment-container-image-name sqlagentacr.azurecr.io/sqlagent-backend:latest

# 8. Configure backend environment variables
#    (Replace values with your actual keys)
az webapp config appsettings set \
  --resource-group sqlagent-rg \
  --name sqlagent-backend \
  --settings \
    LLM_PROVIDER=openai \
    OPENAI_API_KEY=sk-your-key-here \
    OPENAI_MODEL=gpt-4.1 \
    SQLAGENT_RELOAD=0 \
    SQLAGENT_WORKERS=4 \
    MAX_CONNECTIONS=100 \
    DB_POOL_SIZE=20 \
    LLM_CACHE_ENABLED=1 \
    ALLOWED_ORIGINS=https://sqlagent-frontend.azurewebsites.net

# 9. Enable health check
az webapp config set \
  --resource-group sqlagent-rg \
  --name sqlagent-backend \
  --generic-configurations '{"healthCheckPath": "/health"}'

# 10. Create the frontend web app
az webapp create \
  --resource-group sqlagent-rg \
  --plan sqlagent-plan \
  --name sqlagent-frontend \
  --deployment-container-image-name sqlagentacr.azurecr.io/sqlagent-frontend:latest

az webapp config appsettings set \
  --resource-group sqlagent-rg \
  --name sqlagent-frontend \
  --settings \
    API_URL=https://sqlagent-backend.azurewebsites.net


# ────────────────────────────────────────────────────────────────────────────
# OPTION B: Azure Container Apps (auto-scaling, pay-per-use)
# ────────────────────────────────────────────────────────────────────────────

# 1. Create Container Apps environment
az containerapp env create \
  --name sqlagent-env \
  --resource-group sqlagent-rg \
  --location eastus

# 2. Deploy backend
az containerapp create \
  --name sqlagent-backend \
  --resource-group sqlagent-rg \
  --environment sqlagent-env \
  --image sqlagentacr.azurecr.io/sqlagent-backend:latest \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 10 \
  --registry-server sqlagentacr.azurecr.io \
  --env-vars \
    LLM_PROVIDER=openai \
    OPENAI_API_KEY=sk-your-key-here \
    OPENAI_MODEL=gpt-4.1 \
    SQLAGENT_RELOAD=0 \
    SQLAGENT_WORKERS=4

# 3. Deploy frontend
az containerapp create \
  --name sqlagent-frontend \
  --resource-group sqlagent-rg \
  --environment sqlagent-env \
  --image sqlagentacr.azurecr.io/sqlagent-frontend:latest \
  --target-port 3000 \
  --ingress external \
  --cpu 0.5 --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 5 \
  --registry-server sqlagentacr.azurecr.io \
  --env-vars \
    NEXT_PUBLIC_API_BASE_URL=https://sqlagent-backend.<your-env>.azurecontainerapps.io


# ────────────────────────────────────────────────────────────────────────────
# SCALING GUIDE
# ────────────────────────────────────────────────────────────────────────────
#
# Users    | App Service SKU | Workers | Notes
# ---------|-----------------|---------|------
# 1-10     | B1 (1 core)     | 2       | Fine for demos
# 10-100   | B2 (2 cores)    | 4       | Good for internal teams
# 100-1000 | P2v3 (4 cores)  | 8       | Add Redis for shared state
# 1000+    | Container Apps  | auto    | Auto-scaling, add Redis + CDN
#
# For 10,000 users you need:
#   - Azure Container Apps with auto-scaling (10+ replicas)
#   - Azure Cache for Redis (shared session state)
#   - Azure Front Door (CDN + load balancing)
#   - Frontend is already Next.js (migrated from Streamlit)
#   - Azure SQL elastic pool or read replicas
