from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import UniqueConstraint


db = SQLAlchemy()

# Tabla intermedia para la relación muchos a muchos
user_markets = db.Table(
    'user_markets',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('market_id', db.Integer, db.ForeignKey('markets.id'), primary_key=True)
)

class GlobalSettings(db.Model):
    __tablename__ = 'global_settings'
    id = db.Column(db.Integer, primary_key=True)
    automation_enabled = db.Column(db.Boolean, default=True)
    last_sync_timestamp = db.Column(db.DateTime, nullable=True)  

class Market(db.Model):
    __tablename__ = 'markets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    flag = db.Column(db.String(10))
    automation_enabled = db.Column(db.Boolean, default=True)

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True)
    hubspot_user_id = db.Column(db.String(100), unique=True)
    max_stock = db.Column(db.Integer, default=10)
    restock_threshold = db.Column(db.Integer, default=3)
    automation_enabled = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(50), default='BDR')
    allowed_pipelines = db.Column(db.JSON, default=list)
    target_mm_percent = db.Column(db.Integer, default=40)   # ← Nuevo
    target_e_percent = db.Column(db.Integer, default=60)    # ← Nuevo
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    markets = db.relationship(
        'Market',
        secondary=user_markets,
        lazy='select',
        backref=db.backref('users', lazy='select')
    )

class Lead(db.Model):
    __tablename__ = 'leads'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(255))
    market_id = db.Column(db.Integer, db.ForeignKey('markets.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    pipeline = db.Column(db.String(100))
    stage = db.Column(db.String(100))
    origin = db.Column(db.String(50))
    first_source_hubspot = db.Column(db.String(255))
    current_source_hubspot = db.Column(db.String(255))
    vertical = db.Column(db.String(255))
    segment = db.Column(db.String(100))                      # ← nuevo
    score = db.Column(db.Integer, nullable=True)             # ← ya no default=0
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class LeadHistory(db.Model):
    __tablename__ = 'lead_history'
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.String(100), db.ForeignKey('leads.id'))
    previous_stage = db.Column(db.String(100))
    new_stage = db.Column(db.String(100))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)



class UserMarketTarget(db.Model):
    __tablename__ = 'user_market_targets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    market_id = db.Column(db.Integer, db.ForeignKey('markets.id', ondelete='CASCADE'), nullable=False)
    target_percent = db.Column(db.Integer, nullable=False, default=0)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'market_id', name='uq_user_market_target'),
    )
    
    user = db.relationship('User', backref=db.backref('market_targets', cascade='all, delete-orphan'))
    market = db.relationship('Market')
    
    def __repr__(self):
        return f'<UserMarketTarget user={self.user_id} market={self.market_id} pct={self.target_percent}>'