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
        "restock_threshold": 3
    },
    {
        "name": "Pedro Eduardo Arruda Da Silva",
        "email": "pedro.arruda@empresa.com",
        "role": "AE",
        "hubspot_user_id": "1683406654",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Amanda de Souza Lacerda",
        "email": "amanda.lacerda@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "29921148",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Rafael Vianna",
        "email": "rafael.vianna@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "30464142",
        "market_id": 2,
        "max_stock": 10,
        "restock_threshold": 3
    },

    # ------------------ ESPAÑA (Market ID: 1) ------------------
    {
        "name": "Natalia Gonzalo Sanchez",
        "email": "natalia.gonzalo@empresa.com",
        "role": "AE",
        "hubspot_user_id": "1962698788",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Nacho Mérida Prudencio",
        "email": "nacho.merida@empresa.com",
        "role": "AE",
        "hubspot_user_id": "35793587",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Jorge Alcaraz",
        "email": "jorge.alcaraz@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "35767020",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Virginia Caballero Jimenez",
        "email": "virginia.caballero@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "823814582",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Alexia Anghelescu",
        "email": "alexia.anghelescu@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "30089725",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3
    },

    # ------------------ FRANCIA (Market ID: 3) ------------------
    {
        "name": "Nathan Schuhmann",
        "email": "nathan.schuhmann@empresa.com",
        "role": "AE",
        "hubspot_user_id": "30302090",
        "market_id": 3,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Heloise Chassagny",
        "email": "heloise.chassagny@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "30033742",
        "market_id": 3,
        "max_stock": 10,
        "restock_threshold": 3
    },

    # ------------------ ITALIA (Market ID: 5) ------------------
    {
        "name": "Francesco Lamberto",
        "email": "francesco.lamberto@empresa.com",
        "role": "AE",
        "hubspot_user_id": "36364069",
        "market_id": 5,
        "max_stock": 10,
        "restock_threshold": 3
    },

    # ------------------ MÉXICO / LATAM (Market ID: 4) ------------------
    {
        "name": "Luis Antonio Aguilera Tinoco",
        "email": "luis.aguilera@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "1911105412",
        "market_id": 4,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Michelle Nuñez",
        "email": "michelle.nunez@empresa.com",
        "role": "BDR",
        "hubspot_user_id": "30154175",
        "market_id": 4,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Aldo Hernandez Salazar",
        "email": "aldo.hernandez@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "",
        "market_id": 4,
        "max_stock": 10,
        "restock_threshold": 3
    },
    {
        "name": "Michael Ezeh",
        "email": "michael.ezeh@empresa.com",
        "role": "SDR",
        "hubspot_user_id": "32695483",
        "market_id": 1,
        "max_stock": 10,
        "restock_threshold": 3
    }
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
                continue

            # Crear el usuario sin market_id
            new_user = User(
                name=bdr["name"],
                email=bdr["email"],
                hubspot_user_id=bdr["hubspot_user_id"],
                max_stock=bdr.get("max_stock", 10),
                restock_threshold=bdr.get("restock_threshold", 3),
                role=bdr.get("role", "BDR"),
                allowed_pipelines=["Mid-Market", "Enterprise"]
            )
            db.session.add(new_user)
            db.session.flush()  # Para obtener el ID del usuario

            # Asignar mercado
            market = db.session.get(Market, bdr["market_id"])
            if market:
                new_user.markets.append(market)

            created_count += 1

        db.session.commit()
        print(f"✅ Proceso completado:")
        print(f"   - BDRs nuevos creados: {created_count}")
        print(f"   - BDRs existentes (no modificados): {skipped_count}")


if __name__ == "__main__":
    seed_bdrs()