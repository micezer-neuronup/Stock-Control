# ────── Module: automation.py ──────────────────────────────────────────────
# ─── Automatización de distribución de leads con integración HubSpot
# ─── Si detecta cambios relevantes, para y reinicia la distribución
# ──────────────────────────────────────────────────────────────────────────

import os
import requests
from datetime import datetime
from models import db, User, Lead, Market, GlobalSettings, UserMarketTarget
from sqlalchemy import func

# ----------------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------------
EXCLUDED_STAGES = ['Disqualified', 'Qualified']
EXCLUDED_PIPELINES = ['Leads Academy']

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")

PIPELINE_MAP = {
    "3837981938": "Mid-Market",
    "3856712901": "Enterprise",
    "lead-pipeline-id": "Lead",
}

STAGE_MAP = {
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

MARKET_MAPPING = {"ES": 1, "BR": 2, "PT": 2, "BRPT": 2, "FR": 3, "MX": 4, "LATAM": 4, "IT": 5, "US": 6}

COLORS = {
    "reset": "\x1b[0m",
    "gray": "\x1b[90m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "cyan": "\x1b[36m",
}


def get_timestamp():
    now = datetime.utcnow()
    return now.strftime("%Y-%m-%d %H:%M:%S")


def log(level, context, message, meta=None):
    timestamp = get_timestamp()
    meta_str = ""
    if meta:
        meta_str = " | " + " ".join([f"{k}={v}" for k, v in meta.items()])
    
    color_map = {
        "INFO": COLORS["green"],
        "WARN": COLORS["yellow"],
        "ERROR": COLORS["red"],
        "DEBUG": COLORS["gray"],
    }
    color = color_map.get(level, COLORS["reset"])
    
    line = (
        f"{COLORS['gray']}[{timestamp}]{COLORS['reset']} "
        f"{color}[{level}]{COLORS['reset']} "
        f"[{context}] {message}{meta_str}"
    )
    
    print(line)


def is_global_automation_enabled():
    setting = GlobalSettings.query.first()
    return setting.automation_enabled if setting else True


def get_sdr_current_stock(sdr_id):
    return db.session.query(func.count(Lead.id)).filter(
        Lead.user_id == sdr_id,
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%'),
        ~Lead.pipeline.ilike('%Leads Academy%')
    ).scalar() or 0


def get_sdr_available_space_to_fill(sdr):
    current_stock = get_sdr_current_stock(sdr.id)
    return max(0, (sdr.max_stock or 10) - current_stock)


def sdr_needs_restock(sdr):
    current_stock = get_sdr_current_stock(sdr.id)
    threshold = sdr.restock_threshold if sdr.restock_threshold is not None else 0
    return current_stock <= threshold


def get_sdrs_needing_restock():
    if not is_global_automation_enabled():
        log("WARN", "automation", "Automatización global desactivada")
        return []
    
    sdrs = User.query.filter(User.automation_enabled == True).all()
    
    result = []
    for sdr in sdrs:
        active_markets = [m for m in sdr.markets if m.automation_enabled]
        if not active_markets:
            log("DEBUG", "automation", "SDR sin mercados activos", {"name": sdr.name})
            continue
        if sdr_needs_restock(sdr):
            result.append(sdr)
    
    return result


def get_candidate_leads_from_pool():
    return Lead.query.filter(
        (Lead.raw_owner.is_(None)) | (Lead.raw_owner == ''),
        Lead.market_id.isnot(None),
        Lead.score.isnot(None),
        Lead.segment.isnot(None),
        Lead.vertical.ilike('%NeuronUP%'),
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%'),
        ~Lead.pipeline.ilike('%Leads Academy%'),
    ).order_by(Lead.score.desc()).all()


def get_sdr_allowed_pipelines(sdr):
    if sdr.allowed_pipelines:
        return sdr.allowed_pipelines
    return []


def get_hubspot_lead(lead_id, headers):
    url = f"https://api.hubspot.com/crm/v3/objects/leads/{lead_id}"
    params = {
        "properties": "hs_lead_name,hs_pipeline,hs_pipeline_stage,inbound_outbound,market_hubspot,sdr_who_manages,hs_createdate"
    }
    
    log("DEBUG", "hubspot", "Fetch lead desde HubSpot", {"lead_id": lead_id})
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        log("ERROR", "hubspot", "Error al obtener lead de HubSpot", {
            "lead_id": lead_id,
            "status": response.status_code
        })
        return None
    
    log("DEBUG", "hubspot", "Fetch OK", {"lead_id": lead_id})
    return response.json()


def update_hubspot_lead_owner(lead_id, sdr_hubspot_user_id, headers):
    url = f"https://api.hubspot.com/crm/v3/objects/leads/{lead_id}"
    body = {
        "properties": {
            "sdr_who_manages": sdr_hubspot_user_id
        }
    }
    
    log("DEBUG", "hubspot", "PATCH sdr_who_manages en HubSpot", {
        "lead_id": lead_id,
        "sdr_hubspot_id": sdr_hubspot_user_id
    })
    
    response = requests.patch(url, headers=headers, json=body)
    
    if response.status_code == 200:
        log("INFO", "hubspot", "PATCH exitoso", {"lead_id": lead_id})
        return True
    else:
        log("ERROR", "hubspot", "PATCH fallido", {
            "lead_id": lead_id,
            "status": response.status_code,
            "response": response.text[:200]
        })
        return False


def assign_lead_to_sdr(lead_id, sdr_id):
    lead = db.session.get(Lead, lead_id)
    if lead:
        lead.user_id = sdr_id
        lead.last_updated = datetime.utcnow()
        log("DEBUG", "distribution", "Lead asignado en BD local", {"lead_id": lead_id, "sdr_id": sdr_id})
        return True
    return False


def update_local_lead_from_hubspot(lead, props):
    lead.name = props.get("hs_lead_name", lead.name)
    lead.origin = props.get("inbound_outbound", lead.origin)
    
    pipeline_id = props.get("hs_pipeline") or ""
    pipeline_name = PIPELINE_MAP.get(pipeline_id, pipeline_id)
    lead.pipeline = pipeline_name
    
    stage_id = props.get("hs_pipeline_stage") or ""
    stage_name = STAGE_MAP.get(stage_id, stage_id)
    lead.stage = stage_name
    
    market_hubspot = props.get("market_hubspot") or ""
    market_id = MARKET_MAPPING.get(market_hubspot.upper(), None)
    lead.market_id = market_id
    
    sdr_owner = props.get("sdr_who_manages")
    if sdr_owner:
        local_sdr = User.query.filter_by(hubspot_user_id=sdr_owner).first()
        if local_sdr:
            lead.user_id = local_sdr.id
            log("DEBUG", "distribution", "Lead actualizado con SDR de HubSpot", {
                "lead_id": lead.id,
                "sdr": local_sdr.name
            })
    
    log("DEBUG", "distribution", "BD local actualizada con datos frescos", {
        "lead_id": lead.id,
        "pipeline": pipeline_name,
        "stage": stage_name,
        "market_id": market_id
    })
    
    return lead


# ────── Funciones nuevas: objetivos por mercado ──────────────────────────

def get_market_targets(sdr):
    """
    Devuelve dict {market_id: percent} si el SDR tiene config válida, o None si no.
    Solo incluye mercados que el SDR tiene asignados actualmente.
    """
    targets = UserMarketTarget.query.filter_by(user_id=sdr.id).all()
    if not targets:
        return None
    
    assigned_market_ids = {m.id for m in sdr.markets}
    result = {
        t.market_id: t.target_percent
        for t in targets
        if t.market_id in assigned_market_ids
    }
    
    # Si tras filtrar no queda nada o no suma 100, no hay config válida
    if not result or sum(result.values()) != 100:
        return None
    
    return result


def compute_market_objectives(sdr):
    """
    Devuelve {market_id: target_count}.
    
    - Si hay config válida: reparte max_stock según %.
    - Si no: reparto equitativo entre mercados asignados.
    - Residuo del redondeo se asigna al mercado con mayor decimal.
    """
    assigned_markets = [m.id for m in sdr.markets if m.automation_enabled]
    if not assigned_markets:
        return {}
    
    max_stock = sdr.max_stock or 10
    targets_config = get_market_targets(sdr)
    
    if targets_config is None:
        # Reparto equitativo
        n = len(assigned_markets)
        base = max_stock // n
        remainder = max_stock % n
        result = {}
        for i, mid in enumerate(assigned_markets):
            result[mid] = base + (1 if i < remainder else 0)
        return result
    
    # Reparto según %
    exact = {}
    for mid in assigned_markets:
        pct = targets_config.get(mid, 0)
        exact[mid] = (pct / 100) * max_stock
    
    # Floor + residuo al de mayor decimal
    floored = {mid: int(v) for mid, v in exact.items()}
    assigned_total = sum(floored.values())
    remainder = max_stock - assigned_total
    
    if remainder > 0:
        sorted_markets = sorted(
            assigned_markets,
            key=lambda mid: (exact[mid] - floored[mid], targets_config.get(mid, 0)),
            reverse=True
        )
        for i in range(remainder):
            floored[sorted_markets[i % len(sorted_markets)]] += 1
    
    return floored


def compute_market_currents(sdr):
    """
    Devuelve {market_id: current_count} de leads vivos del SDR por mercado.
    """
    assigned_markets = [m.id for m in sdr.markets if m.automation_enabled]
    if not assigned_markets:
        return {}
    
    rows = db.session.query(
        Lead.market_id, func.count(Lead.id)
    ).filter(
        Lead.user_id == sdr.id,
        Lead.market_id.in_(assigned_markets),
        ~Lead.stage.ilike('%Disqualified%'),
        ~Lead.stage.ilike('%Qualified%'),
        ~Lead.pipeline.ilike('%Leads Academy%')
    ).group_by(Lead.market_id).all()
    
    currents = {mid: 0 for mid in assigned_markets}
    for mid, count in rows:
        currents[mid] = count
    return currents


def compute_market_spaces(sdr):
    """
    Devuelve {market_id: space_pendiente} para mercados con objetivo > 0.
    """
    objectives = compute_market_objectives(sdr)
    currents = compute_market_currents(sdr)
    
    spaces = {}
    for mid, target_count in objectives.items():
        current = currents.get(mid, 0)
        space = max(0, target_count - current)
        if space > 0:
            spaces[mid] = space
    
    return spaces


# ────── Distribución principal ───────────────────────────────────────────

def run_distribution():
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }
    
    log("INFO", "distribution", "Iniciando distribución automática de leads")
    
    sdrs_needing = get_sdrs_needing_restock()
    
    if not sdrs_needing:
        log("INFO", "distribution", "Ningún SDR necesita restock")
        return 0
    
    log("INFO", "distribution", f"SDRs que necesitan restock: {len(sdrs_needing)}")
    for sdr in sdrs_needing:
        current = get_sdr_current_stock(sdr.id)
        threshold = sdr.restock_threshold if sdr.restock_threshold is not None else 0
        log("DEBUG", "distribution", "SDR candidato", {
            "name": sdr.name,
            "stock": f"{current}/{sdr.max_stock}",
            "threshold": threshold
        })
    
    candidates = get_candidate_leads_from_pool()
    log("INFO", "distribution", f"Leads candidatos en pool: {len(candidates)}")
    
    if not candidates:
        log("WARN", "distribution", "No hay leads en el pool para asignar")
        return 0
    
    total_assigned = 0
    restart_needed = False
    
    for sdr in sdrs_needing:
        if restart_needed:
            break
        
        space_to_fill = get_sdr_available_space_to_fill(sdr)
        
        if space_to_fill <= 0:
            log("DEBUG", "distribution", "SDR sin espacio", {"name": sdr.name})
            continue
        
        allowed_pipelines = get_sdr_allowed_pipelines(sdr)
        if not allowed_pipelines:
            log("WARN", "distribution", "SDR sin pipelines permitidos", {"name": sdr.name})
            continue
        
        # ─── Cálculos por mercado ────────────────────────────────────────
        market_spaces = compute_market_spaces(sdr)
        
        if not market_spaces:
            log("WARN", "distribution", "SDR sin huecos por mercado", {"name": sdr.name})
            continue
        
        log("INFO", "distribution", "Objetivos por mercado", {
            "name": sdr.name,
            "spaces": dict(market_spaces)
        })
        
        # ─── Ratio ENT/MM global ─────────────────────────────────────────
        current_stock = get_sdr_current_stock(sdr.id)
        current_ent = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == sdr.id,
            Lead.pipeline.ilike('%Enterprise%'),
            ~Lead.stage.ilike('%Disqualified%'),
            ~Lead.stage.ilike('%Qualified%')
        ).scalar() or 0
        
        target_ent_percent = sdr.target_e_percent
        
        if target_ent_percent is not None:
            target_ent_total = round((target_ent_percent / 100) * (sdr.max_stock or 10))
            target_mm_total = (sdr.max_stock or 10) - target_ent_total
            log("INFO", "distribution", "Objetivo ENT definido", {
                "name": sdr.name,
                "target_ent": f"{target_ent_percent}%",
                "current_ent": current_ent,
                "current_stock": current_stock,
                "target_ent_total": target_ent_total,
                "target_mm_total": target_mm_total
            })
        else:
            target_ent_total = None
            target_mm_total = None
            log("INFO", "distribution", "Sin objetivo ENT, reparto normal", {"name": sdr.name})
        
        assigned_ent = 0
        assigned_mm = 0
        
        # ─── Objetivos ENT/MM POR MERCADO ────────────────────────────────
        market_ent_targets = {}
        market_mm_targets = {}
        for mid, space in market_spaces.items():
            if target_ent_percent is not None:
                ent_t = round((target_ent_percent / 100) * space)
                market_ent_targets[mid] = ent_t
                market_mm_targets[mid] = space - ent_t
            else:
                market_ent_targets[mid] = space
                market_mm_targets[mid] = space
        
        # Contadores ENT/MM por mercado (asignados en este ciclo)
        assigned_ent_market = {mid: 0 for mid in market_spaces}
        assigned_mm_market = {mid: 0 for mid in market_spaces}
        
        # Stock actual ENT/MM por mercado
        current_ent_market = {}
        current_mm_market = {}
        _all_currents = compute_market_currents(sdr)
        for mid in market_spaces:
            ce = db.session.query(func.count(Lead.id)).filter(
                Lead.user_id == sdr.id,
                Lead.market_id == mid,
                Lead.pipeline.ilike('%Enterprise%'),
                ~Lead.stage.ilike('%Disqualified%'),
                ~Lead.stage.ilike('%Qualified%')
            ).scalar() or 0
            current_ent_market[mid] = ce
            current_mm_market[mid] = _all_currents.get(mid, 0) - ce
        
        log("INFO", "distribution", "Objetivos ENT/MM por mercado", {
            "name": sdr.name,
            "ent_targets": dict(market_ent_targets),
            "mm_targets": dict(market_mm_targets),
            "ent_current": dict(current_ent_market),
            "mm_current": dict(current_mm_market)
        })
        
        # ─── Helper: candidatos por mercado ──────────────────────────────
        def get_candidates_for_market(mid):
            ent = [
                l for l in candidates
                if l.user_id is None
                and l.market_id == mid
                and 'Enterprise' in (l.pipeline or '')
                and 'Enterprise' in allowed_pipelines
            ]
            mm = [
                l for l in candidates
                if l.user_id is None
                and l.market_id == mid
                and 'Mid-Market' in (l.pipeline or '')
                and 'Mid-Market' in allowed_pipelines
            ]
            ent.sort(key=lambda l: l.score, reverse=True)
            mm.sort(key=lambda l: l.score, reverse=True)
            return ent, mm
        
        # ─── Helper: ¿toca ENT o MM en ESTE mercado? ────────────────────
        def needs_ent(mid):
            if target_ent_percent is None:
                return True
            ent_acum = current_ent_market.get(mid, 0) + assigned_ent_market.get(mid, 0)
            mm_acum = current_mm_market.get(mid, 0) + assigned_mm_market.get(mid, 0)
            ent_target = market_ent_targets.get(mid, 0)
            mm_target = market_mm_targets.get(mid, 0)
            if ent_acum < ent_target:
                return True
            if mm_acum < mm_target:
                return False
            return True
        
        # ─── Helper: procesar un lead ────────────────────────────────────
        def process_lead(lead, is_ent):
            nonlocal total_assigned, restart_needed, candidates
            nonlocal space_to_fill, current_stock, current_ent, assigned_ent, assigned_mm
            nonlocal market_spaces
            nonlocal target_ent_total, target_mm_total
            nonlocal market_ent_targets, market_mm_targets
            
            hs_lead = get_hubspot_lead(lead.id, headers)
            if not hs_lead:
                return 'skipped'
            
            props = hs_lead.get("properties", {})
            update_local_lead_from_hubspot(lead, props)
            
            stage_id = props.get("hs_pipeline_stage") or ""
            stage_name = STAGE_MAP.get(stage_id, stage_id)
            sdr_owner = props.get("sdr_who_manages")
            pipeline_id = props.get("hs_pipeline") or ""
            pipeline_name = PIPELINE_MAP.get(pipeline_id, pipeline_id)
            
            validation_errors = []
            if 'Disqualified' in stage_name or 'Qualified' in stage_name:
                validation_errors.append(f"Stage excluido: {stage_name}")
            if 'Leads Academy' in pipeline_id:
                validation_errors.append("Pipeline Academy")
            if pipeline_name not in allowed_pipelines:
                validation_errors.append(f"Pipeline {pipeline_name} no permitido")
            
            # ─── Caso 1: lead ya tiene SDR en HubSpot ───────────────────
            if sdr_owner:
                if sdr_owner == sdr.hubspot_user_id:
                    log("INFO", "distribution", "Lead ya asignado a este SDR en HubSpot, sincronizado", {
                        "lead_id": lead.id,
                        "sdr": sdr.name
                    })
                    
                    current_stock = get_sdr_current_stock(sdr.id)
                    current_ent = db.session.query(func.count(Lead.id)).filter(
                        Lead.user_id == sdr.id,
                        Lead.pipeline.ilike('%Enterprise%'),
                        ~Lead.stage.ilike('%Disqualified%'),
                        ~Lead.stage.ilike('%Qualified%')
                    ).scalar() or 0
                    space_to_fill = max(0, (sdr.max_stock or 10) - current_stock)
                    
                    # Recalcular market_spaces y objetivos por mercado
                    market_spaces = compute_market_spaces(sdr)
                    
                    # Recalcular currents y targets por mercado
                    _all_currents2 = compute_market_currents(sdr)
                    for m in market_spaces:
                        ce = db.session.query(func.count(Lead.id)).filter(
                            Lead.user_id == sdr.id,
                            Lead.market_id == m,
                            Lead.pipeline.ilike('%Enterprise%'),
                            ~Lead.stage.ilike('%Disqualified%'),
                            ~Lead.stage.ilike('%Qualified%')
                        ).scalar() or 0
                        current_ent_market[m] = ce
                        current_mm_market[m] = _all_currents2.get(m, 0) - ce
                    
                    new_ent_targets = {}
                    new_mm_targets = {}
                    for m, sp in market_spaces.items():
                        if target_ent_percent is not None:
                            et = round((target_ent_percent / 100) * sp)
                            new_ent_targets[m] = et
                            new_mm_targets[m] = sp - et
                        else:
                            new_ent_targets[m] = sp
                            new_mm_targets[m] = sp
                    market_ent_targets = new_ent_targets
                    market_mm_targets = new_mm_targets
                    
                    for m in market_spaces:
                        assigned_ent_market.setdefault(m, 0)
                        assigned_mm_market.setdefault(m, 0)
                    
                    if target_ent_percent is not None:
                        target_ent_total = round((target_ent_percent / 100) * (sdr.max_stock or 10))
                        target_mm_total = (sdr.max_stock or 10) - target_ent_total
                    
                    log("INFO", "distribution", "Recalculado tras sync", {
                        "lead_id": lead.id,
                        "stock": f"{current_stock}/{sdr.max_stock}",
                        "space_to_fill": space_to_fill,
                        "market_spaces": dict(market_spaces),
                        "ent_targets": dict(market_ent_targets)
                    })
                    
                    if space_to_fill <= assigned_ent + assigned_mm:
                        log("WARN", "distribution", "SDR lleno tras sincronización, cortando ciclo", {
                            "name": sdr.name,
                            "stock": f"{current_stock}/{sdr.max_stock}",
                            "assigned_this_cycle": assigned_ent + assigned_mm
                        })
                        return 'stop_sdr'
                    
                    return 'skipped'
                else:
                    log("WARN", "distribution", "Conflicto con otro SDR, reiniciando", {
                        "lead_id": lead.id,
                        "sdr_hubspot": sdr_owner,
                        "sdr_esperado": sdr.hubspot_user_id
                    })
                    db.session.commit()
                    restart_needed = True
                    return 'restart'
            
            # ─── Caso 2: otros errores de validación ────────────────────
            if validation_errors:
                log("INFO", "distribution", "Lead descartado", {
                    "lead_id": lead.id,
                    "razones": "; ".join(validation_errors)
                })
                return 'skipped'
            
            # ─── Caso 3: validación OK → asignar ────────────────────────
            log("INFO", "distribution", "Validación exitosa", {
                "lead_id": lead.id,
                "pipeline": pipeline_name,
                "market": lead.market_id
            })
            
            if not update_hubspot_lead_owner(lead.id, sdr.hubspot_user_id, headers):
                return 'skipped'
            
            if assign_lead_to_sdr(lead.id, sdr.id):
                total_assigned += 1
                log("INFO", "distribution", f"Lead {'ENT' if is_ent else 'MM'} asignado", {
                    "lead_id": lead.id,
                    "sdr": sdr.name,
                    "score": lead.score,
                    "pipeline": pipeline_name,
                    "market_id": lead.market_id
                })
                return 'assigned'
            return 'skipped'
        
        # ─── Bucle intercalado por mercados ─────────────────────────────
        max_iterations = 1000
        iteration = 0
        stop_sdr = False
        
        while market_spaces and iteration < max_iterations and not stop_sdr:
            iteration += 1
            
            active_markets = sorted(
                [mid for mid, sp in market_spaces.items() if sp > 0],
                key=lambda mid: market_spaces[mid],
                reverse=True
            )
            
            if not active_markets:
                break
            
            progressed = False
            
            for mid in active_markets:
                if market_spaces.get(mid, 0) <= 0:
                    continue
                
                ent_cands, mm_cands = get_candidates_for_market(mid)
                prefer_ent = needs_ent(mid)
                
                chosen = None
                is_ent = False
                
                if prefer_ent:
                    if ent_cands:
                        chosen = ent_cands[0]; is_ent = True
                    else:
                        # No hay ENT en este mercado.
                        # Solo caemos a MM si aún no hemos cubierto el cupo MM de este mercado.
                        mm_acum = current_mm_market.get(mid, 0) + assigned_mm_market.get(mid, 0)
                        mm_target = market_mm_targets.get(mid, 0)
                        if mm_cands and mm_acum < mm_target:
                            chosen = mm_cands[0]; is_ent = False
                        else:
                            # Dejamos hueco para relleno
                            continue
                else:
                    if mm_cands:
                        chosen = mm_cands[0]; is_ent = False
                    else:
                        # No hay MM en este mercado.
                        # Solo caemos a ENT si aún no hemos cubierto el cupo ENT de este mercado.
                        ent_acum = current_ent_market.get(mid, 0) + assigned_ent_market.get(mid, 0)
                        ent_target = market_ent_targets.get(mid, 0)
                        if ent_cands and ent_acum < ent_target:
                            chosen = ent_cands[0]; is_ent = True
                        else:
                            continue
                
                if chosen is None:
                    continue
                
                result = process_lead(chosen, is_ent)
                
                if result == 'restart':
                    stop_sdr = True
                    break
                elif result == 'stop_sdr':
                    stop_sdr = True
                    break
                elif result == 'assigned':
                    market_spaces[mid] -= 1
                    if is_ent:
                        assigned_ent += 1
                        assigned_ent_market[mid] = assigned_ent_market.get(mid, 0) + 1
                    else:
                        assigned_mm += 1
                        assigned_mm_market[mid] = assigned_mm_market.get(mid, 0) + 1
                    progressed = True
                    candidates = [l for l in candidates if l.user_id is None]
                elif result == 'skipped':
                    candidates = [l for l in candidates if l.id != chosen.id]
            
            if restart_needed or stop_sdr:
                break
            
            if not progressed:
                break
        
        if restart_needed:
            break
        
        # ─── Relleno: si queda hueco real, seguir asignando ─────────────
        # Ignora objetivo por mercado, respeta el target_e_percent GLOBAL.
        def compute_remaining_space():
            return max(0, space_to_fill - assigned_ent - assigned_mm)
        
        def needs_ent_global():
            if target_ent_total is None:
                return True
            ent_total = current_ent + assigned_ent
            mm_total = (current_stock - current_ent) + assigned_mm
            if ent_total < target_ent_total:
                return True
            if mm_total < target_mm_total:
                return False
            return True
        
        fill_markets = [m.id for m in sdr.markets if m.automation_enabled]
        
        while compute_remaining_space() > 0 and not stop_sdr:
            all_ent = []
            all_mm = []
            for mid in fill_markets:
                e, m = get_candidates_for_market(mid)
                all_ent.extend(e)
                all_mm.extend(m)
            all_ent.sort(key=lambda l: l.score, reverse=True)
            all_mm.sort(key=lambda l: l.score, reverse=True)
            
            prefer_ent = needs_ent_global()
            chosen = None
            is_ent = False
            
            if prefer_ent:
                if all_ent:
                    chosen = all_ent[0]; is_ent = True
                elif all_mm:
                    chosen = all_mm[0]; is_ent = False
            else:
                if all_mm:
                    chosen = all_mm[0]; is_ent = False
                elif all_ent:
                    chosen = all_ent[0]; is_ent = True
            
            if chosen is None:
                break
            
            result = process_lead(chosen, is_ent)
            if result == 'restart':
                stop_sdr = True
                break
            elif result == 'stop_sdr':
                stop_sdr = True
                break
            elif result == 'assigned':
                if is_ent:
                    assigned_ent += 1
                else:
                    assigned_mm += 1
                candidates = [l for l in candidates if l.user_id is None]
            elif result == 'skipped':
                candidates = [l for l in candidates if l.id != chosen.id]
        
        if restart_needed:
            break
        
        # Refrescar pool global al final del SDR
        candidates = [l for l in candidates if l.user_id is None]
    
    db.session.commit()
    
    if restart_needed:
        log("INFO", "distribution", "Reiniciando distribución debido a cambios detectados")
        return run_distribution()
    
    log("INFO", "distribution", "Distribución completada", {"total_assigned": total_assigned})
    
    return total_assigned


if __name__ == "__main__":
    from app import app
    with app.app_context():
        run_distribution()