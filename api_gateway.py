#!/usr/bin/env python3
"""
Arbitrage Flywheel API Gateway
FastAPI application that serves real-time momentum data to external users
Secure API key validation on every request
"""

from fastapi import FastAPI, Depends, HTTPException, Security, Query
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import json
from datetime import datetime
import time
import sys
import os

# Add project root to path so we can import trendfinder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Arbitrage Momentum API",
    description="Real-time market momentum data for arbitrage detection",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS: Allow clients from any origin (configure for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# CONFIGURATION
# ============================================================================

DB_PATH = 'arbitrage_flywheel.db'
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# ============================================================================
# PYDANTIC MODELS (API Response Schemas)
# ============================================================================

class UserInfo(BaseModel):
    username: str
    tier: str
    user_id: int

class MetricsData(BaseModel):
    ami_score_percentage: Optional[float] = None
    signal_class: Optional[str] = None
    raw_data: Optional[dict] = None
    last_update: Optional[str] = None

class MomentumResponse(BaseModel):
    status: str
    asset_id: str
    metrics: MetricsData
    authorized_user: str
    tier: str
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    engine: str
    version: str
    database_connected: bool

class AlertResponse(BaseModel):
    alert_id: int
    asset_id: str
    ami_score: float
    alert_type: str
    signal_confidence: float
    timestamp: str

# ============================================================================
# DATABASE HELPERS
# ============================================================================

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def verify_api_key(api_key: str = Security(api_key_header)) -> dict:
    """Security dependency: Verify API key on every protected request"""
    if not api_key:
        raise HTTPException(
            status_code=403,
            detail="API Key header missing. Include 'X-API-Key' header with your request."
        )
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, username, tier, is_active FROM api_users WHERE api_key = ?",
        (api_key,)
    )
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=403, detail="Invalid or revoked API Key")
    
    if not user['is_active']:
        raise HTTPException(status_code=403, detail="API Key is inactive")
    
    return {
        "user_id": user['user_id'],
        "username": user['username'],
        "tier": user['tier']
    }

def log_api_usage(user_id: int, endpoint: str, response_time_ms: float):
    """Log API usage for billing and analytics"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO api_usage (user_id, endpoint, response_time_ms) VALUES (?, ?, ?)",
        (user_id, endpoint, response_time_ms)
    )
    conn.commit()
    conn.close()

# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@app.get("/")
def dashboard():
    """TrendGoogle Dashboard UI"""
    from fastapi.responses import HTMLResponse
    import os
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        return HTMLResponse(content=open(html_path).read())
    return HTMLResponse("<h1>Dashboard not found</h1><p>Run from the trendgoogle directory.</p>")

# ============================================================================
# PROTECTED ENDPOINTS (API Key Required)
# ============================================================================

@app.get("/api/v1/momentum/{asset_id}", response_model=MomentumResponse, tags=["Data"])
def get_asset_momentum(
    asset_id: str,
    user: dict = Depends(verify_api_key),
    limit_days: int = Query(30, description="Historical baseline in days")
):
    """
    Get real-time Arbitrage Momentum Index for an asset
    
    **Parameters:**
    - `asset_id`: The topic to query (e.g., 'rajasthan_copper_scrap')
    - `limit_days`: Calculate AMI baseline from last N days (default: 30)
    
    **Headers:**
    - `X-API-Key`: Your API key (required)
    
    **Response:**
    - `ami_score_percentage`: Arbitrage Momentum Index (% change)
    - `signal_class`: CRITICAL_ALERT (>25%), MARKET_DECAY (<-25%), or STABLE
    - `timestamp`: UTC timestamp of latest update
    """
    
    start_time = time.time()
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Fetch latest monitoring data for this asset
        cursor.execute('''
            SELECT topic_name, timestamp, ami_score, signal_class, raw_data
            FROM monitoring_history
            WHERE topic_name = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (asset_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Asset '{asset_id}' not found or no monitoring data available"
            )
        
        # Parse response
        raw_data = json.loads(result['raw_data']) if result['raw_data'] else {}
        
        response_time_ms = (time.time() - start_time) * 1000
        log_api_usage(user['user_id'], f"/api/v1/momentum/{asset_id}", response_time_ms)
        
        return MomentumResponse(
            status="success",
            asset_id=asset_id,
            metrics=MetricsData(
                ami_score_percentage=result['ami_score'],
                signal_class=result['signal_class'],
                raw_data=raw_data,
                last_update=result['timestamp']
            ),
            authorized_user=user['username'],
            tier=user['tier'],
            timestamp=datetime.utcnow().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/v1/alerts", response_model=List[AlertResponse], tags=["Data"])
def get_recent_alerts(
    user: dict = Depends(verify_api_key),
    limit: int = Query(10, ge=1, le=100, description="Max alerts to return"),
    asset_id: Optional[str] = Query(None, description="Filter by asset ID")
):
    """
    Get recent anomaly alerts (AMI >±25%)
    
    **Parameters:**
    - `limit`: Maximum number of alerts to return (1-100, default: 10)
    - `asset_id`: Optional filter by specific asset
    
    **Headers:**
    - `X-API-Key`: Your API key (required)
    """
    
    start_time = time.time()
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if asset_id:
            cursor.execute('''
                SELECT id, topic_name, ami_score, alert_type, signal_confidence, timestamp
                FROM alert_log
                WHERE topic_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (asset_id, limit))
        else:
            cursor.execute('''
                SELECT id, topic_name, ami_score, alert_type, signal_confidence, timestamp
                FROM alert_log
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        alerts = [
            AlertResponse(
                alert_id=row['id'],
                asset_id=row['topic_name'],
                ami_score=row['ami_score'],
                alert_type=row['alert_type'],
                signal_confidence=row['signal_confidence'],
                timestamp=row['timestamp']
            )
            for row in results
        ]
        
        response_time_ms = (time.time() - start_time) * 1000
        log_api_usage(user['user_id'], "/api/v1/alerts", response_time_ms)
        
        return alerts
    
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/v1/assets", tags=["Data"])
def list_monitored_assets(user: dict = Depends(verify_api_key)):
    """
    List all currently monitored assets (topics)
    
    **Headers:**
    - `X-API-Key`: Your API key (required)
    """
    
    start_time = time.time()
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT topic_name, geo, category, created_at
            FROM active_profiles
            WHERE topic_name != ''
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        assets = [
            {
                "asset_id": row['topic_name'],
                "geo": row['geo'],
                "category": row['category'],
                "created_at": row['created_at']
            }
            for row in results
        ]
        
        response_time_ms = (time.time() - start_time) * 1000
        log_api_usage(user['user_id'], "/api/v1/assets", response_time_ms)
        
        return {
            "status": "success",
            "count": len(assets),
            "assets": assets,
            "authorized_user": user['username'],
            "tier": user['tier']
        }
    
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/v1/usage", tags=["Account"])
def get_usage_stats(user: dict = Depends(verify_api_key)):
    """
    Get your API usage statistics (for billing)
    
    **Headers:**
    - `X-API-Key`: Your API key (required)
    """
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get usage count
        cursor.execute('''
            SELECT COUNT(*) as request_count, 
                   AVG(response_time_ms) as avg_response_time
            FROM api_usage
            WHERE user_id = ?
        ''', (user['user_id'],))
        
        stats = cursor.fetchone()
        conn.close()
        
        return {
            "status": "success",
            "username": user['username'],
            "tier": user['tier'],
            "request_count": stats['request_count'] or 0,
            "avg_response_time_ms": stats['avg_response_time'] or 0,
            "billing": {
                "requests_this_period": stats['request_count'] or 0,
                "rate_limit": 1000,
                "period_minutes": 60
            }
        }
    
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# ============================================================================
# TREND DISCOVERY ENDPOINT
# ============================================================================

class DiscoverRequest(BaseModel):
    prompt: str

class DiscoverResponse(BaseModel):
    topic_name: str
    keywords: list
    analysis: dict
    alert_config: dict
    saved: bool

@app.post("/api/v1/discover", response_model=DiscoverResponse, tags=["Discovery"])
def discover_trend(req: DiscoverRequest, user: dict = Depends(verify_api_key)):
    """
    Analyze a user prompt with AI, find relevant keywords,
    validate against Google Trends, and save as a new monitoring profile.
    """
    from trendfinder import parse_with_gemini, validate_keywords, save_profile, ensure_alert_config_columns, load_env

    load_env()
    try:
        result = parse_with_gemini(req.prompt)
    except ValueError as e:
        raise HTTPException(400, str(e))
    valid = validate_keywords(result)
    if not valid:
        raise HTTPException(400, "Keywords returned no data. Try a broader topic.")
    alert_config = result.get("alert_config", {})

    # Ensure DB has new columns
    db_path = os.path.join(os.path.dirname(__file__), "arbitrage_flywheel.db")
    import sqlite3
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    cols = {row[1] for row in c.execute("PRAGMA table_info(active_profiles)")}
    for col, dtype in [("spike_threshold","REAL DEFAULT 25.0"),("drop_threshold","REAL DEFAULT -25.0"),("monitor_enabled","INTEGER DEFAULT 1"),("alert_on_spike","INTEGER DEFAULT 1"),("alert_on_drop","INTEGER DEFAULT 1")]:
        if col not in cols:
            c.execute(f"ALTER TABLE active_profiles ADD COLUMN {col} {dtype}")
    conn.commit(); conn.close()

    save_profile(result, alert_config)

    return DiscoverResponse(
        topic_name=result.get("topic_name","unknown"),
        keywords=result.get("keywords",[]),
        analysis=result.get("analysis",{}),
        alert_config=alert_config,
        saved=True
    )

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom error response formatting"""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={
            "status": "error",
            "error_code": exc.status_code,
            "message": exc.detail,
            "timestamp": datetime.utcnow().isoformat()
        },
        status_code=exc.status_code
    )

# ============================================================================
# RUN
# ============================================================================

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
