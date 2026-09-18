# ────── Module: sync_incremental.py ───────────────────────────────────────
# ─── Sync incremental HubSpot → BD local usando hs_lastmodifieddate
# ─── Solo trae leads modificados desde el último sync exitoso
# ──────────────────────────────────────────────────────────────────────────

import os
import requests
from datetime import datetime, timezone

from models import db, Lead, User, GlobalSettings

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

PIPELINE_MAP = {
    "3784347861": "Leads Academy",
    "lead-pipeline-id": "Lead pipeline",
    "3837981938": "Mid-Market Leads",
    "3856712901": "Enterprise Leads",
}

STAGE_MAP = {
    "5300017355": "New (Leads Academy)",
    "5300017356": "Attempting (Leads Academy)",
    "5771994358": "Attempting 2 (Leads Academy)",
    "5771994359": "Attempting 3 (Leads Academy)",
    "5300017357": "Connected (Leads Academy)",
    "5433748684": "Contacto a Futuro (Leads Academy)",
    "5300017358": "Qualified (Leads Academy)",
    "5300017359": "Disqualified (Leads Academy)",
    "5404680415": "New (Mid-Market Leads)",
    "5404680416": "Attempting (Mid-Market Leads)",
    "5404720329": "Conversation (Mid-Market Leads)",
    "5476531421": "Hot (Mid-Market Leads)",
    "5404680418": "Qualified (Mid-Market Leads)",
    "5404680419": "Disqualified (Mid-Market Leads)",
    "5459584220": "New (Enterprise Leads)",
    "5459584221": "Attempting (Enterprise Leads)",
    "5459584223": "Conversation (Enterprise Leads)",
    "5490053342": "Hot (Enterprise Leads)",
    "5459584224": "Qualified (Enterprise Leads)",
    "5459584225": "Disqualified (Enterprise Leads)",
}

MARKET_MAPPING = {
    "ES": 1, "BR": 2, "PT": 2, "BRPT": 2,
    "FR": 3, "MX": 4, "LATAM": 4, "IT": 5,
}

HUBSPOT_LEAD_PROPERTIES = [
    "hs_lead_name", "sdr_who_manages", "hs_pipeline", "hs_pipeline_stage",
    "inbound_outbound", "hs_analytics_source_data_1", "hs_analytics_source",
    "industry", "market_hubspot", "hs_createdate", "hs_lastmodifieddate",
    "lead_priority_score",
]


def _parse_ts(raw):
    if not raw:
        return datetime.utcnow()
    try:
        if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
            return datetime.utcfromtimestamp(int(raw) / 1000.0)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _parse_score(raw):
    try:
        if raw in (None, ""):
            return 0
        return int(float(raw))
    except (ValueError, TypeError):
        return 0


def _do_sync(since_ts, max_pages=200):
    """
    Sincroniza leads modificados desde 'since_ts' (datetime naive UTC).
    Devuelve (imported, updated, skipped_academy, new_last_sync).
    new_last_sync es None si hubo error (para no actualizar el timestamp).
    """
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }

    url = "https://api.hubspot.com/crm/v3/objects/leads/search"

    since_ms = int(since_ts.replace(tzinfo=timezone.utc).timestamp() * 1000) if since_ts else 0

    after = None
    imported = 0
    updated = 0
    skipped_academy = 0
    pages = 0
    had_error = False

    user_map = {u.hubspot_user_id: u.id for u in User.query.all() if u.hubspot_user_id}

    while pages < max_pages:
        pages += 1
        body = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "hs_lastmodifieddate",
                    "operator": "GT",
                    "value": since_ms,
                }]
            }],
            "properties": HUBSPOT_LEAD_PROPERTIES,
            "limit": 100,
            "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "ASCENDING"}],
        }
        if after:
            body["after"] = after

        r = requests.post(url, headers=headers, json=body)
        if r.status_code != 200:
            print(f"❌ Error HubSpot search: {r.status_code} - {r.text[:300]}")
            had_error = True
            break

        data = r.json()
        results = data.get("results", [])

        for hs_lead in results:
            props = hs_lead.get("properties", {})
            raw_pipeline = props.get("hs_pipeline") or ""
            pipeline_name = PIPELINE_MAP.get(raw_pipeline, raw_pipeline or "Sin Pipeline")

            if raw_pipeline == "3784347861" or pipeline_name == "Leads Academy":
                skipped_academy += 1
                continue

            lead_id = str(hs_lead["id"])

            hs_market_code = (props.get("market_hubspot") or "").strip().upper()
            assigned_market_id = MARKET_MAPPING.get(hs_market_code, None)

            sdr_who = props.get("sdr_who_manages")
            local_user_id = user_map.get(sdr_who) if sdr_who else None

            raw_stage = props.get("hs_pipeline_stage") or ""
            stage_name = STAGE_MAP.get(raw_stage, raw_stage or "NEW")

            name = props.get("hs_lead_name") or f"Lead #{lead_id}"
            origin = props.get("inbound_outbound") or None
            first_source = props.get("hs_analytics_source_data_1")
            current_source = props.get("hs_analytics_source")
            vertical = props.get("industry")
            created_at_dt = _parse_ts(props.get("hs_createdate"))
            score_value = _parse_score(props.get("lead_priority_score"))

            existing = db.session.get(Lead, lead_id)

            if existing:
                existing.name = name
                existing.user_id = local_user_id
                existing.market_id = assigned_market_id
                existing.pipeline = pipeline_name
                existing.stage = stage_name
                existing.origin = origin
                existing.first_source_hubspot = first_source
                existing.current_source_hubspot = current_source
                existing.vertical = vertical
                existing.score = score_value
                existing.created_at = created_at_dt
                updated += 1
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
                    created_at=created_at_dt,
                )
                db.session.add(new_lead)
                imported += 1

        db.session.commit()

        paging = data.get("paging", {})
        after = paging.get("next", {}).get("after")
        if not after:
            break

    if had_error:
        return imported, updated, skipped_academy, None

    new_last_sync = datetime.utcnow()
    return imported, updated, skipped_academy, new_last_sync


def run_sync_incremental():
    """Asume que ya estás dentro de un app_context."""
    settings = GlobalSettings.query.first()
    if not settings:
        settings = GlobalSettings(automation_enabled=True)
        db.session.add(settings)
        db.session.commit()

    since = settings.last_sync_timestamp
    print(f"🔄 Sync incremental desde: {since or 'PRIMERA VEZ (todo)'}")

    imported, updated, skipped, new_ts = _do_sync(since)

    if new_ts is not None:
        settings.last_sync_timestamp = new_ts
        db.session.commit()
        print(f"✅ Sync completado: {imported} nuevos, {updated} actualizados, {skipped} Academy ignorados")
        print(f"   next last_sync_timestamp = {new_ts}")
    else:
        print(f"⚠️  Sync falló tras {imported} nuevos, {updated} actualizados, {skipped} Academy ignorados")
        print(f"   last_sync_timestamp NO actualizado (sigue en {since})")

    return imported + updated


if __name__ == "__main__":
    from app import app
    with app.app_context():
        run_sync_incremental()