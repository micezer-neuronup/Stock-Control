from app import app
from models import db, GlobalSettings, Market


def seed_database():
    with app.app_context():
        db.create_all()

        # GlobalSettings
        if not GlobalSettings.query.first():
            db.session.add(GlobalSettings(automation_enabled=True))
            db.session.commit()
            print("✅ GlobalSettings creado")
        else:
            print("ℹ️  GlobalSettings ya existe")

        # Mercados con IDs forzados (coinciden con MARKET_MAPPING de automation.py)
        markets_data = [
            (1, "España", "🇪🇸", True),
            (2, "Brasil - Portugal", "🇧🇷🇵🇹", True),
            (3, "Francia", "🇫🇷", False),
            (4, "LATAM", "🌎", True),
            (5, "Italia", "🇮🇹", True),
        ]

        created = 0
        for mid, name, flag, auto in markets_data:
            if not db.session.get(Market, mid):
                db.session.add(Market(id=mid, name=name, flag=flag, automation_enabled=auto))
                created += 1
        db.session.commit()
        print(f"✅ Mercados: {created} nuevos (total {Market.query.count()})")

        for m in Market.query.order_by(Market.id).all():
            print(f"   {m.id}  {m.name}  automation={m.automation_enabled}")


if __name__ == "__main__":
    seed_database()