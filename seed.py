from app import app
from models import db, GlobalSettings, Market, User, Lead, LeadHistory

def seed_database():
    with app.app_context():
        print("🌱 Limpiando base de datos...")
        # Borrar datos previos en orden inverso por las FK
        db.session.query(User).delete()
        db.session.query(Market).delete()
        db.session.commit()

        print("🌍 Creando mercados...")
        es_market = Market(name="España", automation_enabled=True)
        bp_market = Market(name="Brasil-Portugal", automation_enabled=True)
        fr_market = Market(name="Francia", automation_enabled=False)
        latam_market = Market(name="LATAM", automation_enabled=True)
        it_market = Market(name="Italia", automation_enabled=True)

        # Añadimos TODOS los mercados creados
        db.session.add_all([es_market, bp_market, fr_market, latam_market, it_market])
        db.session.commit() # Guardamos para generar los IDs

        print("✅ Base de datos poblada con éxito!")

if __name__ == "__main__":
    seed_database()