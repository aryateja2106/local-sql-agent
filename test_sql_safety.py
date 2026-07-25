import sqlite3
import tempfile
import unittest

from sql_agent import SQLAgent


class SQLSafetyTests(unittest.TestCase):
    def setUp(self):
        self.database = tempfile.NamedTemporaryFile(suffix=".db")
        connection = sqlite3.connect(self.database.name)
        connection.execute("CREATE TABLE orders (order_id INTEGER)")
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


if __name__ == "__main__":
    unittest.main()
