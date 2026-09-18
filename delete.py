import os
import requests
from datetime import datetime

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

# 1. Obtener todos los leads TEST desde HubSpot
search_url = "https://api.hubspot.com/crm/v3/objects/leads/search"

body = {
    "filterGroups": [
        {
            "filters": [
                {
                    "propertyName": "hs_lead_name",
                    "operator": "CONTAINS_TOKEN",
                    "value": "TEST - Lead"
                }
            ]
        }
    ],
    "properties": [
        "hs_lead_name",
        "hs_pipeline",
        "hs_pipeline_stage",
        "inbound_outbound",
        "market_hubspot",
        "sdr_who_manages",
        "hs_createdate"
    ],
    "limit": 50
}

response = requests.post(search_url, headers=headers, json=body)

if response.status_code != 200:
    print(f"❌ Error buscando leads: {response.status_code} - {response.text}")
    exit()

leads = response.json().get("results", [])
print(f"📋 Leads TEST encontrados en HubSpot: {len(leads)}")

# 2. Importar a la BD local
from app import app
from models import db, Lead

with app.app_context():
    imported = 0
    updated = 0
    
    for hs_lead in leads:
        lead_id = hs_lead.get("id")
        props = hs_lead.get("properties", {})
        
        name = props.get("hs_lead_name", "")
        pipeline = props.get("hs_pipeline", "")
        stage = props.get("hs_pipeline_stage", "")
        origin = props.get("inbound_outbound", "")
        market_hubspot = props.get("market_hubspot", "")
        sdr_owner = props.get("sdr_who_manages", "")
        created_at_raw = props.get("hs_createdate", "")
        
        # Mapear market_code a ID
        MARKET_MAPPING = {"ES": 1, "BR": 2, "PT": 2, "BRPT": 2, "FR": 3, "MX": 4, "LATAM": 4, "IT": 5}
        market_id = MARKET_MAPPING.get(market_hubspot.upper(), None)
        
        # Mapear pipeline
        PIPELINE_MAP = {
            "3837981938": "Mid-Market",
            "3856712901": "Enterprise",
            "lead-pipeline-id": "Lead"
        }
        pipeline_name = PIPELINE_MAP.get(pipeline, pipeline)
        
        # Mapear stage
        STAGE_MAP = {
            "5404680415": "New (Mid-Market Leads)",
            "5404680416": "Attempting (Mid-Market Leads)",
        }
        stage_name = STAGE_MAP.get(stage, stage)
        
        # Parse created_at
        try:
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except:
            created_at = datetime.utcnow()
        
        # Verificar si ya existe
        existing = db.session.get(Lead, lead_id)
        
        if existing:
            existing.name = name
            existing.pipeline = pipeline_name
            existing.stage = stage_name
            existing.origin = origin
            existing.market_id = market_id
            existing.created_at = created_at
            updated += 1
        else:
            new_lead = Lead(
                id=lead_id,
                name=name,
                pipeline=pipeline_name,
                stage=stage_name,
                origin=origin,
                market_id=market_id,
                score=0,
                created_at=created_at,
                user_id=None
            )
            db.session.add(new_lead)
            imported += 1
    
    db.session.commit()
    print(f"✅ Leads importados: {imported}")
    print(f"✅ Leads actualizados: {updated}")