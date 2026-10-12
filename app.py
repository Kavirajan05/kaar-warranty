import os
import io
import csv
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, make_response, abort
from models import db, WarrantyClaim, ValidationResult, AuditLog, Comment
from engine import run_validation_rules, calculate_risk, generate_recommended_action, REFERENCE_DATE, VALID_MASTER_DATA
from seed import seed_database, SAMPLE_CLAIMS

app = Flask(__name__)
app.config["SECRET_KEY"] = "northfield-sap-warranty-demo-key-2026"

# Support for Vercel serverless environment (writable /tmp directory)
IS_VERCEL = os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV")
if IS_VERCEL:
    db_dir = "/tmp"
    db_path = os.path.join(db_dir, "warranty.db")
    bundled_db = os.path.join(os.path.dirname(__file__), "warranty.db")
    if not os.path.exists(db_path) and os.path.exists(bundled_db):
        try:
            import shutil
            shutil.copy(bundled_db, db_path)
        except Exception:
            pass
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///warranty.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Ensure tables and seed data are populated on launch
with app.app_context():
    db.create_all()
    if not WarrantyClaim.query.first():
        seed_database(app)


@app.context_processor
def inject_global_metrics():
    """Injects counts into all templates for global headers and navigation badges."""
    open_count = WarrantyClaim.query.filter(WarrantyClaim.status != 'Resolved').count()
    return {
        'open_exceptions_count': open_count,
        'current_year': 2026,
        'system_ref_date': '2026-10-12'
    }


# ==========================================
# 1. DASHBOARD
# ==========================================
@app.route("/")
@app.route("/dashboard")
def dashboard():
    claims = WarrantyClaim.query.all()
    target_claim = WarrantyClaim.query.filter_by(claim_number="PRD-460082").first()

    total_claims = len(claims)
    unresolved_claims = [c for c in claims if c.status != "Resolved"]
    resolved_claims = [c for c in claims if c.status == "Resolved"]

    total_exceptions = len(unresolved_claims)
    financial_exposure = sum(c.amount for c in unresolved_claims)
    critical_exceptions = sum(1 for c in unresolved_claims if c.risk_level == "CRITICAL")
    sla_at_risk = sum(1 for c in unresolved_claims if c.sla_status == "AT RISK")

    # Calculate average resolution time for resolved claims
    res_times = []
    for c in resolved_claims:
        if c.resolved_at and c.created_at:
            delta_days = (c.resolved_at - c.created_at).total_seconds() / 86400.0
            res_times.append(max(0.5, delta_days))
    avg_resolution_time = round(sum(res_times) / len(res_times), 1) if res_times else 2.4

    kpis = {
        "total_claims": total_claims,
        "total_exceptions": total_exceptions,
        "financial_exposure": financial_exposure,
        "critical_exceptions": critical_exceptions,
        "avg_resolution_time": avg_resolution_time,
        "sla_at_risk": sla_at_risk
    }

    # Risk Distribution Counts
    total_active = total_exceptions if total_exceptions > 0 else 1
    crit_count = sum(1 for c in unresolved_claims if c.risk_level == "CRITICAL")
    high_count = sum(1 for c in unresolved_claims if c.risk_level == "HIGH")
    med_count = sum(1 for c in unresolved_claims if c.risk_level == "MEDIUM")
    low_count = sum(1 for c in unresolved_claims if c.risk_level == "LOW")

    risk_counts = {
        "CRITICAL": crit_count,
        "HIGH": high_count,
        "MEDIUM": med_count,
        "LOW": low_count,
        "pct_critical": round((crit_count / total_active) * 100),
        "pct_high": round((high_count / total_active) * 100),
        "pct_medium": round((med_count / total_active) * 100),
        "pct_low": round((low_count / total_active) * 100),
    }

    # Exception Causes counts across unresolved claims
    cause_sla = sum(1 for c in unresolved_claims if c.sla_status in ("AT RISK", "BREACHED"))
    cause_ageing = sum(1 for c in unresolved_claims if c.age_days >= 3)
    cause_master_data = 0
    cause_approval = 0
    cause_document = 0
    cause_unassigned = sum(1 for c in unresolved_claims if c.assigned_to == "Unassigned")

    for c in unresolved_claims:
        for vr in c.validation_results:
            if vr.status in ("FAIL", "WARNING"):
                if "Master Data" in vr.rule_name:
                    cause_master_data += 1
                elif "Approval" in vr.rule_name:
                    cause_approval += 1
                elif "Document" in vr.rule_name:
                    cause_document += 1

    max_cause = max(1, total_active)
    cause_counts = {
        "sla": cause_sla,
        "ageing": cause_ageing,
        "master_data": cause_master_data,
        "approval": cause_approval,
        "document": cause_document,
        "unassigned": cause_unassigned,
        "pct_sla": min(100, round((cause_sla / max_cause) * 100)),
        "pct_ageing": min(100, round((cause_ageing / max_cause) * 100)),
        "pct_master_data": min(100, round((cause_master_data / max_cause) * 100)),
        "pct_approval": min(100, round((cause_approval / max_cause) * 100)),
        "pct_document": min(100, round((cause_document / max_cause) * 100)),
        "pct_unassigned": min(100, round((cause_unassigned / max_cause) * 100)),
    }

    # Sorted High-Priority Claims (Prioritize Unresolved, then Risk Score DESC, Amount DESC)
    risk_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    high_priority_claims = sorted(
        unresolved_claims,
        key=lambda c: (risk_rank.get(c.risk_level, 0), c.risk_score, c.amount, c.age_days),
        reverse=True
    )[:5]

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        kpis=kpis,
        risk_counts=risk_counts,
        cause_counts=cause_counts,
        high_priority_claims=high_priority_claims,
        target_claim=target_claim
    )


# ==========================================
# 2. EXCEPTION QUEUE (WORKLIST)
# ==========================================
@app.route("/exceptions")
def exceptions():
    query = WarrantyClaim.query

    # Collect filter parameters
    search_q = request.args.get("q", "").strip()
    risk_filter = request.args.get("risk_level", "").strip()
    status_filter = request.args.get("status", "").strip()
    plant_filter = request.args.get("plant", "").strip()
    partner_filter = request.args.get("partner", "").strip()
    owner_filter = request.args.get("owner", "").strip()

    active_filters = []

    if search_q:
        search_pattern = f"%{search_q}%"
        query = query.filter(
            (WarrantyClaim.claim_number.ilike(search_pattern)) |
            (WarrantyClaim.business_partner.ilike(search_pattern)) |
            (WarrantyClaim.material.ilike(search_pattern)) |
            (WarrantyClaim.document_number.ilike(search_pattern))
        )
        active_filters.append(f"Search: '{search_q}'")

    if risk_filter:
        query = query.filter(WarrantyClaim.risk_level == risk_filter)
        active_filters.append(f"Risk: {risk_filter}")

    if status_filter:
        query = query.filter(WarrantyClaim.status == status_filter)
        active_filters.append(f"Status: {status_filter}")

    if plant_filter:
        query = query.filter(WarrantyClaim.plant == plant_filter)
        active_filters.append(f"Plant: {plant_filter}")

    if partner_filter:
        query = query.filter(WarrantyClaim.business_partner == partner_filter)
        active_filters.append(f"Partner: {partner_filter}")

    if owner_filter:
        if owner_filter == "Unassigned":
            query = query.filter(WarrantyClaim.assigned_to == "Unassigned")
            active_filters.append("Owner: Unassigned")
        else:
            query = query.filter(WarrantyClaim.assigned_to == owner_filter)
            active_filters.append(f"Owner: {owner_filter}")

    all_claims = query.all()

    # Sort: Risk Level (CRITICAL -> HIGH -> MEDIUM -> LOW), Risk Score DESC, Amount DESC, Age DESC
    risk_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sorted_claims = sorted(
        all_claims,
        key=lambda c: (
            1 if c.status != "Resolved" else 0,
            risk_rank.get(c.risk_level, 0),
            c.risk_score,
            c.amount,
            c.age_days
        ),
        reverse=True
    )

    # Distinct values for dropdown options
    plants = sorted(list(set(c.plant for c in WarrantyClaim.query.all())))
    partners = sorted(list(set(c.business_partner for c in WarrantyClaim.query.all())))
    owners = sorted(list(set(c.assigned_to for c in WarrantyClaim.query.all() if c.assigned_to)))

    return render_template(
        "exceptions.html",
        active_page="exceptions",
        claims=sorted_claims,
        current_filters={
            "q": search_q,
            "risk_level": risk_filter,
            "status": status_filter,
            "plant": plant_filter,
            "partner": partner_filter,
            "owner": owner_filter
        },
        filter_options={
            "plants": plants,
            "partners": partners,
            "owners": owners
        },
        active_filter_summary=", ".join(active_filters)
    )


# ==========================================
# 3. CLAIM DETAILS & ACTIONS
# ==========================================
@app.route("/claims/<int:claim_id>")
def claim_detail(claim_id):
    claim = db.session.get(WarrantyClaim, claim_id)
    if not claim:
        abort(404)

    return render_template(
        "claim_detail.html",
        active_page="exceptions",
        claim=claim
    )


@app.route("/claims/<int:claim_id>/assign", methods=["POST"])
def assign_owner(claim_id):
    claim = db.session.get(WarrantyClaim, claim_id)
    if not claim:
        abort(404)

    new_owner = request.form.get("assigned_to", "").strip()
    if not new_owner:
        flash("Please select a valid user to assign.", "warning")
        return redirect(url_for("claim_detail", claim_id=claim.id))

    old_owner = claim.assigned_to
    claim.assigned_to = new_owner
    claim.updated_at = datetime.utcnow()

    # Audit log
    audit_desc = f"Owner reassigned from '{old_owner}' to '{new_owner}'."
    log_entry = AuditLog(
        claim_id=claim.id,
        action="Assigned to Owner",
        performed_by="Ravi Kumar (Senior Specialist)",
        description=audit_desc,
        timestamp=datetime.utcnow()
    )
    db.session.add(log_entry)
    db.session.commit()

    flash(f"Claim assigned successfully to {new_owner}.", "success")
    return redirect(url_for("claim_detail", claim_id=claim.id))


@app.route("/claims/<int:claim_id>/comment", methods=["POST"])
def add_comment(claim_id):
    claim = db.session.get(WarrantyClaim, claim_id)
    if not claim:
        abort(404)

    user_name = request.form.get("user_name", "Ravi Kumar").strip()
    comment_text = request.form.get("comment", "").strip()

    if not comment_text:
        flash("Comment cannot be empty.", "warning")
        return redirect(url_for("claim_detail", claim_id=claim.id))

    # Create comment
    comment_entry = Comment(
        claim_id=claim.id,
        user_name=user_name,
        comment=comment_text,
        created_at=datetime.utcnow()
    )
    db.session.add(comment_entry)

    # Add audit log
    audit_desc = f"Operational comment posted by {user_name}: '{comment_text[:60]}...'" if len(comment_text) > 60 else f"Operational comment posted: '{comment_text}'"
    log_entry = AuditLog(
        claim_id=claim.id,
        action="Comment Added",
        performed_by=user_name,
        description=audit_desc,
        timestamp=datetime.utcnow()
    )
    db.session.add(log_entry)
    db.session.commit()

    flash("Comment recorded successfully in claim history.", "success")
    return redirect(url_for("claim_detail", claim_id=claim.id))


@app.route("/claims/<int:claim_id>/resolve", methods=["POST"])
def resolve_claim(claim_id):
    claim = db.session.get(WarrantyClaim, claim_id)
    if not claim:
        abort(404)

    claim.status = "Resolved"
    claim.resolved_at = datetime.utcnow()
    claim.updated_at = datetime.utcnow()

    # Update recommendation
    claim.recommended_action = "Claim Resolved & Closed: Warranty voucher reconciliation complete in SAP FI/CO. No further operational action required."

    # Audit log
    log_entry = AuditLog(
        claim_id=claim.id,
        action="Claim Resolved",
        performed_by=claim.assigned_to if claim.assigned_to != "Unassigned" else "Ravi Kumar (Lead Specialist)",
        description=f"Claim {claim.claim_number} marked as resolved. Warranty credit note verified with vendor.",
        timestamp=datetime.utcnow()
    )
    db.session.add(log_entry)
    db.session.commit()

    flash(f"Claim {claim.claim_number} resolved successfully.", "success")
    return redirect(url_for("claim_detail", claim_id=claim.id))


@app.route("/claims/<int:claim_id>/revalidate", methods=["POST"])
def revalidate_claim(claim_id):
    claim = db.session.get(WarrantyClaim, claim_id)
    if not claim:
        abort(404)

    # Convert model to dict for engine
    claim_data = {
        "company_code": claim.company_code,
        "plant": claim.plant,
        "storage_location": claim.storage_location,
        "cost_center": claim.cost_center,
        "material": claim.material,
        "business_partner": claim.business_partner,
        "document_number": claim.document_number,
        "amount": claim.amount,
        "requested_date": claim.requested_date,
        "status": claim.status,
        "assigned_to": claim.assigned_to,
        "pending_approval": False
    }

    # Execute engine
    new_results, age_days, sla_status = run_validation_rules(claim_data)
    new_score, new_level, explanation_text, _ = calculate_risk(
        claim.amount, age_days, sla_status, new_results
    )
    rec = generate_recommended_action(claim_data, new_results, new_level, sla_status)

    # Remove old validation results and add new
    ValidationResult.query.filter_by(claim_id=claim.id).delete()
    for vr in new_results:
        db.session.add(ValidationResult(
            claim_id=claim.id,
            rule_name=vr["rule_name"],
            status=vr["status"],
            message=vr["message"],
            severity=vr["severity"],
            created_at=datetime.utcnow()
        ))

    claim.risk_score = new_score
    claim.risk_level = new_level
    claim.age_days = age_days
    claim.sla_status = sla_status
    claim.risk_explanation = explanation_text
    claim.recommended_action = f"{rec['action']}: {rec['detail']}"
    claim.updated_at = datetime.utcnow()

    # Log re-validation in audit
    db.session.add(AuditLog(
        claim_id=claim.id,
        action="Validation Re-evaluated",
        performed_by="SAP Validation Engine",
        description=f"Automated business validation rules re-evaluated. Risk score: {new_score} ({new_level}).",
        timestamp=datetime.utcnow()
    ))
    db.session.commit()

    flash("Automated validation rules re-evaluated successfully.", "info")
    return redirect(url_for("claim_detail", claim_id=claim.id))


# ==========================================
# 4. ANALYTICS
# ==========================================
@app.route("/analytics")
def analytics():
    claims = WarrantyClaim.query.all()
    open_claims = [c for c in claims if c.status != "Resolved"]
    resolved_claims = [c for c in claims if c.status == "Resolved"]

    total_open_exposure = sum(c.amount for c in open_claims)
    total_resolved_exposure = sum(c.amount for c in resolved_claims)

    total_active = len(open_claims) if open_claims else 1

    # 1. Risk Tier breakdown
    risk_tiers = [
        {"name": "Critical", "score_range": "80–100", "key": "CRITICAL", "color_class": "text-danger fw-bold", "bg_class": "bg-danger"},
        {"name": "High", "score_range": "60–79", "key": "HIGH", "color_class": "text-warning-emphasis fw-bold", "bg_class": "bg-warning"},
        {"name": "Medium", "score_range": "30–59", "key": "MEDIUM", "color_class": "text-secondary fw-semibold", "bg_class": "bg-info"},
        {"name": "Low", "score_range": "0–29", "key": "LOW", "color_class": "text-success fw-semibold", "bg_class": "bg-success"}
    ]
    for rt in risk_tiers:
        count = sum(1 for c in open_claims if c.risk_level == rt["key"])
        rt["count"] = count
        rt["percentage"] = round((count / total_active) * 100)

    # 2. Cause breakdown
    cause_data = [
        {"name": "SLA Breach / At Risk", "count": sum(1 for c in open_claims if c.sla_status in ("AT RISK", "BREACHED")), "bg_class": "bg-danger"},
        {"name": "Ageing > 3 Days", "count": sum(1 for c in open_claims if c.age_days >= 3), "bg_class": "bg-warning"},
        {"name": "Missing Master Data", "count": 0, "bg_class": "bg-info"},
        {"name": "Commercial Approval Pending", "count": 0, "bg_class": "bg-secondary"},
        {"name": "Document Mismatch", "count": 0, "bg_class": "bg-dark"},
        {"name": "Unassigned Specialist", "count": sum(1 for c in open_claims if c.assigned_to == "Unassigned"), "bg_class": "bg-warning opacity-75"}
    ]
    for c in open_claims:
        for vr in c.validation_results:
            if vr.status in ("FAIL", "WARNING"):
                if "Master Data" in vr.rule_name:
                    cause_data[2]["count"] += 1
                elif "Approval" in vr.rule_name:
                    cause_data[3]["count"] += 1
                elif "Document" in vr.rule_name:
                    cause_data[4]["count"] += 1

    for cd in cause_data:
        cd["percentage"] = min(100, round((cd["count"] / total_active) * 100))

    # 3. Ageing Buckets
    b_0_2 = [c for c in open_claims if c.age_days <= 2]
    b_3_5 = [c for c in open_claims if 3 <= c.age_days <= 5]
    b_gt_5 = [c for c in open_claims if c.age_days > 5]

    ageing_buckets = [
        {"label": "0–2 Days (Optimal Handling)", "count": len(b_0_2), "pct": round((len(b_0_2) / total_active) * 100), "amount": sum(c.amount for c in b_0_2), "bg_class": "bg-success"},
        {"label": "3–5 Days (Approaching SLA Limit)", "count": len(b_3_5), "pct": round((len(b_3_5) / total_active) * 100), "amount": sum(c.amount for c in b_3_5), "bg_class": "bg-warning"},
        {"label": ">5 Days (Breached / Aged Exception)", "count": len(b_gt_5), "pct": round((len(b_gt_5) / total_active) * 100), "amount": sum(c.amount for c in b_gt_5), "bg_class": "bg-danger"}
    ]

    # 4. Plant Performance
    plant_names = {
        "1101": "Cambridge Tech Park",
        "1102": "Oxford Science Hub",
        "1201": "London Research Centre",
        "1305": "Manchester Advanced Energy"
    }
    plants_summary = {}
    for c in open_claims:
        p = c.plant
        if p not in plants_summary:
            plants_summary[p] = {"plant": p, "location_name": plant_names.get(p, "Northfield Facility"), "count": 0, "amount": 0.0}
        plants_summary[p]["count"] += 1
        plants_summary[p]["amount"] += c.amount
    plant_metrics = sorted(plants_summary.values(), key=lambda x: x["amount"], reverse=True)

    # 5. Partner Exposure Ranking
    partner_summary = {}
    for c in open_claims:
        bp = c.business_partner
        if bp not in partner_summary:
            partner_summary[bp] = {"partner": bp, "count": 0, "amount": 0.0}
        partner_summary[bp]["count"] += 1
        partner_summary[bp]["amount"] += c.amount

    for v in partner_summary.values():
        v["avg_amount"] = v["amount"] / v["count"] if v["count"] > 0 else 0.0
    partner_metrics = sorted(partner_summary.values(), key=lambda x: x["amount"], reverse=True)[:5]

    analytics_data = {
        "total_open_exposure": total_open_exposure,
        "total_resolved_exposure": total_resolved_exposure,
        "open_claims_count": len(open_claims),
        "resolved_claims_count": len(resolved_claims),
        "high_and_critical_count": sum(1 for c in open_claims if c.risk_level in ("HIGH", "CRITICAL")),
        "sla_breached_count": sum(1 for c in open_claims if c.sla_status == "BREACHED"),
        "risk_distribution": risk_tiers,
        "cause_distribution": cause_data,
        "ageing_buckets": ageing_buckets,
        "plant_metrics": plant_metrics,
        "partner_metrics": partner_metrics
    }

    return render_template(
        "analytics.html",
        active_page="analytics",
        analytics=analytics_data
    )


# ==========================================
# 5. REPORTS & CSV EXPORT
# ==========================================
@app.route("/reports")
def reports():
    claims = WarrantyClaim.query.order_by(WarrantyClaim.risk_score.desc()).all()
    return render_template(
        "reports.html",
        active_page="reports",
        claims=claims
    )


@app.route("/reports/export.csv")
def export_csv():
    claims = WarrantyClaim.query.order_by(WarrantyClaim.risk_score.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header Row
    writer.writerow([
        "Claim Number",
        "Business Partner",
        "Material",
        "Plant",
        "Storage Location",
        "Cost Centre",
        "Amount (GBP)",
        "Requested Date",
        "Age (Days)",
        "SLA Status",
        "Validation Status",
        "Risk Score",
        "Risk Level",
        "Status",
        "Assigned Owner",
        "Recommended Next Action",
        "Created At"
    ])

    for c in claims:
        writer.writerow([
            c.claim_number,
            c.business_partner,
            c.material,
            c.plant,
            c.storage_location,
            c.cost_center,
            f"{c.amount:.2f}",
            c.requested_date.strftime("%Y-%m-%d") if c.requested_date else "",
            c.age_days,
            c.sla_status,
            c.validation_status,
            c.risk_score,
            c.risk_level,
            c.status,
            c.assigned_to,
            c.recommended_action,
            c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else ""
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=northfield_sap_warranty_exceptions.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    return response


# ==========================================
# 6. RESET DEMO DATA
# ==========================================
@app.route("/reset-demo")
def reset_demo():
    """Wipes and re-seeds SQLite database with baseline demo state."""
    db.drop_all()
    db.create_all()
    seed_database(app)
    flash("Database reset successfully to initial demonstration state.", "info")
    return redirect(url_for("dashboard"))


# ==========================================
# 7. ERROR HANDLING
# ==========================================
@app.errorhandler(404)
def not_found_error(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
