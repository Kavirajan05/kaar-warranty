# SAP Warranty Claim Validation Prototype — Northfield University

> **Process:** Warranty – Warranty Claim Validation  
> **SAP Module:** SAP Warranty Management (WTY / CS / Aftermarket Service Transformation)  
> **Target Scenario:** Northfield University (Energy Modules & Research Equipment)  
> **Target Record:** `PRD-460082` (£125,250 &bull; High Risk &bull; SLA At Risk)

---

## 1. Quickstart & Installation

The prototype is a self-contained, lightweight Python/Flask enterprise application backed by SQLite. No Docker, no external cloud dependencies, and no live SAP credentials required.

### Setup Virtual Environment
```bash
python -m venv venv
```

### Activate (Windows)
```bash
venv\Scripts\activate
```

*(On macOS/Linux: `source venv/bin/activate`)*

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Application
```bash
python app.py
```

### Access Prototype
Open your browser at:
```text
http://127.0.0.1:5000
```
*(The SQLite database `warranty.db` is automatically created and seeded with the full benchmark dataset on first boot).*

---

## 1.1 Vercel Cloud Deployment

The repository is pre-configured with `vercel.json`, `api/index.py`, and automatic `/tmp` SQLite persistence for serverless hosting on **Vercel**.

### Deploy via Vercel CLI
```bash
npm install -g vercel
vercel
```
Accept default settings (Project root, Framework: Other).

### Deploy via GitHub
1. Push this folder to a GitHub repository.
2. In [Vercel Dashboard](https://vercel.com/new), click **Import Git Repository**.
3. Click **Deploy**. Vercel will automatically detect `vercel.json` and deploy the Python serverless app.

---

## 2. Business Problem & Solution

### Problem
Northfield University operates SAP S/4HANA Warranty Management, but business users currently rely on retrospective spreadsheets, email coordination, and manual status chasing. This causes:
- Inability to quickly prioritize high-exposure claims approaching SLA breach.
- Working capital tied up in stalled supplier warranty reimbursements.
- Lack of explainable root causes for exception failures.
- Missing accountability and disconnected audit history.

### Solution
This application serves as an **operational exception-management and prioritization layer** directly on top of SAP Warranty Management. It dynamically validates transactional parameters, calculates explainable risk scores (0–100), and provides a role-based action queue with full governance auditability.

---

## 3. Explainable Risk Calculation (0–100 Points)

The risk model is 100% transparent and deterministic (no opaque AI or black-box ML):

$$\text{Risk Score} = \text{Financial Exposure (30)} + \text{Ageing (25)} + \text{SLA Impact (25)} + \text{Validation Exceptions (20)}$$

### Scoring Dimensions

1. **Financial Exposure (Max 30 Points):**
   - $< £10,000 \rightarrow$ 5 pts
   - $£10,000 - £50,000 \rightarrow$ 15 pts
   - $> £50,000 \rightarrow$ 30 pts

2. **Claim Ageing (Max 25 Points):**
   - $0 - 2 \text{ days} \rightarrow$ 5 pts
   - $3 - 5 \text{ days} \rightarrow$ 15 pts
   - $> 5 \text{ days} \rightarrow$ 25 pts

3. **SLA / Service Impact (Max 25 Points):**
   - $\text{SAFE} (\le 3 \text{ days}) \rightarrow$ 0 pts
   - $\text{AT RISK} (4 - 5 \text{ days}) \rightarrow$ 15 pts
   - $\text{BREACHED} (> 5 \text{ days}) \rightarrow$ 25 pts

4. **Validation Exceptions (Max 20 Points):**
   - $0 \text{ exceptions} \rightarrow$ 0 pts
   - $1 \text{ exception} \rightarrow$ 5 pts
   - $2 \text{ exceptions} \rightarrow$ 15 pts
   - $3+ \text{ exceptions} \rightarrow$ 20 pts

### Classification Tiers
- **0–29:** LOW (Green)
- **30–59:** MEDIUM (Yellow)
- **60–79:** HIGH (Orange)
- **80–100:** CRITICAL (Red)

### Benchmark Assessment Record: `PRD-460082`
- **Claim Amount:** £125,250 ($> £50\text{k} \rightarrow$ **30 pts**)
- **Age:** 5 Days ($3 - 5 \text{ days} \rightarrow$ **15 pts**)
- **SLA:** AT RISK (**15 pts**)
- **Validation Exceptions:** Ageing & SLA Alerts (**15 pts**)
- **Total Risk Score:** **75 / 100 (HIGH RISK)**

---

## 4. End-to-End Interview Demo Flow (5–7 Minutes)

| Step | Action | What to Demonstrate / Say |
|---|---|---|
| **Step 1** | Open `http://127.0.0.1:5000/` | *"This is the management overview of warranty exceptions at Northfield University."* Show Top 6 KPI cards. |
| **Step 2** | Review Dashboard KPIs | Highlight total exposure (£480k+), 2 Critical exceptions, and SLA At Risk items. |
| **Step 3** | Navigate to Exceptions | Click **Exceptions** in the top navigation bar to access the prioritised work queue. |
| **Step 4** | Locate Claim `PRD-460082` | Show the highlighted demo claim at the top of the queue or use the instant search filter. |
| **Step 5** | Explain Risk Drivers | Point out the £125,250 exposure, 5 days ageing, SLA At Risk status, and **Score: 75 (HIGH)**. |
| **Step 6** | Open Claim Details | Click **Open** on `PRD-460082` to view transaction metadata and validation diagnostics. |
| **Step 7** | Inspect Validation Results | Show the 7 executed rules (Mandatory fields ✓, Master data ✓, Document check ✓, Ageing ⚠, SLA ⚠). |
| **Step 8** | Review Risk Breakdown | Show the **Why is this claim HIGH risk?** explainable panel with exact point contributions. |
| **Step 9** | Review Recommended Action | Show the system's actionable advice: *"Assign Priority Owner & Escalate High-Exposure SLA"*. |
| **Step 10** | Assign Owner | In **Assign Accountable Owner**, select `Ravi Kumar` and click **Update Assignment**. Verify success banner. |
| **Step 11** | Add Comment | Under Operational Comments, enter *"Contacted Baltic Freight logistics lead. Technical report expected in 2 hours."* and submit. |
| **Step 12** | Resolve Claim | Click **Mark as Resolved**. Confirm the dialog. |
| **Step 13** | Review Audit Timeline | Point out the immutable audit entries showing Ingestion $\rightarrow$ Validation $\rightarrow$ Risk $\rightarrow$ Assignment $\rightarrow$ Comment $\rightarrow$ Resolution. |
| **Step 14** | Return to Dashboard | Notice that the exception count decreased, resolved count increased, and analytics updated in real-time. |
| **Step 15** | Show Analytics & Reports | Navigate to `/analytics` (cause distribution & plant metrics) and `/reports` (click **Download CSV**). |

---

## 5. Technical Architecture & Future SAP Integration

### Current Prototype Architecture
```text
Local SQLite (warranty.db)
        ↓
SQLAlchemy ORM (models.py)
        ↓
Validation & Risk Scoring Engine (engine.py)
        ↓
Flask Application Controller (app.py)
        ↓
SAP Fiori / Horizon-Inspired UI (Jinja2 + Bootstrap 5)
```

### Production SAP Integration Roadmap
The SQLite database serves as a decoupled repository that maps directly to SAP standard entities:

```text
SAP S/4HANA 2023 On-Premise / Cloud
   (WTY / CS-ACM Claims, MARA, BUT000, EKKO)
        ↓
SAP OData V4 APIs (e.g. API_WARRANTYCLAIM_SRV)
        ↓
SAP BTP Destination & Connectivity Service
        ↓
SAP Cloud Application Programming Model (CAP) / Flask Microservice
        ↓
Operational Exception Management Work Queue
```

In a production deployment:
1. `models.py` queries would be replaced with HTTP calls to standard SAP S/4HANA OData entities (`A_WarrantyClaim`, `A_WarrantyClaimItem`).
2. Resolution updates would issue an `OData PATCH / Function Import` to transition the claim status directly in SAP.
3. The validation engine rules match standard SAP BRFplus / custom rule engine logic.
