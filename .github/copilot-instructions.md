# SNMPHealthMonitor AI Coding Instructions

## Project Overview
This is a networked system monitoring solution comprising two distinct components:
1.  **`rasberrypi` (Collector):** An SNMP agent/collector that polls devices, writes data to MySQL, and broadcasts real-time updates via UDP.
2.  **`server_django` (Backend):** A Django-based application serving a dashboard, REST API (Django Ninja), and real-time WebSockets (Django Channels).

## Architecture & Data Flow
The "Dual-Path" data flow is critical for performance:
*   **Path 1 (History):** Collector writes metrics to MySQL. Backend reads via Raw SQL (for aggregations) and Django ORM (for metadata).
*   **Path 2 (Real-time):** Collector sends UDP packets to Backend (Port 6003). Backend's UDP Listener (in background thread) transforms data and pushes to Frontend via WebSockets.

## Component: `server_django` (The Backend)
*   **Server Stack:** Django + Daphne (ASGI) + WhiteNoise (Static).
*   **Directories:**
    *   `apps/metrics`: API endpoints (Ninja) and Data Services (Raw SQL).
    *   `apps/realtime`: UDP Listener and WebSocket Consumers.
    *   `apps/web`: Standard Django Views for HTML rendering.
*   **Real-time Architecture:**
    *   **UDP Listener:** A `threading.Thread` started in `apps/realtime/apps.py` `ready()` hook. This bypasses ASGI lifespan issues on Windows/Daphne.
    *   **WebSockets:** Standard `AsyncJsonWebsocketConsumer` in `apps/realtime/consumers.py`.
    *   **Flow:** UDP Packet -> `UdpListener` -> `RealTimeTransformer` -> `ChannelLayer.group_send()` -> `Consumer` -> WebSocket Client.

## Component: `rasberrypi` (The Collector)
*   **Entry Point:** `python -m manager` (Run from `rasberrypi` directory).
*   **Config:** `config/config.json` determines polled devices and OIDs.
*   **Database:** Direct SQL writer in `db_service/db_writer.py`.

## Critical Patterns & Conventions
1.  **Database Access:**
    *   **Metadata:** Use Django ORM (`Device.objects...`).
    *   **Metrics (Time-Series):** Use Raw SQL via `connection.cursor()` in `apps/metrics/services.py`. Do NOT use ORM for high-volume metric ingestion/retrieval.
    *   **Date Handling:** Backend returns **ISO 8601 strings** (`.isoformat()`). Frontend uses `new Date(iso_string)`. DO NOT pass python `datetime` objects directly to views/API responses.
2.  **Frontend (Vanilla JS):**
    *   Located in `server_django/static/js/`.
    *   Uses ES6 Modules (`import/export`).
    *   **Dashboard Logic:** `dashboard.js` orchestrates `websocket-manager.js` (live data) and `data-processor.js`.
    *   **History Page:** Uses HTTP API (`/api/history/...`) strictly. Real-time status updates via WebSocket are optional but must use `systemstatus` topic if enabled.
3.  **Static Files:**
    *   Always run `python manage.py collectstatic --noinput` after modifying `server_django/static/`. Daphne serves files from `server_django/staticfiles`.

## Workflows & Debugging
*   **Running Server:**
    ```powershell
    # Must use Daphne for WebSockets/ASGI
    daphne -p 8000 config.asgi:application
    ```
*   **Running Collector:**
    ```powershell
    cd rasberrypi
    python -m manager
    ```
*   **Debugging Real-time:**
    *   Check `apps/realtime/apps.py` to ensure `start_udp_listener_thread` is called.
    *   Use browser DevTools -> Network -> WS to verify WebSocket connection.
    *   Verify `UDP_LISTEN_PORT` in `.env` matches the collector's target port.

## API Design (Django Ninja)
*   Routes defined in `apps/metrics/api.py`.
*   Uses `pydantic` schemas in `apps/metrics/schemas.py`.
*   Responses must be strictly typed (e.g., `HistoryMetricsResponse`).
