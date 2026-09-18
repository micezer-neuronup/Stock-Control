import os
from app import app
from models import db, User, Market


BDR_LIST = [
    # ------------------ BRASIL + PORTUGAL (Market ID: 2) ------------------
    {
        "name": "Adriana Ferreira dos Santos",
        "email": "adriana.ferreira@empresa.com",
        "role": "AE",
        "hubspot_user_id": "29921153",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Pedro Eduardo Arruda Da Silva",
        "email": "pedro.arruda@empresa.com",
        "role": "AE",
        "hubspot_user_id": "1683406654",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Amanda de Souza Lacerda",
        "email": "amanda.lacerda@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "29921148",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Rafael Vianna",
        "email": "rafael.vianna@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "30464142",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },

    # ------------------ ESPAÑA (Market ID: 1) ------------------
    {
        "name": "Natalia Gonzalo Sanchez",
        "email": "natalia.gonzalo@empresa.com",
        "role": "AE",
        "hubspot_user_id": "1962698788",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Nacho Mérida Prudencio",
        "email": "nacho.merida@empresa.com",
        "role": "AE",
        "hubspot_user_id": "35793587",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Jorge Alcaraz",
        "email": "jorge.alcaraz@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "35767020",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Virginia Caballero Jimenez",
        "email": "virginia.caballero@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "823814582",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Alexia Anghelescu",
        "email": "alexia.anghelescu@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "30089725",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },

    # ------------------ FRANCIA (Market ID: 3) ------------------
    {
        "name": "Nathan Schuhmann",
        "email": "nathan.schuhmann@empresa.com",
        "role": "AE",
        "hubspot_user_id": "30302090",
        "market_id": 3,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Heloise Chassagny",
        "email": "heloise.chassagny@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "30033742",
        "market_id": 3,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },

    # ------------------ ITALIA (Market ID: 5) ------------------
    {
        "name": "Francesco Lamberto",
        "email": "francesco.lamberto@empresa.com",
        "role": "AE",
        "hubspot_user_id": "36364069",
        "market_id": 5,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },

    # ------------------ MÉXICO / LATAM (Market ID: 4) ------------------
    {
        "name": "Luis Antonio Aguilera Tinoco",
        "email": "luis.aguilera@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "1911105412",
        "market_id": 4,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Michelle Nuñez",
        "email": "michelle.nunez@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "30154175",
        "market_id": 4,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },
    {
        "name": "Aldo Hernandez Salazar",
        "email": "aldo.hernandez@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "",
        "market_id": 4,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": False,
    },

    # ------------------ MICHAEL (activo para la prueba) ------------------
    {
        "name": "Michael Ezeh",
        "email": "michael.ezeh@neuronup.com",
        "role": "SDR",
        "hubspot_user_id": "32695483",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3,
        "automation_enabled": True,   # ← único activo
        "target_e_percent": 60,
    },
]


def seed_bdrs():
    with app.app_context():
        print("🌱 Verificando e insertando BDRs...")
        created_count = 0
        skipped_count = 0

        for bdr in BDR_LIST:
            existing_user = User.query.filter_by(hubspot_user_id=bdr["hubspot_user_id"]).first()

            if existing_user:
                skipped_count += 1
                print(f"   ⏭️  Ya existe: {existing_user.name}")
                continue

            new_user = User(
                name=bdr["name"],
                email=bdr["email"],
                hubspot_user_id=bdr["hubspot_user_id"],
                max_stock=bdr.get("max_stock", 10),
                restock_threshold=bdr.get("restock_threshold", 3),
                role=bdr.get("role", "BDR"),
                allowed_pipelines=["Mid-Market", "Enterprise"],
                automation_enabled=bdr.get("automation_enabled", False),
                target_e_percent=bdr.get("target_e_percent", 60),
            )
            db.session.add(new_user)
            db.session.flush()

            market = db.session.get(Market, bdr["market_id"])
            if market:
                new_user.markets.append(market)

            created_count += 1
            status = "🟢" if new_user.automation_enabled else "⚪"
            print(f"   ✅ Creado: {new_user.name} {status}")

        db.session.commit()
        print(f"\n✅ Proceso completado:")
        print(f"   - BDRs nuevos creados: {created_count}")
        print(f"   - BDRs existentes (no modificados): {skipped_count}")

        print(f"\n📋 Estado actual:")
        for u in User.query.order_by(User.id).all():
            status = "🟢" if u.automation_enabled else "⚪"
            print(f"   {status} id={u.id} {u.name} hubspot={u.hubspot_user_id} market={[m.name for m in u.markets]} target_e={u.target_e_percent}")


if __name__ == "__main__":
    seed_bdrs()