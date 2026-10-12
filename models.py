from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class WarrantyClaim(db.Model):
    __tablename__ = 'warranty_claims'

    id = db.Column(db.Integer, primary_key=True)
    claim_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    company_code = db.Column(db.String(10), nullable=False)
    plant = db.Column(db.String(10), nullable=False)
    storage_location = db.Column(db.String(10), nullable=True)
    cost_center = db.Column(db.String(20), nullable=True)
    material = db.Column(db.String(100), nullable=False)
    business_partner = db.Column(db.String(100), nullable=False)
    document_number = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    requested_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(30), default='At Risk')  # At Risk, Pending Validation, Under Review, Escalated, Resolved
    risk_score = db.Column(db.Integer, default=0)
    risk_level = db.Column(db.String(20), default='LOW')  # LOW, MEDIUM, HIGH, CRITICAL
    age_days = db.Column(db.Integer, default=0)
    sla_status = db.Column(db.String(20), default='SAFE')  # SAFE, AT RISK, BREACHED
    validation_status = db.Column(db.String(20), default='PASS')  # PASS, FAIL, WARNING
    assigned_to = db.Column(db.String(100), default='Unassigned')
    recommended_action = db.Column(db.Text, nullable=True)
    risk_explanation = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    validation_results = db.relationship('ValidationResult', backref='claim', lazy=True, cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='claim', lazy=True, cascade='all, delete-orphan', order_by='AuditLog.timestamp.desc()')
    comments = db.relationship('Comment', backref='claim', lazy=True, cascade='all, delete-orphan', order_by='Comment.created_at.desc()')

    def to_dict(self):
        return {
            'id': self.id,
            'claim_number': self.claim_number,
            'company_code': self.company_code,
            'plant': self.plant,
            'storage_location': self.storage_location,
            'cost_center': self.cost_center,
            'material': self.material,
            'business_partner': self.business_partner,
            'document_number': self.document_number,
            'amount': self.amount,
            'requested_date': self.requested_date.strftime('%Y-%m-%d') if self.requested_date else '',
            'status': self.status,
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'age_days': self.age_days,
            'sla_status': self.sla_status,
            'validation_status': self.validation_status,
            'assigned_to': self.assigned_to,
            'recommended_action': self.recommended_action,
            'risk_explanation': self.risk_explanation,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
            'resolved_at': self.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if self.resolved_at else None
        }


class ValidationResult(db.Model):
    __tablename__ = 'validation_results'

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('warranty_claims.id'), nullable=False, index=True)
    rule_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # PASS, FAIL, WARNING, AT RISK
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), nullable=False)  # INFO, WARNING, HIGH, CRITICAL
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('warranty_claims.id'), nullable=False, index=True)
    action = db.Column(db.String(100), nullable=False)
    performed_by = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('warranty_claims.id'), nullable=False, index=True)
    user_name = db.Column(db.String(100), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
