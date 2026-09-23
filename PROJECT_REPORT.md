# Cloud Monitoring & Automation Dashboard

## Detailed Project Report

**Project type:** Real-time infrastructure monitoring and operations dashboard  
**Primary technologies:** Python, FastAPI, React, WebSockets, SQLite, Docker  
**Audience:** SRE, DevOps, platform engineering, infrastructure operations, and technical reviewers  
**Status:** Functional local and Dockerized implementation

---

## 1. Executive summary

The Cloud Monitoring & Automation Dashboard is a full-stack monitoring solution that brings system telemetry, operational alerts, log validation, troubleshooting data, authentication, and role-based access into one real-time interface.

The backend continuously collects CPU, memory, disk, and uptime data for a small server fleet. It evaluates threshold rules, records alerts, simulates remediation actions for critical events, validates incoming log records, and broadcasts the current operational snapshot to connected React clients through a WebSocket channel.

The frontend provides a live dashboard that updates without manual refresh. Users must authenticate before accessing monitoring data. The application supports administrator, operator, and viewer roles, with protected API routes and an authenticated WebSocket connection.

The complete system can run locally or as a two-container Docker Compose deployment.

## 2. Project objectives

The project was designed to demonstrate the following capabilities:

1. Monitor system health metrics across a server fleet.
2. Expose monitoring data through REST APIs.
3. Stream live operational updates through WebSockets.
4. Detect threshold breaches and classify alert severity.
5. Simulate automated remediation for critical alerts.
6. Validate logs using structural and semantic rules.
7. Provide operational summaries for troubleshooting and reporting.
8. Protect monitoring data with authentication and authorization.
9. Package and validate the application using Docker.
10. Provide repeatable testing through unit tests and CI configuration.

## 3. Functional scope

### 3.1 Fleet monitoring

The monitoring engine tracks:

- CPU utilization
- memory utilization
- disk utilization
- uptime
- server identity and role

The default fleet contains:

- `host-local`: the real machine running the backend
- `web-node-1`: simulated web frontend node
- `worker-node-1`: simulated batch worker node

The local host is measured with `psutil`. Simulated nodes use a bounded random-walk model so that the dashboard behaves like a multi-node environment without requiring a cloud account.

### 3.2 Alerting and remediation

The alert engine evaluates the latest metric sample for each server.

| Metric | Warning threshold | Critical threshold |
| --- | ---: | ---: |
| CPU | 75% | 90% |
| Memory | 80% | 92% |
| Disk | 85% | 95% |

Critical alerts record a simulated remediation action:

| Metric | Remediation action |
| --- | --- |
| CPU | `restart_high_cpu_process` |
| Memory | `clear_cache_and_restart_service` |
| Disk | `rotate_and_compress_old_logs` |

The remediation is intentionally simulated. In a production deployment, these actions would call a controlled runbook, cloud automation service, or infrastructure management system.

### 3.3 Log validation

The log pipeline validates every generated log entry.

Validation rules include:

- the level must be recognized
- the message must not be empty
- the message must not appear truncated
- `ERROR` and `CRITICAL` messages must contain a traceable identifier such as a request ID, exception name, or service name

The reporting endpoint returns:

- total logs processed
- invalid or low-signal logs
- valid-log percentage

### 3.4 Authentication and role-based access

The API uses signed bearer tokens with an expiration time.

| Role | Permissions |
| --- | --- |
| `admin` | Read monitoring data, run all approved operations, and read the operation audit |
| `operator` | Read monitoring data and clear the cache |
| `viewer` | Read-only monitoring access with no operational controls |

Protected resources require an `Authorization: Bearer <token>` header. The live WebSocket requires the token as a query parameter:

```text
ws://localhost:8123/ws/live?token=<jwt>
```

The React frontend:

- displays a login form
- stores the active session in browser session storage
- adds the token to REST requests
- adds the token to the WebSocket connection
- displays the active username and role
- supports sign out
- automatically reconnects the live channel

The local demonstration accounts are:

| Username | Password | Role |
| --- | --- | --- |
| `admin` | `admin123` | admin |
| `operator` | `operator123` | operator |
| `viewer` | `viewer123` | viewer |

These credentials must be replaced before any non-development deployment.

## 4. Technical architecture

```text
                         +-----------------------------+
                         | React + Vite frontend       |
                         | Login, dashboard, Chart.js  |
                         +--------------+--------------+
                                        |
                         REST + authenticated WebSocket
                                        |
                         +--------------v--------------+
                         | FastAPI backend              |
                         | Auth, API routes, tick loop  |
                         +------+-----------+-----------+
                                |           |
                      +---------v--+   +----v-------------+
                      | Monitoring |   | Alert engine     |
                      | psutil +   |   | thresholds +     |
                      | simulation |   | remediation log  |
                      +---------+--+   +----+-------------+
                                |           |
                                +-----+-----+
                                      v
                         +-----------------------------+
                         | Log validation pipeline      |
                         +--------------+--------------+
                                        |
                         +--------------v--------------+
                         | SQLite database              |
                         | servers, metrics, logs,      |
                         | alerts                       |
                         +-----------------------------+
```

### Real-time processing cycle

The asynchronous backend loop runs every three seconds:

1. Collect current metrics.
2. Evaluate alert thresholds.
3. Record warning or critical alerts.
4. Record simulated remediation for critical alerts.
5. Generate and validate a batch of log entries.
6. Build a consistent dashboard snapshot.
7. Broadcast the snapshot to authenticated WebSocket clients.

This design means the browser receives updates from the backend rather than repeatedly polling every endpoint.

## 5. API contract

### Authentication endpoints

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | Public | Authenticate a user and issue a token |
| `GET` | `/api/auth/me` | Authenticated | Return the active user and role |
| `GET` | `/api/admin/users` | Admin | Return configured role identities |
| `POST` | `/api/operations/clear_cache` | Operator/Admin | Clear the cache |
| `POST` | `/api/operations/restart_service` | Admin | Request a service restart |
| `POST` | `/api/operations/rotate_logs` | Admin | Request log rotation |
| `GET` | `/api/operations/audit` | Admin | Review operational actions |

### Monitoring endpoints

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Public | Service health and connection count |
| `GET` | `/api/servers` | Authenticated | List monitored servers |
| `GET` | `/api/metrics/latest` | Authenticated | Get current metrics |
| `GET` | `/api/metrics/history/{server_id}` | Authenticated | Get historical metrics |
| `GET` | `/api/alerts` | Authenticated | List alerts |
| `GET` | `/api/logs` | Authenticated | List recent logs |
| `GET` | `/api/logs/summary` | Authenticated | Get validation statistics |
| `WebSocket` | `/ws/live?token=<jwt>` | Authenticated | Receive real-time snapshots |

### Snapshot payload

The WebSocket sends a payload with this shape:

```json
{
  "type": "snapshot",
  "servers": [],
  "alerts": [],
  "logs": [],
  "log_summary": {
    "total_logs": 0,
    "flagged_invalid": 0,
    "valid_rate_percent": 100.0
  }
}
```

## 6. Persistence model

SQLite is used for local persistence.

### `servers`

Stores the monitored fleet:

- `id`
- `name`
- `role`
- `is_real`

### `metrics`

Stores time-series health samples:

- `id`
- `server_id`
- `timestamp`
- `cpu_percent`
- `memory_percent`
- `disk_percent`
- `uptime_seconds`

### `logs`

Stores raw logs and validation results:

- `id`
- `server_id`
- `timestamp`
- `level`
- `message`
- `is_valid`
- `validation_note`

### `alerts`

Stores threshold events and remediation outcomes:

- `id`
- `server_id`
- `timestamp`
- `metric`
- `value`
- `threshold`
- `severity`
- `status`
- `remediation_action`
- `remediation_result`

### `operation_audit`

Stores an audit record for every approved operational request:

- `id`
- `timestamp`
- `username`
- `role`
- `action`
- `target`
- `result`

## 7. Deployment model

The Docker deployment contains two services:

### Backend container

- Base image: `python:3.13-slim`
- Runs FastAPI with Uvicorn
- Exposes port `8123`
- Stores the SQLite database inside the container filesystem for the demonstration setup

### Frontend container

- Build image: `node:20-alpine`
- Runtime image: `nginx:alpine`
- Builds the React application with Vite
- Serves the static frontend on port `80`

### Compose startup

```powershell
cd C:\Users\lenovo\Downloads\cloud-monitoring-dashboard\cloud-monitoring-dashboard
docker compose up --build -d
```

Application URLs:

```text
Frontend: http://localhost/
Backend:  http://localhost:8123
Health:   http://localhost:8123/api/health
```

Stop the stack:

```powershell
docker compose down
```

## 8. Configuration

Use environment variables for deployment configuration:

```text
JWT_SECRET
TOKEN_TTL_SECONDS
ADMIN_PASSWORD
OPERATOR_PASSWORD
VIEWER_PASSWORD
VITE_API_URL
VITE_WS_URL
```

The file [.env.example](../.env.example) provides the configuration template.

For production:

- use a long randomly generated JWT secret
- replace all demo passwords
- avoid committing `.env`
- use HTTPS and `wss://`
- place the application behind a reverse proxy
- use a managed database instead of container-local SQLite

## 9. Verification and test results

### Automated backend tests

The backend test suite covers:

- health endpoint availability
- unauthenticated access rejection
- successful viewer login
- viewer access to monitoring data
- viewer rejection from admin resources
- admin access to admin resources
- valid log validation
- invalid error-log detection
- truncated-log detection
- supported log levels

Verified result:

```text
8 tests passed
```

### Frontend build verification

The production frontend build was verified with:

```powershell
cd frontend
npm run build
```

The Vite production bundle completed successfully.

### Docker verification

The Docker Compose stack was rebuilt and started successfully. Verification covered:

- Docker Compose configuration parsing
- backend image build
- frontend image build
- backend container startup
- frontend container startup
- frontend HTTP response `200`
- viewer login and JWT issuance
- protected metrics response `200`
- viewer admin authorization response `403`
- authenticated operator WebSocket snapshot

The authenticated WebSocket returned a snapshot containing three monitored servers.

## 10. Operational runbook

### Start

```powershell
docker compose up --build -d
```

### Check status

```powershell
docker compose ps
```

### View logs

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

### Check health

```powershell
Invoke-RestMethod http://localhost:8123/api/health
```

### Stop

```powershell
docker compose down
```

### Reset local generated data

Stop the containers first, then remove the generated `monitoring.db` file if a clean local database is required.

## 11. Known limitations

This implementation is intentionally portfolio- and demonstration-oriented:

- user accounts are configured through environment variables rather than stored in a user database
- JWT signing is implemented directly for minimal dependencies; a production system should use a mature identity provider or a well-maintained JWT library
- remediation actions are simulated
- two fleet nodes use generated metrics
- SQLite is not intended for high-volume multi-instance production workloads
- the frontend and backend use separate local origins in development
- no alert notification provider is configured

## 12. Recommended production roadmap

1. Replace demo authentication with an OIDC provider such as Entra ID, Auth0, Okta, or Keycloak.
2. Store users, roles, and audit events in a managed database.
3. Move SQLite data to PostgreSQL or a cloud-native time-series store.
4. Add rate limiting, refresh tokens, audit logging, and token revocation.
5. Integrate real AWS CloudWatch or Azure Monitor data sources.
6. Connect remediation actions to approved runbooks with least-privilege credentials.
7. Add alert notification channels such as email, Teams, Slack, or PagerDuty.
8. Add dashboards for memory, disk, uptime, and historical trends.
9. Add container health checks and deployment probes.
10. Add dependency scanning and image vulnerability scanning to CI.

## 13. Portfolio and resume alignment

The implementation supports the following experience summary:

> Built a real-time cloud monitoring dashboard using Python, FastAPI, React, REST APIs, WebSockets, SQLite, and Docker. Tracked system health metrics, operational alerts, log validation results, troubleshooting information, and simulated remediation actions. Added JWT authentication and role-based access for administrators, operators, and viewers. Automated log validation and reporting workflows to improve issue detection efficiency and delivered a containerized, tested deployment workflow.

## 14. File reference

- [Backend API](../backend/main.py)
- [Authentication module](../backend/auth.py)
- [Monitoring engine](../backend/monitor.py)
- [Alert engine](../backend/alerts.py)
- [Log validation](../backend/log_validation.py)
- [Database layer](../backend/database.py)
- [React dashboard](../frontend/src/App.jsx)
- [Dashboard styles](../frontend/src/index.css)
- [Docker Compose](../docker-compose.yml)
- [CI workflow](../.github/workflows/ci.yml)
