import os
from datetime import date, datetime, timedelta
from models import db, WarrantyClaim, ValidationResult, AuditLog, Comment
from engine import run_validation_rules, calculate_risk, generate_recommended_action, REFERENCE_DATE

SAMPLE_CLAIMS = [
    # 1. PRIMARY ASSESSMENT DEMO RECORD
    {
        "claim_number": "PRD-460082",
        "company_code": "1200",
        "plant": "1101",
        "storage_location": "SL15",
        "cost_center": "CC-2282",
        "material": "Lithium Module LM-90",
        "business_partner": "Baltic Freight BV",
        "document_number": "PRD-460082",
        "amount": 125250.0,
        "requested_date": date(2026, 10, 7),  # 5 days old -> SLA AT RISK
        "status": "At Risk",
        "assigned_to": "Unassigned",
        "pending_approval": False,
        "initial_comments": [
            ("System Monitor", "Claim ingested from SAP S/4HANA Warranty Claim interface queue (IDOC/WTY_CLAIM)."),
            ("System Rule Engine", "Flagged for manual review: Financial exposure exceeds £50,000 threshold and age reaches 5 days.")
        ]
    },
    # 2. CRITICAL - Ageing > 5 days + Breached SLA + High Value
    {
        "claim_number": "PRD-520194",
        "company_code": "1200",
        "plant": "1101",
        "storage_location": "SL10",
        "cost_center": "CC-2282",
        "material": "Industrial Inverter INV-500",
        "business_partner": "Siemens Industrial UK",
        "document_number": "PRD-520194",
        "amount": 94800.0,
        "requested_date": date(2026, 10, 4),  # 8 days old -> BREACHED
        "status": "Escalated",
        "assigned_to": "David Smith",
        "pending_approval": False,
        "initial_comments": [
            ("David Smith", "Awaiting emergency supplier warranty inspection report from Siemens UK field engineer.")
        ]
    },
    # 3. CRITICAL - Multiple Exceptions: Missing Master Data + Pending Approval
    {
        "claim_number": "CLM-883102",
        "company_code": "9999",  # Invalid Company Code -> Master data failure
        "plant": "1201",
        "storage_location": "SL01",
        "cost_center": "CC-4500",
        "material": "Unregistered Battery Pack BX-99",  # Invalid Material
        "business_partner": "Apex Scientific Ltd",
        "document_number": "CLM-883102",
        "amount": 62400.0,
        "requested_date": date(2026, 10, 6),  # 6 days old -> BREACHED
        "status": "At Risk",
        "assigned_to": "Unassigned",
        "pending_approval": True,
        "initial_comments": [
            ("Integration Gateway", "Master Data lookup failed: Company code 9999 not registered in Northfield FI ledger.")
        ]
    },
    # 4. HIGH - Pending Approval + High Value (£82,000)
    {
        "claim_number": "PRD-330911",
        "company_code": "1000",
        "plant": "1102",
        "storage_location": "SL22",
        "cost_center": "CC-1010",
        "material": "Cryo-Cooling Unit CC-400",
        "business_partner": "Oxford Instruments Group",
        "document_number": "PRD-330911",
        "amount": 82000.0,
        "requested_date": date(2026, 10, 8),  # 4 days old -> AT RISK
        "status": "Pending Validation",
        "assigned_to": "Sarah Jenkins",
        "pending_approval": True,
        "initial_comments": [
            ("Sarah Jenkins", "Submitted financial authorization request to Oxford Science Hub operations director.")
        ]
    },
    # 5. HIGH - Document Mismatch + Approaching SLA
    {
        "claim_number": "PRD-774120",
        "company_code": "1200",
        "plant": "1305",
        "storage_location": "SL15",
        "cost_center": "CC-8820",
        "material": "Solar Harvester SH-20",
        "business_partner": "Alpha Power Systems",
        "document_number": "DOC_INV_ERR_99",  # Invalid format -> Document check failure
        "amount": 47500.0,
        "requested_date": date(2026, 10, 7),  # 5 days old -> AT RISK
        "status": "At Risk",
        "assigned_to": "Unassigned",
        "pending_approval": False,
        "initial_comments": [
            ("Billing Bot", "Purchase order document cross-reference missing in SAP MM table EKPO.")
        ]
    },
    # 6. MEDIUM - Missing Master Data (Unknown Vendor) + Moderate Value
    {
        "claim_number": "CLM-610423",
        "company_code": "1200",
        "plant": "1101",
        "storage_location": "SL15",
        "cost_center": "CC-2282",
        "material": "Telemetry Sensor TS-10",
        "business_partner": "Unknown Subcontractor Ltd",  # Invalid Partner
        "document_number": "CLM-610423",
        "amount": 24500.0,
        "requested_date": date(2026, 10, 9),  # 3 days old -> SAFE
        "status": "Under Review",
        "assigned_to": "Elena Rostova",
        "pending_approval": False,
        "initial_comments": [
            ("Elena Rostova", "Vendor onboarding request sent to Procurement MDG team.")
        ]
    },
    # 7. MEDIUM - Ageing (4 days) + Moderate Value
    {
        "claim_number": "PRD-290114",
        "company_code": "2100",
        "plant": "1201",
        "storage_location": "SL01",
        "cost_center": "CC-3100",
        "material": "Laser Diode LD-85",
        "business_partner": "Cambridge Precision Ltd",
        "document_number": "PRD-290114",
        "amount": 31200.0,
        "requested_date": date(2026, 10, 8),  # 4 days old -> AT RISK
        "status": "Under Review",
        "assigned_to": "Ravi Kumar",
        "pending_approval": False,
        "initial_comments": [
            ("Ravi Kumar", "Technical diagnostics confirmed defective diode assembly. Validating supplier warranty contract.")
        ]
    },
    # 8. MEDIUM - Pending Approval + Moderate Exposure
    {
        "claim_number": "CLM-401829",
        "company_code": "1000",
        "plant": "1102",
        "storage_location": "SL22",
        "cost_center": "CC-1010",
        "material": "Fiber Optical Transceiver FOT-40",
        "business_partner": "Nordic Logistics ApS",
        "document_number": "CLM-401829",
        "amount": 18900.0,
        "requested_date": date(2026, 10, 10),  # 2 days old -> SAFE
        "status": "Pending Validation",
        "assigned_to": "Unassigned",
        "pending_approval": True,
        "initial_comments": []
    },
    # 9. LOW - Straight-Through Clean Claim (Low Value, Fresh)
    {
        "claim_number": "CLM-109284",
        "company_code": "1200",
        "plant": "1101",
        "storage_location": "SL15",
        "cost_center": "CC-2282",
        "material": "Quantum Sensor QS-12",
        "business_partner": "Apex Scientific Ltd",
        "document_number": "CLM-109284",
        "amount": 6450.0,
        "requested_date": date(2026, 10, 11),  # 1 day old -> SAFE
        "status": "Under Review",
        "assigned_to": "Sarah Jenkins",
        "pending_approval": False,
        "initial_comments": [
            ("Sarah Jenkins", "All documentation in order. Batch serial number matched.")
        ]
    },
    # 10. LOW - Clean Straight-Through Processing
    {
        "claim_number": "PRD-118803",
        "company_code": "1000",
        "plant": "1102",
        "storage_location": "SL22",
        "cost_center": "CC-1010",
        "material": "Telemetry Sensor TS-10",
        "business_partner": "Vanguard Automation Ltd",
        "document_number": "PRD-118803",
        "amount": 4200.0,
        "requested_date": date(2026, 10, 11),  # 1 day old -> SAFE
        "status": "Pending Validation",
        "assigned_to": "Unassigned",
        "pending_approval": False,
        "initial_comments": []
    },
    # 11. RESOLVED CLAIM - Historical resolution example (Audit demonstrate)
    {
        "claim_number": "PRD-990215",
        "company_code": "1200",
        "plant": "1101",
        "storage_location": "SL15",
        "cost_center": "CC-2282",
        "material": "Lithium Module LM-90",
        "business_partner": "Baltic Freight BV",
        "document_number": "PRD-990215",
        "amount": 54000.0,
        "requested_date": date(2026, 10, 2),  # 10 days old
        "status": "Resolved",
        "assigned_to": "Ravi Kumar",
        "pending_approval": False,
        "resolved_at": datetime(2026, 10, 5, 14, 30),
        "initial_comments": [
            ("Ravi Kumar", "Supplier Baltic Freight BV agreed to 100% warranty credit note CN-88219."),
            ("Ravi Kumar", "Settlement posted in SAP FI-AP. Claim closed.")
        ]
    },
    # 12. RESOLVED CLAIM - Straight-Through Resolution
    {
        "claim_number": "CLM-334910",
        "company_code": "1000",
        "plant": "1102",
        "storage_location": "SL22",
        "cost_center": "CC-1010",
        "material": "Solar Harvester SH-20",
        "business_partner": "Alpha Power Systems",
        "document_number": "CLM-334910",
        "amount": 12800.0,
        "requested_date": date(2026, 10, 5),
        "status": "Resolved",
        "assigned_to": "David Smith",
        "pending_approval": False,
        "resolved_at": datetime(2026, 10, 7, 16, 15),
        "initial_comments": [
            ("David Smith", "Approved and processed warranty credit voucher in SAP.")
        ]
    }
]


def seed_database(app):
    """Initializes and seeds database with sample UK SAP warranty claims."""
    with app.app_context():
        db.create_all()

        # If data already exists, don't duplicate
        if WarrantyClaim.query.first():
            return

        print("Seeding SQLite database with Northfield University warranty claims...")

        for item in SAMPLE_CLAIMS:
            # Run engine validation rules
            val_results, age_days, sla_status = run_validation_rules(item)

            # Compute risk
            risk_score, risk_level, explanation_text, _ = calculate_risk(
                item["amount"], age_days, sla_status, val_results
            )

            # Overall validation status
            has_fail = any(r["status"] == "FAIL" for r in val_results)
            has_warn = any(r["status"] == "WARNING" for r in val_results)
            if has_fail:
                val_status = "FAIL"
            elif has_warn:
                val_status = "WARNING"
            else:
                val_status = "PASS"

            # Recommended action
            rec = generate_recommended_action(item, val_results, risk_level, sla_status)
            recommended_action = f"{rec['action']}: {rec['detail']}"

            # Create claim entity
            claim = WarrantyClaim(
                claim_number=item["claim_number"],
                company_code=item["company_code"],
                plant=item["plant"],
                storage_location=item.get("storage_location", "SL15"),
                cost_center=item.get("cost_center", "CC-2282"),
                material=item["material"],
                business_partner=item["business_partner"],
                document_number=item["document_number"],
                amount=item["amount"],
                requested_date=item["requested_date"],
                status=item["status"],
                risk_score=risk_score,
                risk_level=risk_level,
                age_days=age_days,
                sla_status=sla_status,
                validation_status=val_status,
                assigned_to=item.get("assigned_to", "Unassigned"),
                recommended_action=recommended_action,
                risk_explanation=explanation_text,
                created_at=datetime.combine(item["requested_date"], datetime.min.time()) + timedelta(hours=9),
                resolved_at=item.get("resolved_at")
            )
            db.session.add(claim)
            db.session.flush()

            # Insert validation results
            for vr in val_results:
                v_entry = ValidationResult(
                    claim_id=claim.id,
                    rule_name=vr["rule_name"],
                    status=vr["status"],
                    message=vr["message"],
                    severity=vr["severity"],
                    created_at=claim.created_at + timedelta(minutes=2)
                )
                db.session.add(v_entry)

            # Insert baseline audit logs
            t_base = claim.created_at
            audit_events = [
                ("Claim Ingested", "SAP Interface (IDOC/RFC)", f"Claim {claim.claim_number} received from Northfield SAP S/4HANA Warranty module.", t_base),
                ("Validation Completed", "SAP Validation Engine", f"Executed 7 automated rule checks. Overall status: {val_status}.", t_base + timedelta(minutes=1)),
                ("Risk Calculated", "Risk Scoring Engine", f"Calculated risk score {risk_score}/100 ({risk_level}). SLA: {sla_status}.", t_base + timedelta(minutes=2))
            ]

            if claim.assigned_to and claim.assigned_to != "Unassigned":
                audit_events.append((
                    "Assigned to Owner",
                    "Operations Manager",
                    f"Claim assigned to {claim.assigned_to} for technical/commercial review.",
                    t_base + timedelta(hours=1)
                ))

            if claim.status == "Resolved":
                audit_events.append((
                    "Claim Resolved",
                    claim.assigned_to or "Warranty Lead",
                    f"Warranty claim resolved and posted. Settlement credit voucher verified in SAP.",
                    claim.resolved_at or (t_base + timedelta(days=2))
                ))

            for action, actor, desc, ts in audit_events:
                db.session.add(AuditLog(
                    claim_id=claim.id,
                    action=action,
                    performed_by=actor,
                    description=desc,
                    timestamp=ts
                ))

            # Add comments
            for user, c_text in item.get("initial_comments", []):
                db.session.add(Comment(
                    claim_id=claim.id,
                    user_name=user,
                    comment=c_text,
                    created_at=t_base + timedelta(hours=2)
                ))

        db.session.commit()
        print(f"Successfully seeded {len(SAMPLE_CLAIMS)} warranty claims into SQLite.")


if __name__ == "__main__":
    from flask import Flask
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///warranty.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    seed_database(app)
