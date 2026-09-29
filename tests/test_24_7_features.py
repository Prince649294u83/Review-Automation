import os
import unittest
import json
from datetime import datetime, timezone

# Ensure scheduler is disabled during testing to avoid background jobs and file locks
os.environ["FLASK_TESTING"] = "1"
os.environ["ENABLE_SCHEDULER"] = "false"

import db
import worker
from app import app

class Test247Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.DB_PATH = "test_reviews.db"
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        # Cleanup test db
        if os.path.exists("test_reviews.db"):
            try:
                os.remove("test_reviews.db")
            except Exception:
                pass
        for ext in ["-wal", "-shm"]:
            f = "test_reviews.db" + ext
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        # Clean table before each test
        with db.get_connection() as conn:
            conn.execute("DELETE FROM reviews")

    def test_database_crud_and_wal(self):
        """Test DB initialization, insertion, querying, and updating."""
        review_id = "test-rev-001"
        self.assertFalse(db.review_exists(review_id))

        db.insert_review(
            review_id,
            "Alice Sharma",
            5,
            "Amazing Coorg pandi curry and hospitable staff!",
            datetime.now(timezone.utc).isoformat()
        )
        self.assertTrue(db.review_exists(review_id))

        rev = db.get_review_by_id(review_id)
        self.assertIsNotNone(rev)
        self.assertEqual(rev["reviewer_name"], "Alice Sharma")
        self.assertEqual(rev["star_rating"], 5)
        self.assertEqual(rev["status"], "pending")

        # Test updating
        db.update_review(review_id, status="posted", approved_reply="Thank you Alice!")
        updated = db.get_review_by_id(review_id)
        self.assertEqual(updated["status"], "posted")
        self.assertEqual(updated["approved_reply"], "Thank you Alice!")

    def test_worker_parse_time_robustness(self):
        """Ensure parse_time produces timezone-aware datetimes across diverse formats."""
        now = datetime.now(timezone.utc)

        # 1. ISO string ending in Z
        t1 = worker.parse_time("2026-09-29T12:00:00Z")
        self.assertIsNotNone(t1.tzinfo)
        diff1 = (now - t1).total_seconds()
        self.assertIsInstance(diff1, float)

        # 2. ISO string with offset
        t2 = worker.parse_time("2026-09-29T12:00:00+00:00")
        self.assertIsNotNone(t2.tzinfo)

        # 3. Naive ISO string (no timezone) - must be coerced to UTC
        t3 = worker.parse_time("2026-09-29T12:00:00")
        self.assertIsNotNone(t3.tzinfo)
        diff3 = (now - t3).total_seconds()
        self.assertIsInstance(diff3, float)

        # 4. Empty string fallback
        t4 = worker.parse_time("")
        self.assertIsNotNone(t4.tzinfo)

    def test_health_endpoint(self):
        """Verify the health check endpoint returns 200 for 24/7 monitors."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "crg-review-bot")
        self.assertIn("timestamp", data)

    def test_webhook_endpoints(self):
        """Test incoming review webhook and pending replies webhook."""
        # 1. Test missing review_id
        res = self.client.post(
            "/api/webhook/review-received",
            json={"reviewer_name": "Bob"}
        )
        self.assertEqual(res.status_code, 400)

        # 2. Test receiving a 2-star review (should hold for approval)
        import ai_client
        original_gen = ai_client.generate_reply
        ai_client.generate_reply = lambda name, stars, comment: f"Dear {name}, we sincerely apologize for your experience."

        try:
            review_payload = {
                "review_id": "test-webhook-rev-2",
                "reviewer_name": "Rohan",
                "star_rating": 2,
                "comment": "Food was delayed and cold.",
                "review_time": datetime.now(timezone.utc).isoformat()
            }
            res = self.client.post("/api/webhook/review-received", json=review_payload)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["action"], "hold_for_approval")
            self.assertEqual(data["review_id"], "test-webhook-rev-2")

            # Check DB state
            saved = db.get_review_by_id("test-webhook-rev-2")
            self.assertEqual(saved["status"], "ai_drafted")
            self.assertIn("sincerely apologize", saved["ai_draft"])

            # 3. Simulate manager approving the reply on dashboard
            db.update_review(
                "test-webhook-rev-2",
                approved_reply="Dear Rohan, we sincerely apologize. Please contact us directly."
            )

            # 4. Test pending-replies endpoint
            res_pending = self.client.get("/api/webhook/pending-replies")
            self.assertEqual(res_pending.status_code, 200)
            pending_data = res_pending.get_json()
            self.assertEqual(pending_data["count"], 1)
            self.assertEqual(pending_data["replies"][0]["review_id"], "test-webhook-rev-2")

            # 5. Test mark-posted endpoint
            res_mark = self.client.post("/api/webhook/mark-posted", json={"review_id": "test-webhook-rev-2"})
            self.assertEqual(res_mark.status_code, 200)
            saved_posted = db.get_review_by_id("test-webhook-rev-2")
            self.assertEqual(saved_posted["status"], "posted")

        finally:
            ai_client.generate_reply = original_gen

if __name__ == "__main__":
    unittest.main()
