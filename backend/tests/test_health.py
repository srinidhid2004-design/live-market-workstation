import unittest

import httpx

from app.main import app


class HealthTest(unittest.IsolatedAsyncioTestCase):
    async def test_health_returns_exact_json(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertEqual(response.content, b'{"status":"healthy"}')
