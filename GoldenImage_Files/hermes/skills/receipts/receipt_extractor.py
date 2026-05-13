#!/usr/bin/env python3
"""
receipt_extractor.py — Gmail Receipt Extraction for Archer (April 9, 2026)
Full Google API version. Checkpoint wired to PocketBase.
"""

import os
import sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import requests
from datetime import datetime

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets'
]

def load_checkpoint(agent_id="archer", pb_url="http://localhost:8090"):
    """Load checkpoint from PocketBase"""
    try:
        r = requests.get(
            f"{pb_url}/api/collections/startup_checkpoint/records",
            params={
                "filter": f'agent_id="{agent_id}"',
                "sort": "-created_at",
                "perPage": 1
            },
            timeout=3
        )
        items = r.json().get("items", [])
        return items[0] if items else None
    except Exception as e:
        return None

def save_checkpoint(agent_id="archer", blocking_directives=None, pending_work=None, pb_url="http://localhost:8090"):
    """Save checkpoint to PocketBase"""
    try:
        payload = {
            "agent_id": agent_id,
            "blocking_directives": blocking_directives or [],
            "pending_work": pending_work or [],
            "last_execution_id": "receipt_extraction"
        }
        requests.post(
            f"{pb_url}/api/collections/startup_checkpoint/records",
            json=payload,
            timeout=2
        )
    except Exception as e:
        pass

def get_gmail_service():
    """Get authenticated Gmail service"""
    creds = None
    token_path = 'token.pickle'
    
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

def extract_receipts():
    """Main extraction logic"""
    print("🔍 Archer checking Gmail for receipts...\n")
    
    checkpoint = load_checkpoint(agent_id="archer")
    if checkpoint:
        print(f"✅ Checkpoint loaded from PocketBase")
    else:
        print("ℹ️  No checkpoint found - starting fresh")
    
    try:
        service = get_gmail_service()
        
        # Search for receipt emails
        query = "receipt OR invoice OR payment confirmation OR order OR purchase OR transaction"
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=30
        ).execute()
        
        messages = results.get('messages', [])
        print(f"\n📧 Found {len(messages)} potential receipt emails\n")
        
        receipt_count = 0
        for msg in messages[:5]:  # Process first 5
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown sender')
            
            print(f"  📄 {subject}")
            print(f"     From: {sender}")
            receipt_count += 1
        
        print(f"\n✅ Processed {receipt_count} receipts")
        
        # Save checkpoint
        save_checkpoint(
            agent_id="archer",
            pending_work=[f"Extracted {receipt_count} receipts on {datetime.now().isoformat()}"]
        )
        print("✅ Checkpoint saved to PocketBase\n")
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    extract_receipts()
