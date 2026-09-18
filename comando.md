Lead Disqualified al pool y en New:

```python
python3 -c "
from app import app
from models import db, Lead

with app.app_context():
    leads = Lead.query.filter(Lead.stage.ilike('%Disqualified%')).all()
    for lead in leads:
        lead.stage = 'New (Mid-Market Leads)'
        lead.user_id = None
    db.session.commit()
    print(f'✅ {len(leads)} leads Disqualified → New y al pool')
"
``



Todos los leads a new y pool
```python
python3 -c "
from app import app
from models import db, Lead, User

with app.app_context():
    michael = User.query.filter_by(hubspot_user_id='32695483').first()
    
    leads = Lead.query.filter(
        Lead.user_id == michael.id,
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%')
    ).limit(8).all()
    
    for lead in leads:
        lead.stage = 'New (Mid-Market Leads)'
        lead.user_id = None
        print(f'   ✅ {lead.id} → New y al pool')
    
    db.session.commit()
    
    current = Lead.query.filter(
        Lead.user_id == michael.id,
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%')
    ).count()
    print(f'Michael stock actual: {current}/{michael.max_stock}')
"
```

Quitar leads asignados y bajar a Michael al threshold

```python
python3 -c "
from app import app
from models import db, Lead, User

with app.app_context():
    michael = User.query.filter_by(hubspot_user_id='32695483').first()
    
    # Quitar 8 leads (dejar 2 para activar restock)
    leads = Lead.query.filter(
        Lead.user_id == michael.id,
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%')
    ).limit(8).all()
    
    for lead in leads:
        lead.stage = 'Disqualified (Mid-Market Leads)'
        lead.user_id = None
        print(f'   ❌ {lead.id} → Disqualified y al pool')
    
    db.session.commit()
    
    current = Lead.query.filter(
        Lead.user_id == michael.id,
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%')
    ).count()
    print(f'Michael stock actual: {current}/{michael.max_stock}')
"
```



# Crear Leads TEST

```python
import os
import requests
import time

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

# Usar el contacto ya existente
contact_id = "856517264628"
print(f"✅ Usando contacto existente: {contact_id}")

# Crear los leads asociados al contacto
leads_url = "https://api.hubspot.com/crm/v3/objects/leads"

created_count = 0

for i in range(1, 26):
    body = {
        "properties": {
            "hs_lead_name": f"TEST - Lead {i}",
            "hs_pipeline": "3837981938",
            "hs_pipeline_stage": "5404680415",
            "inbound_outbound": "Inbound",
            "sdr_who_manages": ""
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 578
                    }
                ]
            }
        ]
    }
    
    response = requests.post(leads_url, headers=headers, json=body)
    
    if response.status_code == 201:
        created_count += 1
        lead_id = response.json().get("id")
        print(f"✅ Lead {i} creado: {lead_id}")
    else:
        print(f"❌ Error al crear Lead {i}: {response.status_code} - {response.text[:150]}")
    
    time.sleep(0.2)

print(f"\n✅ Proceso completado: {created_count} leads TEST creados")
print(f"   Contacto asociado: {contact_id}")
``



### Limpiar TEST PRUEBAS DE HUSBPOT
```python
python3 -c "
import os, requests

HUBSPOT_TOKEN = os.getenv('HUBSPOT_TOKEN')
headers = {'Authorization': f'Bearer {HUBSPOT_TOKEN}', 'Content-Type': 'application/json'}

url = 'https://api.hubspot.com/crm/v3/objects/leads/search'
body = {
    'filterGroups': [{'filters': [{'propertyName': 'hs_lead_name', 'operator': 'CONTAINS_TOKEN', 'value': 'TEST - Lead'}]}],
    'properties': ['hs_lead_name', 'sdr_who_manages', 'hubspot_owner_id'],
    'limit': 100
}
resp = requests.post(url, headers=headers, json=body)
leads = resp.json().get('results', [])

for lead in leads:
    lead_id = lead.get('id')
    lead_name = lead.get('properties', {}).get('hs_lead_name', '')
    patch_url = f'https://api.hubspot.com/crm/v3/objects/leads/{lead_id}'
    patch_body = {'properties': {'sdr_who_manages': '', 'hubspot_owner_id': ''}}
    patch_resp = requests.patch(patch_url, headers=headers, json=patch_body)
    if patch_resp.status_code == 200:
        print(f'✅ {lead_id} | {lead_name} limpiado')
    else:
        print(f'❌ {lead_id} | {lead_name}: {patch_resp.status_code}')
"
```


### Quitar owners a leads en husbpot
```python
python3 -c "
import os
import requests

HUBSPOT_TOKEN = os.getenv('HUBSPOT_TOKEN')
headers = {'Authorization': f'Bearer {HUBSPOT_TOKEN}', 'Content-Type': 'application/json'}

# Obtener todos los leads TEST y TEST ENT y limpiar owner
search_url = 'https://api.hubspot.com/crm/v3/objects/leads/search'
body = {
    'filterGroups': [
        {
            'filters': [
                {
                    'propertyName': 'hs_lead_name',
                    'operator': 'CONTAINS_TOKEN',
                    'value': 'TEST - Lead'
                }
            ]
        }
    ],
    'properties': ['hs_lead_name', 'sdr_who_manages', 'hubspot_owner_id'],
    'limit': 100
}

resp = requests.post(search_url, headers=headers, json=body)
leads = resp.json().get('results', [])

for lead in leads:
    lead_id = lead.get('id')
    url = f'https://api.hubspot.com/crm/v3/objects/leads/{lead_id}'
    patch_body = {
        'properties': {
            'sdr_who_manages': '',
            'hubspot_owner_id': ''
        }
    }
    patch_resp = requests.patch(url, headers=headers, json=patch_body)
    if patch_resp.status_code == 200:
        print(f'✅ {lead_id} limpiado')
    else:
        print(f'❌ {lead_id}: {patch_resp.status_code}')
"
```



```python
```


```python
```


```python
```


```python
```


### FLUJO

## Flujo de distribución (con parada y reinicio):

1. **Verificar automatización global** → si OFF, terminar.

2. **Obtener SDRs que necesitan restock** (activos, con mercados activos, stock <= threshold).

3. **Obtener leads candidatos del pool local**.

4. **Para cada SDR que necesita restock:**
   - Calcular `space_to_fill`.
   - Obtener `market_ids` activos y `allowed_pipelines`.
   - Calcular `ent_space` y `mm_space` según `target_e_percent`.

5. **Separar candidatos ENT y MM.**

6. **Asignar ENT primero:**
   - Para cada lead ENT:
     - Fetch a HubSpot.
     - Actualizar BD local con datos frescos.
     - Validar.
     - Si validación **falla**:
       - **Actualizar BD local** con el lead.
       - **Parar la distribución completa**.
       - **Reiniciar desde el paso 1** (la BD ya está actualizada).
     - Si validación OK:
       - PATCH a HubSpot.
       - Asignar en BD local.

7. **Asignar MM después:**
   - Misma lógica.

8. **Commit final y log.**




proporcion de mercado para cada ususrio y para poder seleccioanr % de mercado.

si esta el core de lucas, ese
si no, formula de marta
crear en hubspot




JO