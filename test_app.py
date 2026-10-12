import unittest
from app import app, db
from models import WarrantyClaim, ValidationResult, AuditLog, Comment
from seed import seed_database

class WarrantyAppTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()
            seed_database(app)

    def test_dashboard_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PRD-460082", response.data)
        self.assertIn(b"Warranty Exception Management Dashboard", response.data)
        self.assertIn(b"Total Claims", response.data)

    def test_exceptions_queue_and_filters(self):
        # All exceptions
        response = self.client.get("/exceptions")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PRD-460082", response.data)

        # Filter by CRITICAL
        response_crit = self.client.get("/exceptions?risk_level=CRITICAL")
        self.assertEqual(response_crit.status_code, 200)
        self.assertIn(b"PRD-520194", response_crit.data)

        # Filter by Search
        response_search = self.client.get("/exceptions?q=Baltic")
        self.assertEqual(response_search.status_code, 200)
        self.assertIn(b"Baltic Freight BV", response_search.data)

    def test_claim_detail_target_record(self):
        with app.app_context():
            target = WarrantyClaim.query.filter_by(claim_number="PRD-460082").first()
            target_id = target.id

        response = self.client.get(f"/claims/{target_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PRD-460082", response.data)
        self.assertIn(b"125,250", response.data)
        self.assertIn(b"Lithium Module LM-90", response.data)
        self.assertIn(b"Baltic Freight BV", response.data)
        self.assertIn(b"Mandatory Field Check", response.data)
        self.assertIn(b"Why is this claim HIGH risk?", response.data)

    def test_complete_demo_workflow(self):
        with app.app_context():
            target = WarrantyClaim.query.filter_by(claim_number="PRD-460082").first()
            target_id = target.id
            self.assertEqual(target.assigned_to, "Unassigned")
            self.assertNotEqual(target.status, "Resolved")

        # 1. Assign Owner to Ravi Kumar
        assign_resp = self.client.post(
            f"/claims/{target_id}/assign",
            data={"assigned_to": "Ravi Kumar"},
            follow_redirects=True
        )
        self.assertEqual(assign_resp.status_code, 200)
        self.assertIn(b"Claim assigned successfully to Ravi Kumar", assign_resp.data)

        with app.app_context():
            claim = db.session.get(WarrantyClaim, target_id)
            self.assertEqual(claim.assigned_to, "Ravi Kumar")
            # Verify Audit Log
            latest_audit = AuditLog.query.filter_by(claim_id=target_id).order_by(AuditLog.timestamp.desc()).first()
            self.assertEqual(latest_audit.action, "Assigned to Owner")

        # 2. Add Comment
        comment_resp = self.client.post(
            f"/claims/{target_id}/comment",
            data={"user_name": "Ravi Kumar", "comment": "Contacted Baltic Freight logistics lead. Technical report expected in 2 hours."},
            follow_redirects=True
        )
        self.assertEqual(comment_resp.status_code, 200)
        self.assertIn(b"Comment recorded successfully", comment_resp.data)

        with app.app_context():
            comments = Comment.query.filter_by(claim_id=target_id).all()
            self.assertTrue(any("Baltic Freight" in c.comment for c in comments))

        # 3. Mark as Resolved
        resolve_resp = self.client.post(
            f"/claims/{target_id}/resolve",
            follow_redirects=True
        )
        self.assertEqual(resolve_resp.status_code, 200)
        self.assertIn(b"resolved successfully", resolve_resp.data)

        with app.app_context():
            claim = db.session.get(WarrantyClaim, target_id)
            self.assertEqual(claim.status, "Resolved")
            self.assertIsNotNone(claim.resolved_at)

        # 4. Check that Dashboard reflects updated status
        dash_resp = self.client.get("/dashboard")
        self.assertEqual(dash_resp.status_code, 200)

    def test_analytics_and_reports(self):
        analytics_resp = self.client.get("/analytics")
        self.assertEqual(analytics_resp.status_code, 200)
        self.assertIn(b"Executive Warranty Exception Analytics", analytics_resp.data)

        reports_resp = self.client.get("/reports")
        self.assertEqual(reports_resp.status_code, 200)
        self.assertIn(b"Audit & Compliance Reporting", reports_resp.data)

        csv_resp = self.client.get("/reports/export.csv")
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp.content_type, "text/csv; charset=utf-8")
        self.assertIn(b"PRD-460082", csv_resp.data)
        self.assertIn(b"Claim Number,Business Partner,Material", csv_resp.data)

    def test_404_error_handling(self):
        response = self.client.get("/claims/999999")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"404", response.data)
        self.assertIn(b"Warranty Claim Not Found", response.data)

if __name__ == "__main__":
    unittest.main()
