# Cybersecurity Assessment Report: SNMP Health Monitor
**Date:** June 3, 2026
**Project:** SNMP Health Monitor

## 1. Executive Summary
This report details the cybersecurity posture of the SNMP Health Monitor project. The assessment covers the Django backend, the Raspberry Pi/Jetson SNMP collectors, and the database worker.

## 2. Timeline of Key Security, Performance & Architectural Events

| Event Phase | Description | Security / Architectural Impact | Commit Reference / Link |
| :--- | :--- | :--- | :--- |
| **Initial Phase** | Project initialized as a Flask application, later migrated to a Django server. | Established core framework structure. | N/A |
| **Refactoring** | Legacy codebase, migration scripts, and unused research files removed. | Reduced attack surface by cleaning up dead code. | `fa08ca2` |
| **Authentication** | Full login/logout authentication with session and audit logging added. | Enforced access control and enabled security auditing. | `10f0ca8` |
| **CSRF Fixes** | Disabled CSRF on Django Ninja API for JS fetch; added CSRF tokens to upload forms. | Mitigated Cross-Site Request Forgery (CSRF) vulnerabilities. | `dbcd22a`, `ea8ebce` |
| **Decoupling** | Collector daemon decoupled from direct database writes, introducing a Dockerized DB worker. | Decoupled subsystems, reducing direct database exposure vectors. | `506eb01` |
| **Current Phase** | Fallback UDP listener startup implemented and PySNMP versions pinned. | Improved daemon reliability and locked down dependency versions. | `e788483` |
| **Asset Security** | Replaced heavy CDN Chart.js dev package with local minified UMD `chart.umd.min.js` and stripped source map comments. | Removed source disclosures and avoided external library dependency tracking. | `2301a72` |
| **Reflow Mitigation** | Resolved startup forced reflows by deferring text formatting (`this.init()`) in the base UI. | Resolved Main-Thread locking and boosted UI response time during critical path. | `75daa6d` |
| **CSS Segregation** | Extracted history investigation styles into `history.css` load path. | Reduced base stylesheet overhead by ~30%, saving bandwidth. | `7e7f848` |
| **Contrast Correct** | Adjusted color scheme variables and status badges to satisfy WCAG AA contrast standards. | Complied with regulatory usability guidelines for impaired users. | `7e7f848` |
| **Layout Shift Fix** | Set `display: optional` on web fonts and established static size bounds on connection-status badges. | Eliminated visual layout shifts (CLS), improving usability and rendering stability. | `d23bfe7` |

## 3. Vulnerability Findings & Security Posture

### 3.1. Authentication and Authorization
* **Web Interface:** The web interface employs Django's session-based authentication. However, the WebSocket connections (`server_django/apps/realtime/routing.py`) do not appear to enforce authentication, potentially allowing unauthorized access to real-time metrics.
* **SNMP Agents:** The `snmpd.conf` files for both Raspberry Pi and Jetson use the default public community string (`rocommunity public default -V all`). This is a significant risk, allowing anyone on the network to read SNMP data.

### 3.2. Data Transmission and Exposure
* **UDP Listeners:** 
    * The Django backend listens for UDP packets on `0.0.0.0:6004`.
    * The DB worker listens on `0.0.0.0:6003` (default).
    * These listeners do not implement source authentication or encryption, making them susceptible to spoofing and injection of malicious metrics data.
* **Encryption:** The system currently relies on HTTP and unencrypted UDP/WebSocket traffic. There is no evidence of TLS/SSL enforcement for data in transit.

### 3.3. Configuration and Secrets Management
* **Django Secrets:** The `.env` file contains a hardcoded, weak `DJANGO_SECRET_KEY` (`your-secret-key-here`) and has `DEBUG=True` enabled, which can leak sensitive information in production.
* **Database Credentials:** The `db_config.py` defaults to a root user with an empty password. While environment variables can override these, the defaults are insecure.
* **SNMP Credentials:** `config_prompt.py` stores and processes the SNMP community string in plaintext.

### 3.4. Input Validation and SQL Injection
* **DB Worker:** The `worker.py` parses incoming UDP JSON payloads. While it checks for required keys, it lacks strict schema validation.
* **Database Writes:** `db_writer.py` utilizes parameterized queries (e.g., `%s`), which effectively mitigates SQL injection risks during metric insertion.

## 4. Recommendations
1. **Secure SNMP Configuration:** Change the default `public` community string to a strong, unique value. Restrict SNMP access to specific IP addresses.
2. **Implement Encryption:** Enable TLS/SSL for the Django web server and secure WebSocket (WSS) connections.
3. **Secure UDP Channels:** Implement a shared secret or HMAC-based authentication for the UDP communication between the collector, DB worker, and Django backend to prevent packet spoofing.
4. **Secret Management:** Generate a cryptographically secure `DJANGO_SECRET_KEY`, disable `DEBUG` mode in production, and enforce strong database passwords.
5. **WebSocket Authentication:** Enforce Django session authentication on WebSocket connections.
