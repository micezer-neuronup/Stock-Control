import os, requests, time, uuid

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}

# 1. Borrar los 2 leads actuales
lead_ids = ["...", "..."]  # los IDs que te salieron
for lid in lead_ids:
    r = requests.delete(f"https://api.hubapi.com/crm/v3/objects/leads/{lid}", headers=headers)
    print(f"delete {lid}: {r.status_code}")

# 2. Crear contacto con email único
email = f"test.brasil.{uuid.uuid4().hex[:8]}@example-test-br.com"
r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, json={
    "properties": {
        "firstname": "TEST",
        "lastname": "Contacto Brasil",
        "email": email,
        "country": "Brazil"
    }
})
print(f"contacto: {r.status_code} {r.text[:200]}")
contact_id = r.json().get("id")
print(f"contact_id = {contact_id} (email={email})")

# 3. Crear 2 leads nuevos
for i in [1, 2]:
    body = {
        "properties": {
            "hs_lead_name": f"TEST - Lead Brasil {i}",
            "hs_pipeline": "3837981938",
            "hs_pipeline_stage": "5404680415",
            "inbound_outbound": "Inbound",
            "sdr_who_manages": ""
        },
        "associations": [
            {"to": {"id": contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 578}]}
        ]
    }
    r = requests.post("https://api.hubapi.com/crm/v3/objects/leads", headers=headers, json=body)
    if r.status_code == 201:
        print(f"lead {i}: {r.json().get('id')}")
    else:
        print(f"lead {i} error: {r.status_code} {r.text[:200]}")
    time.sleep(0.3)