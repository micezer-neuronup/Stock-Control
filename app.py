import os
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import func, case, cast, Date

from config import Config
from models import db, GlobalSettings, Market, User, Lead, LeadHistory, UserMarketTarget

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from automation import run_distribution, log

from sync_incremental import run_sync_incremental

app = Flask(__name__)
app.config.from_object(Config)

CORS(app, 
     resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type", "ngrok-skip-browser-warning"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])



# ────── Initialization & Database ─────────────────────────────────────────────
db.init_app(app)

with app.app_context():
    db.create_all()
    
    # Semilla inicial para GlobalSettings si está vacía
    if not GlobalSettings.query.first():
        default_settings = GlobalSettings(automation_enabled=True)
        db.session.add(default_settings)
        db.session.commit()



def run_distribution_with_context():
    with app.app_context():
        log("INFO", "CRON", "Iniciando distribución automática programada...")
        try:
            assigned = run_distribution()
            log("INFO", "CRON", f"Distribución programada completada: {assigned} leads asignados")
        except Exception as e:
            log("ERROR", "CRON", f"Error en distribución programada: {str(e)}")

# ────── Function: run_sync_incremental_with_context ───────────────────────
# ─── Wrapper que ejecuta run_sync_incremental con el contexto de Flask
# ─── Captura excepciones y las registra en el log
# ──────────────────────────────────────────────────────────────────────────
def run_sync_incremental_with_context():
    with app.app_context():
        log("INFO", "CRON", "Iniciando sync incremental desde HubSpot...")
        try:
            total = run_sync_incremental()
            log("INFO", "CRON", f"Sync incremental completado: {total} leads procesados")
        except Exception as e:
            log("ERROR", "CRON", f"Error en sync incremental: {str(e)}")


scheduler = BackgroundScheduler(timezone="Europe/Madrid")

if not scheduler.get_job("daily_distribution"):
     scheduler.add_job(
         run_distribution_with_context,
         CronTrigger(minute=30),
         id="daily_distribution",
         replace_existing=True
     )
     scheduler.add_job(
         run_sync_incremental_with_context,
         CronTrigger(minute=0),
         id="hourly_sync",
         replace_existing=True
     )
     scheduler.start()
     log("INFO", "CRON", "Scheduler iniciado: distribución diaria 12:00 + sync incremental cada hora (Europe/Madrid)")
else:
     log("INFO", "CRON", "Scheduler ya estaba iniciado")


# ────── Routes ────────────────────────────────────────────────────────────────

@app.route('/api/leads/', methods=['GET'])
def get_leads():
    market_id = request.args.get('market_id', type=int)
    query = Lead.query

    if market_id:
        query = query.filter_by(market_id=market_id)

    leads = query.all()

    results = []
    for lead in leads:
        assigned_user = lead.user if hasattr(lead, 'user') else getattr(lead, 'owner', None)
        owner_name = assigned_user.name if assigned_user else "Lead Pool"

        results.append({
            "id": lead.id,
            "name": lead.name,
            "market_id": lead.market_id,
            "market_name": lead.market.name if lead.market else "Sin Mercado",
            "user_id": lead.user_id,
            "owner_name": owner_name,
            "pipeline": lead.pipeline,
            "stage": lead.stage,
            "origin": lead.origin,
            "first_source_hubspot": lead.first_source_hubspot,
            "current_source_hubspot": lead.current_source_hubspot,
            "vertical": lead.vertical,
            "score": lead.score,
            "last_updated": lead.last_updated.isoformat() if lead.last_updated else None,
            "created_at": lead.created_at.isoformat() if lead.created_at else None
        })

    return jsonify(results), 200


@app.route('/api/users/', methods=['GET'])
def get_users():
    users = User.query.all()
    result = []
    for u in users:
        current_stock = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == u.id,
            ~Lead.stage.ilike('%Qualified%'),
            ~Lead.stage.ilike('%Disqualified%')
        ).scalar() or 0

        inbound_count = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == u.id,
            ~Lead.stage.ilike('%Qualified%'),
            ~Lead.stage.ilike('%Disqualified%'),
            Lead.origin.ilike('%inbound%')
        ).scalar() or 0

        outbound_count = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == u.id,
            ~Lead.stage.ilike('%Qualified%'),
            ~Lead.stage.ilike('%Disqualified%'),
            (Lead.origin.notilike('%inbound%')) | (Lead.origin.is_(None))
        ).scalar() or 0

        mm_count = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == u.id,
            ~Lead.stage.ilike('%Qualified%'),
            ~Lead.stage.ilike('%Disqualified%'),
            Lead.pipeline.ilike('%Mid-Market%')
        ).scalar() or 0

        ent_count = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == u.id,
            ~Lead.stage.ilike('%Qualified%'),
            ~Lead.stage.ilike('%Disqualified%'),
            Lead.pipeline.ilike('%Enterprise%')
        ).scalar() or 0

        mm_percent = round((mm_count / current_stock * 100)) if current_stock > 0 else 0
        e_percent = round((ent_count / current_stock * 100)) if current_stock > 0 else 0

        target_e_percent = u.target_e_percent if u.target_e_percent is not None else None

        # ─── market_breakdown: TODOS los mercados donde el user tiene leads ───
        rows = db.session.query(
            Lead.market_id,
            func.count(Lead.id)
        ).filter(
            Lead.user_id == u.id,
            Lead.market_id.isnot(None),
            ~Lead.stage.ilike('%Disqualified%'),
            ~Lead.stage.ilike('%Qualified%'),
            ~Lead.pipeline.ilike('%Leads Academy%')
        ).group_by(Lead.market_id).all()

        market_breakdown = {}
        for mid, _ in rows:
            base_q = db.session.query(func.count(Lead.id)).filter(
                Lead.user_id == u.id,
                Lead.market_id == mid,
                ~Lead.stage.ilike('%Disqualified%'),
                ~Lead.stage.ilike('%Qualified%'),
                ~Lead.pipeline.ilike('%Leads Academy%')
            )
            total_m = base_q.scalar() or 0
            inbound_m = base_q.filter(Lead.origin.ilike('%inbound%')).scalar() or 0
            outbound_m = total_m - inbound_m
            ent_m = base_q.filter(Lead.pipeline.ilike('%Enterprise%')).scalar() or 0
            mm_m = total_m - ent_m

            market_breakdown[mid] = {
                "total": total_m,
                "inbound": inbound_m,
                "outbound": outbound_m,
                "ent": ent_m,
                "mm": mm_m,
            }

        result.append({
            "id": u.id,
            "owner_name": u.name,
            "hubspot_user_id": u.hubspot_user_id,
            "email": u.email or "",
            "market_ids": [m.id for m in u.markets],
            "market_names": [m.name for m in u.markets],
            "max_stock": u.max_stock or 10,
            "restock_threshold": u.restock_threshold or 3,
            "automation_enabled": u.automation_enabled,
            "current_stock": current_stock,
            "role": u.role or "BDR",
            "pipelines": u.allowed_pipelines or [],
            "inbound_count": inbound_count,
            "outbound_count": outbound_count,
            "mm_count": mm_count,
            "ent_count": ent_count,
            "mm_percent": mm_percent,
            "e_percent": e_percent,
            "target_e_percent": target_e_percent,
            "market_breakdown": market_breakdown,
        })
    return jsonify(result), 200


@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    data = request.json or {}
    
    if "market_ids" in data:
        user.markets = []
        for market_id in data["market_ids"]:
            market = db.session.get(Market, market_id)
            if market:
                user.markets.append(market)
    
    if "max_stock" in data:
        user.max_stock = data["max_stock"]
    if "restock_threshold" in data:
        user.restock_threshold = data["restock_threshold"]
    if "role" in data:
        user.role = data["role"]
    if "pipelines" in data:
        user.allowed_pipelines = data["pipelines"]
    if "automation_enabled" in data:
        user.automation_enabled = data["automation_enabled"]
    if "target_e_percent" in data:
        user.target_e_percent = data["target_e_percent"]

    db.session.commit()
    return jsonify({"message": "Usuario actualizado correctamente"}), 200


@app.route('/api/users/<int:user_id>/leads', methods=['GET'])
def get_user_leads(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    leads = Lead.query.filter(
        Lead.user_id == user_id,
        ~Lead.stage.ilike('%Qualified%'),
        ~Lead.stage.ilike('%Disqualified%')
    ).all()

    result = [{
        "id": l.id,
        "market_name": l.market.name if l.market else "Sin mercado",
        "status": l.stage,
        "score": l.score,
        "owner_name": user.name,
        "lead_type": l.origin
    } for l in leads]

    return jsonify(result), 200


@app.route('/api/users/<int:user_id>/restock', methods=['POST'])
def force_user_restock(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    alive_condition = ~Lead.stage.ilike('%Qualified%') & ~Lead.stage.ilike('%Disqualified%')
    
    current_stock = db.session.query(func.count(Lead.id)).filter(
        Lead.user_id == user.id,
        alive_condition
    ).scalar() or 0

    space_available = (user.max_stock or 10) - current_stock
    if space_available <= 0:
        return jsonify({"message": f"{user.name} ya está al máximo ({current_stock}/{user.max_stock})"}), 200

    allowed_pipes = user.allowed_pipelines or []
    
    pool_leads = Lead.query.filter(
        Lead.user_id.is_(None),
        Lead.market_id.in_([m.id for m in user.markets]),
        Lead.pipeline.in_(allowed_pipes),
        alive_condition
    ).order_by(Lead.score.desc(), Lead.id.asc()).limit(space_available).all()

    assigned_count = len(pool_leads)
    for lead in pool_leads:
        lead.user_id = user.id

    db.session.commit()
    return jsonify({"message": f"Se han recargado {assigned_count} leads a {user.name}"}), 200


@app.route('/api/stock-control', methods=['GET'])
def get_dashboard_stats():
    # ============================================================
    # FILTROS BASE
    # ============================================================
    EXCLUDED_PIPELINES = ['Leads Academy']
    
    ALIVE_FILTER = (
        ~Lead.stage.ilike('%Disqualified%') &
        ~Lead.pipeline.in_(EXCLUDED_PIPELINES)
    )
    
    POOL_FILTER = (
        (Lead.raw_owner.is_(None) | (Lead.raw_owner == '')) &
        Lead.market_id.isnot(None) &
        Lead.score.isnot(None) &
        Lead.segment.isnot(None) &
        Lead.vertical.ilike('%NeuronUP%') &
        ~Lead.stage.ilike('%Disqualified%') &
        ~Lead.stage.ilike('%Qualified%') &
        ~Lead.pipeline.ilike('%Leads Academy%')
    )
    
    WORKLOAD_FILTER = (
        ~Lead.stage.ilike('%Disqualified%') &
        ~Lead.stage.ilike('%Qualified%') &
        ~Lead.pipeline.in_(EXCLUDED_PIPELINES)
    )
    
    # ============================================================
    # 1. HERO METRICS
    # ============================================================
    total_vivos = db.session.query(func.count(Lead.id)).filter(ALIVE_FILTER).scalar() or 0

    leads_en_pool = db.session.query(func.count(Lead.id)).filter(
        POOL_FILTER,
        Lead.user_id.is_(None)
    ).scalar() or 0

    # Leads realmente asignados (con user_id)
    asignados_reales = db.session.query(func.count(Lead.id)).filter(
        ALIVE_FILTER,
        Lead.user_id.isnot(None)
    ).scalar() or 0

    avg_score_raw = db.session.query(func.avg(Lead.score)).filter(ALIVE_FILTER).scalar()
    score_promedio = round(avg_score_raw) if avg_score_raw is not None else 0

    total_calificados = db.session.query(func.count(Lead.id)).filter(
        ALIVE_FILTER,
        Lead.stage.ilike('%Qualified%')
    ).scalar() or 0

    porcentaje_calificados = round((total_calificados / total_vivos * 100), 1) if total_vivos > 0 else 0.0

    inbound_vivos = db.session.query(func.count(Lead.id)).filter(
        ALIVE_FILTER,
        Lead.origin.ilike('%inbound%')
    ).scalar() or 0

    outbound_vivos = db.session.query(func.count(Lead.id)).filter(
        ALIVE_FILTER,
        (Lead.origin.notilike('%inbound%')) | (Lead.origin.is_(None))
    ).scalar() or 0

    # ============================================================
    # 2. PIPELINE DATA
    # ============================================================
    pipeline_counts = db.session.query(
        Lead.pipeline,
        func.count(Lead.id)
    ).filter(ALIVE_FILTER).group_by(Lead.pipeline).all()

    pipeline_map_config = {
        "Lead pipeline": {"name": "Lead", "color": "#64748b"},
        "Mid-Market Leads": {"name": "Mid-Market", "color": "#6366f1"},
        "Enterprise Leads": {"name": "Enterprise", "color": "#10b981"}
    }

    pipeline_data = []
    for raw_pipeline, count in pipeline_counts:
        config = pipeline_map_config.get(raw_pipeline, {"name": raw_pipeline or "Otro", "color": "#94a3b8"})
        pipeline_data.append({
            "name": config["name"],
            "value": count,
            "color": config["color"]
        })

    # ============================================================
    # 3. LEADS POR MERCADO
    # ============================================================
    MARKET_NAMES_BY_ID = {
        1: "España",
        2: "Brasil - Portugal",
        3: "Francia",
        4: "LATAM",
        5: "Italia",
        6: "USA",
    }
    
    MARKET_FLAGS_BY_ID = {
        1: "🇪🇸",
        2: "🇧🇷🇵🇹",
        3: "🇫🇷",
        4: "🌎",
        5: "🇮🇹",
        6: "🇺🇸",

    }
    
    MARKET_FLAG_CODES = {
        1: "es",
        2: "br",
        3: "fr",
        4: "mx",
        5: "it",
        6: "us",
    }

    market_stacked_data = []

    for market_id in [1, 2, 3, 4, 5, 6]:
        asignados = db.session.query(func.count(Lead.id)).filter(
            Lead.market_id == market_id,
            Lead.user_id.isnot(None),
            ALIVE_FILTER
        ).scalar() or 0

        en_pool = db.session.query(func.count(Lead.id)).filter(
            Lead.market_id == market_id,
            Lead.user_id.is_(None),
            POOL_FILTER
        ).scalar() or 0
        
        total_market = asignados + en_pool
        total_global = total_vivos if total_vivos > 0 else 1
        pct = round((total_market / total_global) * 100)
        
        market_stacked_data.append({
            "name": MARKET_NAMES_BY_ID.get(market_id, f"Mercado {market_id}"),
            "flag": MARKET_FLAGS_BY_ID.get(market_id, "❓"),
            "flagCode": MARKET_FLAG_CODES.get(market_id, ""),
            "asignados": asignados,
            "enPool": en_pool,
            "pct": pct
        })

    sin_mercado_asignados = db.session.query(func.count(Lead.id)).filter(
        Lead.market_id.is_(None),
        Lead.user_id.isnot(None),
        ALIVE_FILTER
    ).scalar() or 0

    sin_mercado_en_pool = db.session.query(func.count(Lead.id)).filter(
        Lead.market_id.is_(None),
        Lead.user_id.is_(None),
        POOL_FILTER
    ).scalar() or 0

    if sin_mercado_asignados > 0 or sin_mercado_en_pool > 0:
        market_stacked_data.append({
            "name": "Sin mercado",
            "flag": "❓",
            "flagCode": "",
            "asignados": sin_mercado_asignados,
            "enPool": sin_mercado_en_pool,
            "pct": round(((sin_mercado_asignados + sin_mercado_en_pool) / (total_vivos if total_vivos > 0 else 1)) * 100)
        })

    # ============================================================
    # 4. DISTRIBUCIÓN POR ESTADOS
    # ============================================================
    BASE_FILTER = ~Lead.pipeline.in_(EXCLUDED_PIPELINES)
    
    new_count = db.session.query(func.count(Lead.id)).filter(BASE_FILTER, Lead.stage.ilike('%New%')).scalar() or 0
    att_count = db.session.query(func.count(Lead.id)).filter(BASE_FILTER, Lead.stage.ilike('%Attempting%')).scalar() or 0
    
    cont_count = db.session.query(func.count(Lead.id)).filter(
        BASE_FILTER,
        (Lead.stage.ilike('%Connected%')) | 
        (Lead.stage.ilike('%Conversation%')) | 
        (Lead.stage.ilike('%Contacto%')) | 
        (Lead.stage.ilike('%Hot%'))
    ).scalar() or 0

    qual_count = db.session.query(func.count(Lead.id)).filter(
        BASE_FILTER,
        Lead.stage.ilike('%Qualified%'),
        ~Lead.stage.ilike('%Disqualified%')
    ).scalar() or 0

    disq_count = db.session.query(func.count(Lead.id)).filter(BASE_FILTER, Lead.stage.ilike('%Disqualified%')).scalar() or 0

    state_data = [
        {"name": "New", "value": new_count},
        {"name": "Att.", "value": att_count},
        {"name": "Cont.", "value": cont_count},
        {"name": "Qual.", "value": qual_count},
        {"name": "Disq.", "value": disq_count}
    ]

    # ============================================================
    # 5. ENTRADA DIARIA
    # ============================================================
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    daily_activity = (
        db.session.query(
            cast(Lead.created_at, Date).label('date'),
            Lead.origin,
            func.count(Lead.id).label('count')
        )
        .filter(Lead.created_at >= seven_days_ago)
        .filter(BASE_FILTER)
        .group_by(cast(Lead.created_at, Date), Lead.origin)
        .order_by(cast(Lead.created_at, Date))
        .all()
    )
    
    evolution_dict = {}
    for row in daily_activity:
        date_str = row.date.strftime('%d/%m')
        if date_str not in evolution_dict:
            evolution_dict[date_str] = {'date': date_str, 'inbound': 0, 'outbound': 0}
        
        if row.origin and 'inbound' in row.origin.lower():
            evolution_dict[date_str]['inbound'] = row.count
        else:
            evolution_dict[date_str]['outbound'] = row.count
    
    evolution_data = list(evolution_dict.values())
    evolution_data.sort(key=lambda x: datetime.strptime(x['date'], '%d/%m'))
    evolution_data = evolution_data[-7:]

    # ============================================================
    # 6. CARGA POR SDR
    # ============================================================
    users = User.query.all()
    sdr_workload_data = []

    for u in users:
        current_stock = db.session.query(func.count(Lead.id)).filter(
            Lead.user_id == u.id,
            WORKLOAD_FILTER
        ).scalar() or 0

        max_stock = u.max_stock if (u.max_stock and u.max_stock > 0) else 10
        
        carga_normal = min(current_stock, max_stock)
        sobrecarga = max(0, current_stock - max_stock)

        first_name = (u.name or "SDR").split()[0]

        sdr_workload_data.append({
            "name": first_name,
            "cargaNormal": carga_normal,
            "sobrecarga": sobrecarga,
            "maxStock": max_stock,
            "automation_enabled": u.automation_enabled
        })

    return jsonify({
        "stats": {
            "totalLeadsVivos": total_vivos,
            "leadsEnPool": leads_en_pool,
            "asignadosReales": asignados_reales,
            "scorePromedio": score_promedio,
            "porcentajeCalificados": porcentaje_calificados,
            "inboundVivos": inbound_vivos,
            "outboundVivos": outbound_vivos,
            "marketStackedData": market_stacked_data,
            "pipelineData": pipeline_data,
            "stateData": state_data,
            "evolutionData": evolution_data,
            "sdrWorkloadData": sdr_workload_data
        }
    }), 200

@app.route('/api/distribute', methods=['POST'])
def distribute_leads():
    """Dispara la distribución automática de leads."""
    try:
        assigned = run_distribution()
        return jsonify({
            "message": "Distribución completada",
            "assigned": assigned
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/global-automation', methods=['GET'])
def get_global_automation():
    """Obtiene el estado de automatización global."""
    setting = GlobalSettings.query.first()
    enabled = setting.automation_enabled if setting else True
    return jsonify({"automation_enabled": enabled}), 200


@app.route('/api/markets', methods=['GET'])
def get_markets():
    """Obtiene todos los mercados con su estado de automatización."""
    markets = Market.query.all()
    result = [{
        "id": m.id,
        "name": m.name,
        "flag": m.flag,
        "automation_enabled": m.automation_enabled
    } for m in markets]
    return jsonify(result), 200


@app.route('/api/global-automation', methods=['PUT'])
def update_global_automation():
    """Actualiza el estado de automatización global."""
    data = request.json or {}
    enabled = data.get("enabled", True)
    
    setting = GlobalSettings.query.first()
    if setting:
        setting.automation_enabled = enabled
    else:
        setting = GlobalSettings(automation_enabled=enabled)
        db.session.add(setting)
    
    db.session.commit()
    return jsonify({"message": "Automatización global actualizada"}), 200


@app.route('/api/markets/<int:market_id>', methods=['PUT'])
def update_market_automation(market_id):
    """Actualiza el estado de automatización de un mercado."""
    market = db.session.get(Market, market_id)
    if not market:
        return jsonify({"error": "Mercado no encontrado"}), 404
    
    data = request.json or {}
    if "automation_enabled" in data:
        market.automation_enabled = data["automation_enabled"]
    
    db.session.commit()
    return jsonify({"message": "Mercado actualizado"}), 200


@app.route('/api/users/by-name/<name>', methods=['GET'])
def get_user_by_name(name):
    """Busca usuarios cuyo nombre contenga el texto dado."""
    users = User.query.filter(User.name.ilike(f'%{name}%')).all()
    result = [{
        "id": u.id,
        "owner_name": u.name,
        "automation_enabled": u.automation_enabled,
    } for u in users]
    return jsonify(result), 200




@app.route('/api/users/<int:user_id>/market-targets', methods=['PUT'])
def update_user_market_targets(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    data = request.json or {}
    targets = data.get("targets", [])
    
    # Mercados asignados al SDR
    assigned_market_ids = {m.id for m in user.markets}
    
    # Validaciones
    if not isinstance(targets, list):
        return jsonify({"error": "Formato inválido"}), 400
    
    # Si la lista está vacía → borrar config (equitativo)
    if len(targets) == 0:
        UserMarketTarget.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        return jsonify({"message": "Config eliminada, reparto equitativo"}), 200
    
    # Validar cada target
    seen_markets = set()
    total = 0
    for t in targets:
        mid = t.get("market_id")
        pct = t.get("target_percent", 0)
        
        if mid not in assigned_market_ids:
            return jsonify({"error": f"Mercado {mid} no asignado al SDR"}), 400
        if mid in seen_markets:
            return jsonify({"error": f"Mercado {mid} duplicado"}), 400
        if not isinstance(pct, int) or pct < 0 or pct > 100:
            return jsonify({"error": f"Porcentaje inválido para mercado {mid}"}), 400
        
        seen_markets.add(mid)
        total += pct
    
    # Debe sumar exactamente 100
    if total != 100:
        return jsonify({"error": f"La suma debe ser 100, actual: {total}"}), 400
    
    # Guardar: borrar los existentes y crear nuevos
    UserMarketTarget.query.filter_by(user_id=user_id).delete()
    for t in targets:
        db.session.add(UserMarketTarget(
            user_id=user_id,
            market_id=t["market_id"],
            target_percent=t["target_percent"]
        ))
    
    db.session.commit()
    return jsonify({"message": "Config actualizada"}), 200


@app.route('/api/users/<int:user_id>/market-targets', methods=['DELETE'])
def delete_user_market_targets(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    UserMarketTarget.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    return jsonify({"message": "Config eliminada"}), 200





@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "message": "Backend y Base de Datos conectados correctamente"
    }), 200


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)