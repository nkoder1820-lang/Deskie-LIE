# Deskie Lead Intelligence Engine (LIE)

An AI-powered lead intelligence system for discovering and scoring potential Deskie customers.

## Stack
- **Backend**: Python + FastAPI
- **AI**: NVIDIA NIM free tier (Llama 3.1 70B)
- **Database**: PostgreSQL (local)
- **Frontend**: Next.js + Tailwind

## Quick Start

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Node.js 18+
- NVIDIA NIM API key (free at [build.nvidia.com](https://build.nvidia.com))
- Google Places API key ([console.cloud.google.com](https://console.cloud.google.com))

### 2. Database Setup
```powershell
# Create the database
psql -U postgres -c "CREATE DATABASE deskie_lie;"

# Run migrations
psql -U postgres -d deskie_lie -f backend/migrations/001_initial_schema.sql
```

### 3. Backend Setup
```powershell
cd backend

# Copy and fill in env
copy .env.example .env
# Edit .env with your API keys

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the API server
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Setup
```powershell
cd frontend
npm install
npm run dev
```

### 5. Run Your First Research
Visit `http://localhost:8000/docs` and POST to `/api/research/run`:
```json
{
  "industry": "dental_clinics",
  "city": "Mumbai",
  "max_results": 10
}
```

Or open `http://localhost:3000` to use the dashboard.

## Without API Keys (Mock Mode)
The system works without API keys using mock data — great for testing the pipeline and dashboard.

## Architecture
```
Discovery Agent → Website + Review + Social + Value Agents → Scoring Engine → Report Generator → Dashboard
```

## Lead Priority
- **HOT** (90-100): Immediate outreach
- **HIGH** (75-89): Priority queue
- **MEDIUM** (50-74): Monitor
- **LOW** (<50): Not ready
