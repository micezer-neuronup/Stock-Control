import os
import sys
import requests
from datetime import datetime

# Añade la raíz del proyecto para importar app y models
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app
from models import db, Lead, User, Market

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

# ⚙️ CONFIGURACIÓN DE PRUEBAS
MAX_LEADS = None  

# 🗺️ Mapeo de Pipelines
PIPELINE_MAP = {
    "3784347861": "Leads Academy",
    "lead-pipeline-id": "Lead pipeline",
    "3837981938": "Mid-Market Leads",
    "3856712901": "Enterprise Leads"
}

# 🗺️ Mapeo Completo de Stages
STAGE_MAP = {
    # LEADS ACADEMY
    "5300017355": "New (Leads Academy)",
    "5300017356": "Attempting (Leads Academy)",
    "5771994358": "Attempting 2 (Leads Academy)",
    "5771994359": "Attempting 3 (Leads Academy)",
    "5300017357": "Connected (Leads Academy)",
    "5433748684": "Contacto a Futuro (Leads Academy)",
    "5300017358": "Qualified (Leads Academy)",
    "5300017359": "Disqualified (Leads Academy)",

    # LEAD PIPELINE
    "new-stage-id": "New (Lead pipeline)",
    "attempting-stage-id": "Attempting (Lead pipeline)",
    "connected-stage-id": "Connected (Lead pipeline)",
    "qualified-stage-id": "Qualified (Lead pipeline)",
    "unqualified-stage-id": "Disqualified (Lead pipeline)",

    # MID-MARKET LEADS
    "5404680415": "New (Mid-Market Leads)",
    "5404680416": "Attempting (Mid-Market Leads)",
    "5404720329": "Conversation (Mid-Market Leads)",
    "5476531421": "Hot (Mid-Market Leads)",
    "5404680418": "Qualified (Mid-Market Leads)",
    "5404680419": "Disqualified (Mid-Market Leads)",

    # ENTERPRISE LEADS
    "5459584220": "New (Enterprise Leads)",
    "5459584221": "Attempting (Enterprise Leads)",
    "5459584223": "Conversation (Enterprise Leads)",
    "5490053342": "Hot (Enterprise Leads)",
    "5459584224": "Qualified (Enterprise Leads)",
    "5459584225": "Disqualified (Enterprise Leads)",
}

HUBSPOT_LEAD_PROPERTIES = [
    "hs_lead_name",
    "sdr_who_manages",
    "hs_pipeline",
    "hs_pipeline_stage",
    "inbound_outbound",
    "hs_analytics_source_data_1",
    "hs_analytics_source",
    "industry",
    "market_hubspot",
    "hs_createdate",
    "lead_priority_score",
]

MARKET_MAPPING = {
    "ES": 1,         
    "BR": 2,         
    "PT": 2,
    "BRPT": 2,       
    "FR": 3,         
    "MX": 4,         
    "LATAM": 4,      
    "IT": 5          
}


def parse_hubspot_timestamp(raw_time):
    if not raw_time:
        return datetime.utcnow()
    try:
        if isinstance(raw_time, int) or (isinstance(raw_time, str) and raw_time.isdigit()):
            return datetime.utcfromtimestamp(int(raw_time) / 1000.0)
        return datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


def parse_score(raw):
    try:
        if raw in (None, ""):
            return 0
        return int(float(raw))
    except (ValueError, TypeError):
        return 0


def fetch_and_import_leads():
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }
    
    url = "https://api.hubspot.com/crm/v3/objects/leads"
    
    with app.app_context():
        print("🔍 Cargando mapa de usuarios...")
        
        users = User.query.all()
        user_map = {user.hubspot_user_id: user.id for user in users if user.hubspot_user_id}

        has_more = True
        after = None
        imported_count = 0
        updated_count = 0
        skipped_academy_count = 0

        limit_info = f"Objetivo: {MAX_LEADS} leads válidos" if MAX_LEADS else "Modo COMPLETO"
        print(f"🚀 Importando leads desde HubSpot ({limit_info})...")

        while has_more:
            params = {
                "limit": 50,
                "properties": ",".join(HUBSPOT_LEAD_PROPERTIES),
            }
            if after:
                params["after"] = after

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                print(f"❌ Error API HubSpot ({response.status_code}): {response.text}")
                break

            data = response.json()
            results = data.get("results", [])

            for hs_lead in results:
                props = hs_lead.get("properties", {})
                
                raw_pipeline = props.get("hs_pipeline") or ""
                pipeline_name = PIPELINE_MAP.get(raw_pipeline, raw_pipeline or "Sin Pipeline")

                if raw_pipeline == "3784347861" or pipeline_name == "Leads Academy":
                    skipped_academy_count += 1
                    continue

                lead_id = str(hs_lead["id"])

                # Mercado
                hs_market_code = (props.get("market_hubspot") or "").strip().upper()
                assigned_market_id = MARKET_MAPPING.get(hs_market_code, None)

                # SDR que gestiona el lead
                sdr_who_manages = props.get("sdr_who_manages")
                local_user_id = user_map.get(sdr_who_manages) if sdr_who_manages else None

                raw_stage = props.get("hs_pipeline_stage") or ""
                stage_name = STAGE_MAP.get(raw_stage, raw_stage or "NEW")

                name = props.get("hs_lead_name") or f"Lead #{lead_id}"
                origin = props.get("inbound_outbound") or None
                first_source = props.get("hs_analytics_source_data_1")
                current_source = props.get("hs_analytics_source")
                vertical = props.get("industry")
                score_value = parse_score(props.get("lead_priority_score"))

                existing_lead = db.session.get(Lead, lead_id)
                created_at_dt = parse_hubspot_timestamp(props.get("hs_createdate"))

                if existing_lead:
                    existing_lead.name = name
                    existing_lead.user_id = local_user_id
                    existing_lead.market_id = assigned_market_id
                    existing_lead.pipeline = pipeline_name
                    existing_lead.stage = stage_name
                    existing_lead.origin = origin
                    existing_lead.first_source_hubspot = first_source
                    existing_lead.current_source_hubspot = current_source
                    existing_lead.vertical = vertical
                    existing_lead.score = score_value
                    existing_lead.created_at = created_at_dt
                    updated_count += 1
                else:
                    new_lead = Lead(
                        id=lead_id,
                        name=name,
                        market_id=assigned_market_id,
                        user_id=local_user_id,
                        pipeline=pipeline_name,
                        stage=stage_name,
                        origin=origin,
                        first_source_hubspot=first_source,
                        current_source_hubspot=current_source,
                        vertical=vertical,
                        score=score_value,
                        created_at=created_at_dt
                    )
                    db.session.add(new_lead)
                    imported_count += 1

                valid_saved = imported_count + updated_count
                if MAX_LEADS is not None and valid_saved >= MAX_LEADS:
                    break

            db.session.commit()

            valid_saved = imported_count + updated_count
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            has_more = bool(after) and (MAX_LEADS is None or valid_saved < MAX_LEADS)

        print(f"\n✅ Importación completada:")
        print(f"   - Leads VÁLIDOS guardados: {imported_count + updated_count} (Nuevos: {imported_count}, Actualizados: {updated_count})")
        print(f"   - Leads ignorados de Academy: {skipped_academy_count}")


if __name__ == "__main__":
    fetch_and_import_leads()