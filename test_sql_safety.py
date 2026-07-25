import sqlite3
import tempfile
import unittest

from sql_agent import SQLAgent


class SQLSafetyTests(unittest.TestCase):
    def setUp(self):
        self.database = tempfile.NamedTemporaryFile(suffix=".db")
        connection = sqlite3.connect(self.database.name)
        connection.execute("CREATE TABLE orders (order_id INTEGER)")
        connection.execute("CREATE TABLE batch_control (batch_id TEXT, source_count INT, accepted_count INT, quarantine_count INT, stage TEXT, finished_at TEXT)")
        connection.execute(
            "INSERT INTO batch_control VALUES ('b1', 13, 9, 3, 'bronze_to_silver', '2026-07-20')"
        )
        connection.execute("INSERT INTO orders VALUES (1)")
        connection.commit()
        connection.close()
        self.agent = SQLAgent(self.database.name, llm_client=None)

    def tearDown(self):
        self.agent.close()
        self.database.close()

    def test_allows_single_read_query(self):
        result, error = self.agent.execute_sql("SELECT order_id FROM orders")
        self.assertIsNone(error)
        self.assertEqual(result.row_count, 1)

    def test_rejects_write_and_multiple_statements(self):
        for sql in ("DELETE FROM orders", "SELECT * FROM orders; DROP TABLE orders"):
            result, error = self.agent.execute_sql(sql)
            self.assertIsNone(result)
            self.assertIn("read-only", error)

    def test_sanitizes_noisy_model_output(self):
        noisy = '''Here you go:\n```sql\nSELECT batch_id, accepted_count + quarantine_count AS accounted_rows\nFROM batch_control\nWHERE stage = \'bronze_to_silver\';\nLIMIT 1;\n```\nCREATE TABLE evil(x INT);'''
        cleaned = SQLAgent.sanitize_sql(noisy)
        self.assertTrue(cleaned.upper().startswith("SELECT"))
        self.assertNotIn("CREATE", cleaned.upper())
        result, error = self.agent.execute_sql(noisy)
        self.assertIsNone(error)
        self.assertEqual(result.row_count, 1)

    def test_quoted_json_fragment_is_recoverable(self):
        noisy = '"sql_query": "SELECT order_id FROM orders", "explanation": "x"'
        cleaned = SQLAgent.sanitize_sql(noisy)
        self.assertEqual(cleaned.upper(), "SELECT ORDER_ID FROM ORDERS")
        self.assertTrue(SQLAgent.is_read_only_sql(noisy))


if __name__ == "__main__":
    unittest.main()
