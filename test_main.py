import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import main


class MainAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.init_db()

    def test_health_endpoint(self):
        client = TestClient(main.app)
        response = client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['status'], 'ok')
        self.assertIn('connected_clients', body)

    def test_protected_endpoint_requires_authentication(self):
        client = TestClient(main.app)
        response = client.get('/api/metrics/latest')
        self.assertEqual(response.status_code, 401)

    def test_viewer_can_read_metrics_but_cannot_access_admin_users(self):
        client = TestClient(main.app)
        login = client.post('/api/auth/login', json={'username': 'viewer', 'password': 'viewer123'})
        self.assertEqual(login.status_code, 200)
        token = login.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        self.assertEqual(client.get('/api/metrics/latest', headers=headers).status_code, 200)
        self.assertEqual(client.get('/api/admin/users', headers=headers).status_code, 403)

    def test_admin_can_access_admin_users(self):
        client = TestClient(main.app)
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
        token = login.json()['access_token']
        response = client.get('/api/admin/users', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(response.status_code, 200)
    def test_viewer_cannot_run_operations(self):
        client = TestClient(main.app)
        login = client.post('/api/auth/login', json={'username': 'viewer', 'password': 'viewer123'})
        headers = {'Authorization': f'Bearer {login.json()["access_token"]}'}
        response = client.post('/api/operations/clear_cache', headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_operator_can_clear_cache_but_not_restart_service(self):
        client = TestClient(main.app)
        login = client.post('/api/auth/login', json={'username': 'operator', 'password': 'operator123'})
        headers = {'Authorization': f'Bearer {login.json()["access_token"]}'}
        self.assertEqual(client.post('/api/operations/clear_cache', headers=headers).status_code, 200)
        self.assertEqual(client.post('/api/operations/restart_service', headers=headers).status_code, 403)

    def test_admin_can_run_all_operations_and_read_audit(self):
        client = TestClient(main.app)
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
        headers = {'Authorization': f'Bearer {login.json()["access_token"]}'}
        self.assertEqual(client.post('/api/operations/clear_cache', headers=headers).status_code, 200)
        self.assertEqual(client.post('/api/operations/restart_service', headers=headers).status_code, 200)
        self.assertEqual(client.post('/api/operations/rotate_logs', headers=headers).status_code, 200)
        self.assertEqual(client.get('/api/operations/audit', headers=headers).status_code, 200)


if __name__ == '__main__':
    unittest.main()
