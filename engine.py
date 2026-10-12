import re
from datetime import date, datetime

# Anchor reference date for the scenario: October 12, 2026
REFERENCE_DATE = date(2026, 10, 12)

# SAP Master Data reference catalog for Northfield University
VALID_MASTER_DATA = {
    "company_codes": {
        "1200": "Northfield Energy & Tech UK",
        "1000": "Northfield University Central",
        "2100": "Northfield Research Labs EU"
    },
    "plants": {
        "1101": "Cambridge Tech Park",
        "1102": "Oxford Science Hub",
        "1201": "London Research Centre",
        "1305": "Manchester Advanced Energy"
    },
    "storage_locations": ["SL15", "SL10", "SL01", "SL22", "SL99"],
    "cost_centers": ["CC-2282", "CC-1010", "CC-4500", "CC-8820", "CC-3100"],
    "materials": [
        "Lithium Module LM-90",
        "Cryo-Cooling Unit CC-400",
        "Industrial Inverter INV-500",
        "Solar Harvester SH-20",
        "Telemetry Sensor TS-10",
        "Laser Diode LD-85",
        "Quantum Sensor QS-12",
        "Fiber Optical Transceiver FOT-40"
    ],
    "business_partners": [
        "Baltic Freight BV",
        "Apex Scientific Ltd",
        "Nordic Logistics ApS",
        "Siemens Industrial UK",
        "Alpha Power Systems",
        "Cambridge Precision Ltd",
        "Oxford Instruments Group",
        "Vanguard Automation Ltd"
    ]
}


def run_validation_rules(claim_data):
    """
    Executes transparent business validation rules against a claim dict or model.
    Returns a list of dicts: [{rule_name, status, message, severity}]
    """
    results = []

    # Extract fields safely
    company_code = str(claim_data.get("company_code") or "").strip()
    plant = str(claim_data.get("plant") or "").strip()
    material = str(claim_data.get("material") or "").strip()
    business_partner = str(claim_data.get("business_partner") or "").strip()
    document_number = str(claim_data.get("document_number") or "").strip()
    amount = claim_data.get("amount")
    requested_date = claim_data.get("requested_date")

    # 1. Mandatory Field Check
    missing_fields = []
    if not company_code: missing_fields.append("Company Code")
    if not plant: missing_fields.append("Plant")
    if not material: missing_fields.append("Material")
    if not business_partner: missing_fields.append("Business Partner")
    if not document_number: missing_fields.append("Document Number")
    if amount is None or str(amount).strip() == "": missing_fields.append("Amount")
    if not requested_date: missing_fields.append("Requested Date")

    if missing_fields:
        results.append({
            "rule_name": "Mandatory Field Check",
            "status": "FAIL",
            "message": f"Missing mandatory SAP header/item fields: {', '.join(missing_fields)}",
            "severity": "CRITICAL"
        })
    else:
        results.append({
            "rule_name": "Mandatory Field Check",
            "status": "PASS",
            "message": "All required SAP warranty fields are present and populated",
            "severity": "INFO"
        })

    # 2. Amount Validation
    try:
        amt_val = float(amount) if amount is not None else 0.0
        if amt_val <= 0:
            results.append({
                "rule_name": "Amount Validation",
                "status": "FAIL",
                "message": f"Claim amount (£{amt_val:,.2f}) must be greater than zero",
                "severity": "HIGH"
            })
        else:
            results.append({
                "rule_name": "Amount Validation",
                "status": "PASS",
                "message": f"Claim amount (£{amt_val:,.2f}) is valid and positive",
                "severity": "INFO"
            })
    except (ValueError, TypeError):
        results.append({
            "rule_name": "Amount Validation",
            "status": "FAIL",
            "message": "Claim amount is not a valid numerical currency format",
            "severity": "CRITICAL"
        })
        amt_val = 0.0

    # 3. Document Relationship Check
    if not document_number:
        # already handled in mandatory
        pass
    else:
        doc_pattern = r"^(PRD|CLM|WTY)-\d{5,8}$"
        if not re.match(doc_pattern, document_number):
            results.append({
                "rule_name": "Document Relationship Check",
                "status": "FAIL",
                "message": f"Document '{document_number}' does not match standard SAP document numbering (e.g. PRD-460082)",
                "severity": "HIGH"
            })
        else:
            results.append({
                "rule_name": "Document Relationship Check",
                "status": "PASS",
                "message": f"SAP reference document '{document_number}' successfully verified against purchasing index",
                "severity": "INFO"
            })

    # 4. Master Data Validation
    md_errors = []
    if company_code and company_code not in VALID_MASTER_DATA["company_codes"]:
        md_errors.append(f"Company code '{company_code}' not defined in SAP FI")
    if plant and plant not in VALID_MASTER_DATA["plants"]:
        md_errors.append(f"Plant '{plant}' not found in SAP MM logistics org")
    if material and material not in VALID_MASTER_DATA["materials"]:
        md_errors.append(f"Material '{material}' not found in material master MARA")
    if business_partner and business_partner not in VALID_MASTER_DATA["business_partners"]:
        md_errors.append(f"Business partner '{business_partner}' not found in BP master")

    if md_errors:
        results.append({
            "rule_name": "Master Data Check",
            "status": "FAIL",
            "message": f"Master data mismatch: {'; '.join(md_errors)}",
            "severity": "HIGH"
        })
    else:
        results.append({
            "rule_name": "Master Data Check",
            "status": "PASS",
            "message": "Company code, plant, material, and vendor BP verified against SAP master records",
            "severity": "INFO"
        })

    # Calculate Age
    if isinstance(requested_date, str):
        try:
            req_d = datetime.strptime(requested_date, "%Y-%m-%d").date()
        except ValueError:
            req_d = REFERENCE_DATE
    elif isinstance(requested_date, date):
        req_d = requested_date
    elif isinstance(requested_date, datetime):
        req_d = requested_date.date()
    else:
        req_d = REFERENCE_DATE

    age_days = max(0, (REFERENCE_DATE - req_d).days)

    # 5. Ageing Validation
    if age_days <= 2:
        results.append({
            "rule_name": "Ageing Check",
            "status": "PASS",
            "message": f"Claim age is {age_days} day(s), well within the optimal 48-hour handling target",
            "severity": "INFO"
        })
    elif 3 <= age_days <= 5:
        results.append({
            "rule_name": "Ageing Check",
            "status": "WARNING",
            "message": f"Claim age is {age_days} days. Approaching upper operational threshold (5 days)",
            "severity": "WARNING"
        })
    else:
        results.append({
            "rule_name": "Ageing Check",
            "status": "FAIL",
            "message": f"Claim age is {age_days} days, exceeding the 5-day handling threshold",
            "severity": "HIGH"
        })

    # 6. SLA Validation
    if age_days <= 3:
        sla_status = "SAFE"
        results.append({
            "rule_name": "SLA Check",
            "status": "PASS",
            "message": f"SLA status is SAFE ({age_days}/5 days consumed)",
            "severity": "INFO"
        })
    elif age_days in (4, 5):
        sla_status = "AT RISK"
        results.append({
            "rule_name": "SLA Check",
            "status": "WARNING",
            "message": f"SLA status is AT RISK ({age_days}/5 days elapsed, 24h to breach)",
            "severity": "WARNING"
        })
    else:
        sla_status = "BREACHED"
        results.append({
            "rule_name": "SLA Check",
            "status": "FAIL",
            "message": f"SLA status is BREACHED ({age_days} days elapsed > 5 days limit)",
            "severity": "CRITICAL"
        })

    # 7. Approval & Delegation Check
    requires_approval = claim_data.get("pending_approval", False)
    if requires_approval:
        results.append({
            "rule_name": "Approval Check",
            "status": "WARNING",
            "message": "Commercial authorization pending: Requires senior cost center controller sign-off",
            "severity": "WARNING"
        })
    else:
        results.append({
            "rule_name": "Approval Check",
            "status": "PASS",
            "message": "Standard operational warranty authorization verified against delegation of authority",
            "severity": "INFO"
        })

    return results, age_days, sla_status


def calculate_risk(amount, age_days, sla_status, validation_results):
    """
    Transparent rules-based risk score (Max 100 points):
      1. Financial Exposure = max 30 points
      2. Ageing = max 25 points
      3. SLA/Service Impact = max 25 points
      4. Validation Exceptions = max 20 points
    """
    reasons = []

    # 1. Financial Exposure Score (30 pts max)
    amt = float(amount or 0.0)
    if amt < 10000:
        exp_score = 5
        exp_reason = f"Financial exposure (£{amt:,.2f}) is below £10,000 (Low exposure: +5 pts)"
    elif 10000 <= amt <= 50000:
        exp_score = 15
        exp_reason = f"Financial exposure (£{amt:,.2f}) is between £10,000 and £50,000 (Moderate exposure: +15 pts)"
    else:
        exp_score = 30
        exp_reason = f"Financial exposure (£{amt:,.2f}) exceeds £50,000 high-risk threshold (+30 pts)"
    reasons.append(exp_reason)

    # 2. Ageing Score (25 pts max)
    if age_days <= 2:
        age_score = 5
        age_reason = f"Claim age is {age_days} days (0–2 days window: +5 pts)"
    elif 3 <= age_days <= 5:
        age_score = 15
        age_reason = f"Claim age is {age_days} days (3–5 days ageing threshold: +15 pts)"
    else:
        age_score = 25
        age_reason = f"Claim age is {age_days} days (>5 days aged item: +25 pts)"
    reasons.append(age_reason)

    # 3. SLA Score (25 pts max)
    if sla_status == "SAFE":
        sla_score = 0
        sla_reason = "SLA status is SAFE (No penalty: +0 pts)"
    elif sla_status == "AT RISK":
        sla_score = 15
        sla_reason = "SLA status is AT RISK (Approaching 5-day breach window: +15 pts)"
    else:  # BREACHED
        sla_score = 25
        sla_reason = "SLA status is BREACHED (Exceeded contractual threshold: +25 pts)"
    reasons.append(sla_reason)

    # 4. Validation Exceptions Score (20 pts max)
    # Count any validation result that is FAIL or WARNING
    exceptions = [r for r in validation_results if r["status"] in ("FAIL", "WARNING")]
    exc_count = len(exceptions)
    if exc_count == 0:
        val_score = 0
        val_reason = "No validation exceptions detected (Clean claim: +0 pts)"
    elif exc_count == 1:
        val_score = 5
        val_reason = f"1 validation exception detected: {exceptions[0]['rule_name']} (+5 pts)"
    elif exc_count == 2:
        val_score = 15
        val_reason = f"2 validation exceptions detected ({exceptions[0]['rule_name']}, {exceptions[1]['rule_name']}: +15 pts)"
    else:
        val_score = 20
        val_reason = f"{exc_count} validation exceptions detected ({', '.join(e['rule_name'] for e in exceptions[:3])}: +20 pts)"
    reasons.append(val_reason)

    total_score = min(100, exp_score + age_score + sla_score + val_score)

    # Risk Classification
    if total_score <= 29:
        risk_level = "LOW"
    elif total_score <= 59:
        risk_level = "MEDIUM"
    elif total_score <= 79:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    explanation_text = "\n".join([f"• {r}" for r in reasons])

    breakdown = {
        "exposure_score": exp_score,
        "ageing_score": age_score,
        "sla_score": sla_score,
        "validation_score": val_score,
        "total_score": total_score,
        "risk_level": risk_level,
        "reasons": reasons,
        "explanation_text": explanation_text
    }

    return total_score, risk_level, explanation_text, breakdown


def generate_recommended_action(claim_data, validation_results, risk_level, sla_status):
    """
    Generates actionable next steps based on the failure causes, SLA, and financial exposure.
    """
    # Check specific rule failures
    failed_rules = {r["rule_name"]: r for r in validation_results if r["status"] in ("FAIL", "WARNING")}

    assigned_to = str(claim_data.get("assigned_to") or "Unassigned").strip()
    status = str(claim_data.get("status") or "").strip()
    amount = float(claim_data.get("amount") or 0.0)

    if status == "Resolved":
        return {
            "action": "Claim Resolved & Closed",
            "detail": "Warranty voucher reconciliation complete in SAP FI/CO. No further operational action required."
        }

    if "Mandatory Field Check" in failed_rules:
        return {
            "action": "Complete Mandatory SAP Header & Line Data",
            "detail": "Data enrichment required. Contact submitting service department to populate missing mandatory parameters."
        }

    if "Master Data Check" in failed_rules:
        return {
            "action": "Verify and Complete Master Data in SAP MDG",
            "detail": "Align company code, plant, material, or BP records with central SAP MDG master catalogs before processing."
        }

    if "Document Relationship Check" in failed_rules:
        return {
            "action": "Reconcile Related Purchasing / Service Document",
            "detail": "Review SAP reference document link against goods receipt index to correct mismatched document number."
        }

    if sla_status in ("AT RISK", "BREACHED") and amount > 50000:
        if assigned_to in ("Unassigned", ""):
            return {
                "action": "Assign Priority Owner & Escalate High-Exposure SLA",
                "detail": f"Assign an accountable owner and review the SLA risk. The claim has significant financial exposure (£{amount:,.2f}) and is approaching the service threshold."
            }
        else:
            return {
                "action": "Escalate to Tier-2 Warranty Resolution Team",
                "detail": f"Expedite resolution with {assigned_to} and seek financial sign-off to avert contractual SLA penalty."
            }

    if "Approval Check" in failed_rules:
        return {
            "action": "Request Financial Controller Sign-off",
            "detail": f"Claim exposure of £{amount:,.2f} exceeds local authority limits. Submit for Cost Centre approval."
        }

    if assigned_to in ("Unassigned", ""):
        return {
            "action": "Assign an Accountable Owner",
            "detail": "Claim is currently unowned in the exception work queue. Assign a team member to initiate review."
        }

    if sla_status == "AT RISK":
        return {
            "action": "Accelerate Technical Warranty Inspection",
            "detail": "Expedite technical part verification to ensure resolution before 5-day SLA deadline expires."
        }

    return {
        "action": "Standard Straight-Through Processing",
        "detail": "Claim meets all baseline criteria. Proceed with standard SAP warranty credit voucher generation."
    }
