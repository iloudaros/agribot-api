import hmac
import hashlib
import time
import os
import json
import requests
import logging

logger = logging.getLogger(__name__)

import app.api.forward.credentials as credentials

API_KEY  = credentials.API_KEY
SECRET   = credentials.SECRET
BASE_URL = credentials.BASE_URL

def make_headers(body: str = "") -> dict:
    nonce     = os.urandom(16).hex()
    timestamp = str(int(time.time()))
    data      = nonce + timestamp + body
    signature = hmac.new(SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()

    return {
        "apiKey":       API_KEY,
        "X-Nonce":      nonce,
        "X-Timestamp":  timestamp,
        "X-Signature":  signature,
        "Content-Type": "application/json",
    }

def push_pc4_monitoring_data(payload: dict):
    body = json.dumps(payload, separators=(',', ':'))
    headers = make_headers(body)
    
    try:
        logger.info(f"Pushing PC4 Monitoring Data to AgroApps for parcel {payload.get('parcel_id')}...")
        resp = requests.post(f"{BASE_URL}/external-crop-monitoring", data=body, headers=headers, timeout=10)
        resp.raise_for_status()
        logger.info(f"✓ AgroApps PC4 Monitoring Push Success: {resp.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ AgroApps PC4 Monitoring Push Failed: {e}")
        if e.response is not None:
            logger.error(f"Response: {e.response.text}")
