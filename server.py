"""Verita course-project backend.

This zero-dependency service exposes a small REST API, persists onboarding data
in SQLite and serves the browser application. Enterprise integrations are kept
behind adapters so the demo can later be connected to Okta and Patronum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "data" / "verita.db"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Assessment:
    score: int
    risk: str
    recommendation: str
    reasons: list[str]
    model_version: str = "patronum-demo-1.0"


class PatronumAdapter:
    """Explainable local substitute for the external Patronum AI service."""

    def assess(self, customer: dict) -> Assessment:
        name = customer["fullName"].strip()
        address = customer["address"].strip()
        customer_type = customer["customerType"]
        reasons: list[str] = []
        score = 96

        if customer_type == "Small business":
            score -= 28
            reasons.append("Business registration requires authorized representative validation")
        if len(address) < 12:
            score -= 18
            reasons.append("Service address is too short for high-confidence validation")
        if any(keyword in name.lower() for keyword in ("review", "duplicate", "risk")):
            score -= 33
            reasons.append("Possible duplicate identity record detected")

        if score < 75:
            reasons.extend(["No sanctions match detected", "Manual validation required before activation"])
            return Assessment(score=max(score, 12), risk="High" if score < 55 else "Medium", recommendation="Review", reasons=reasons)

        return Assessment(
            score=score,
            risk="Low",
            recommendation="Approved",
            reasons=[
                "Document authenticity checks passed",
                "No sanctions or duplicate identity match",
                "Identity fields extracted with high confidence",
            ],
        )


class CerberusAdapter:
    """Local SAML-style identity substitute for the course demo."""

    def __init__(self) -> None:
        self._tokens: dict[str, dict] = {}
        self._lock = threading.Lock()

    def login(self) -> dict:
        token = secrets.token_urlsafe(32)
        user = {
            "id": "cerberus-amartin",
            "name": "Amelia Martin",
            "role": "Compliance lead",
            "permissions": ["cases:read", "cases:write", "reviews:decide", "governance:read"],
        }
        with self._lock:
            self._tokens[token] = user
        return {"token": token, "user": user, "provider": "Cerberus SAML 2.0 demo adapter"}

    def user_for_token(self, token: str) -> dict | None:
        with self._lock:
            return self._tokens.get(token)


class VeritaService:
    def __init__(self, db_path: Path, *, reset: bool = False) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cerberus = CerberusAdapter()
        self.patronum = PatronumAdapter()
        self._initialize(reset=reset)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self, *, reset: bool) -> None:
        with closing(self.connect()) as db, db:
            if reset:
                db.executescript(
                    """
                    DROP TABLE IF EXISTS audit_log;
                    DROP TABLE IF EXISTS ai_assessments;
                    DROP TABLE IF EXISTS documents;
                    DROP TABLE IF EXISTS cases;
                    """
                )
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    market TEXT NOT NULL CHECK (market IN ('FR', 'AU')),
                    customer_type TEXT NOT NULL,
                    address TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES cases(id),
                    filename TEXT NOT NULL,
                    encrypted INTEGER NOT NULL,
                    malware_scan TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES cases(id),
                    model_version TEXT NOT NULL,
                    confidence_score INTEGER NOT NULL,
                    risk TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL UNIQUE
                );
                """
            )
            count = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        if count == 0:
            self._seed()

    def _seed(self) -> None:
        seeds = [
            ("FR-2026-04291", "Sophie Moreau", "sophie.moreau@example.fr", "FR", "Individual", "14 rue de Charonne, Paris", "Review", "High", 42, ["Proof of address differs from declared service address", "Identity document image contains a low-confidence region", "Manual validation required before activation"]),
            ("AU-2026-01872", "Daniel Walsh", "daniel.walsh@example.au", "AU", "Small business", "86 George Street, Sydney", "Review", "Medium", 68, ["Business registration requires authorized representative validation", "No sanctions match detected", "Manual validation required by AU business rule"]),
            ("FR-2026-04288", "Marc Dubois", "marc.dubois@example.fr", "FR", "Individual", "9 avenue Jean Jaures, Lyon", "Review", "High", 51, ["Possible duplicate identity record detected", "Existing record has a different email address", "Confirm merge or reject the new intake"]),
            ("FR-2026-04287", "Claire Bernard", "claire.bernard@example.fr", "FR", "Individual", "4 rue des Lilas, Lille", "Approved", "Low", 97, []),
            ("AU-2026-01869", "Olivia Chen", "olivia.chen@example.au", "AU", "Individual", "12 Collins Street, Melbourne", "Processing", "Low", 92, []),
            ("FR-2026-04274", "Antoine Petit", "antoine.petit@example.fr", "FR", "Small business", "18 quai de la Loire, Nantes", "Approved", "Low", 95, []),
            ("AU-2026-01858", "Jack Taylor", "jack.taylor@example.au", "AU", "Individual", "31 Queen Street, Brisbane", "Approved", "Low", 98, []),
        ]
        timestamp = now_iso()
        with closing(self.connect()) as db, db:
            for index, seed in enumerate(seeds):
                case_id, name, email, market, customer_type, address, status, risk, score, reasons = seed
                created_at = timestamp
                db.execute(
                    "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (case_id, name, email, market, customer_type, address, status, risk, score, created_at, created_at),
                )
                db.execute(
                    "INSERT INTO ai_assessments (case_id, model_version, confidence_score, risk, recommendation, reasons_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (case_id, "patronum-demo-1.0", score, risk, status, json_text(reasons), created_at),
                )
                db.execute(
                    "INSERT INTO documents (case_id, filename, encrypted, malware_scan, created_at) VALUES (?, ?, 1, 'passed', ?)",
                    (case_id, "identity_document.pdf", created_at),
                )
        self.audit("system", "DEMO_DATA_SEEDED", "verita", {"cases": len(seeds)})

    def audit(self, actor: str, action: str, entity_id: str, details: dict) -> dict:
        created_at = now_iso()
        details_json = json_text(details)
        with closing(self.connect()) as db, db:
            last = db.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            previous_hash = last["entry_hash"] if last else "GENESIS"
            payload = "|".join((created_at, actor, action, entity_id, details_json, previous_hash))
            entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            cursor = db.execute(
                "INSERT INTO audit_log (created_at, actor, action, entity_id, details_json, previous_hash, entry_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (created_at, actor, action, entity_id, details_json, previous_hash, entry_hash),
            )
            return {"id": cursor.lastrowid, "createdAt": created_at, "entryHash": entry_hash}

    def login(self) -> dict:
        session = self.cerberus.login()
        self.audit(session["user"]["name"], "AUTH_LOGIN", session["user"]["id"], {"provider": session["provider"]})
        return session

    def list_cases(self, query: str = "", status: str = "") -> list[dict]:
        clauses, values = [], []
        if query:
            clauses.append("(LOWER(full_name) LIKE ? OR LOWER(id) LIKE ? OR LOWER(market) LIKE ? OR LOWER(customer_type) LIKE ?)")
            like = f"%{query.lower()}%"
            values.extend([like, like, like, like])
        if status:
            clauses.append("status = ?")
            values.append(status)
        sql = "SELECT * FROM cases" + (f" WHERE {' AND '.join(clauses)}" if clauses else "") + " ORDER BY created_at DESC, id DESC"
        with closing(self.connect()) as db, db:
            rows = db.execute(sql, values).fetchall()
        return [self._case_payload(row) for row in rows]

    def get_case(self, case_id: str) -> dict | None:
        with closing(self.connect()) as db, db:
            row = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
            if not row:
                return None
            reasons_row = db.execute("SELECT reasons_json FROM ai_assessments WHERE case_id = ? ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
            documents = [dict(item) for item in db.execute("SELECT filename, encrypted, malware_scan AS malwareScan, created_at AS createdAt FROM documents WHERE case_id = ?", (case_id,)).fetchall()]
        payload = self._case_payload(row)
        payload["reason"] = json.loads(reasons_row["reasons_json"]) if reasons_row else []
        payload["documents"] = documents
        return payload

    def _case_payload(self, row: sqlite3.Row) -> dict:
        name = row["full_name"]
        return {
            "id": row["id"],
            "name": name,
            "email": row["email"],
            "initials": "".join(part[0].upper() for part in name.split()[:2]),
            "market": row["market"],
            "type": row["customer_type"],
            "address": row["address"],
            "status": row["status"],
            "risk": row["risk"],
            "score": row["score"],
            "created": self._relative_time(row["created_at"]),
            "createdAt": row["created_at"],
        }

    @staticmethod
    def _relative_time(timestamp: str) -> str:
        age = datetime.now(UTC) - datetime.fromisoformat(timestamp)
        minutes = max(0, int(age.total_seconds() // 60))
        if minutes < 1:
            return "just now"
        if minutes < 60:
            return f"{minutes} min ago"
        return f"{minutes // 60} h ago"

    def create_case(self, customer: dict, actor: str) -> dict:
        required = ("fullName", "email", "country", "customerType", "address")
        missing = [key for key in required if not str(customer.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        if customer["country"] not in ("FR", "AU"):
            raise ValueError("Country must be FR or AU")

        assessment = self.patronum.assess(customer)
        timestamp = now_iso()
        prefix = customer["country"]
        with closing(self.connect()) as db, db:
            count = db.execute("SELECT COUNT(*) FROM cases WHERE market = ?", (prefix,)).fetchone()[0]
            case_id = f"{prefix}-2026-{50000 + count + 1:05d}"
            db.execute(
                "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, customer["fullName"].strip(), customer["email"].strip(), prefix, customer["customerType"], customer["address"].strip(), assessment.recommendation, assessment.risk, assessment.score, timestamp, timestamp),
            )
            db.execute(
                "INSERT INTO documents (case_id, filename, encrypted, malware_scan, created_at) VALUES (?, 'identity_document.pdf', 1, 'passed', ?)",
                (case_id, timestamp),
            )
            db.execute(
                "INSERT INTO ai_assessments (case_id, model_version, confidence_score, risk, recommendation, reasons_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (case_id, assessment.model_version, assessment.score, assessment.risk, assessment.recommendation, json_text(assessment.reasons), timestamp),
            )
        self.audit(actor, "CASE_CREATED", case_id, {"market": prefix, "status": assessment.recommendation})
        self.audit("Patronum", "AI_ASSESSMENT_COMPLETED", case_id, asdict(assessment))
        return self.get_case(case_id)

    def decide_case(self, case_id: str, decision: str, actor: str, comment: str = "") -> dict:
        status_by_decision = {"approve": "Approved", "escalate": "Processing"}
        if decision not in status_by_decision:
            raise ValueError("Decision must be approve or escalate")
        with closing(self.connect()) as db, db:
            row = db.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone()
            if not row:
                raise LookupError("Case not found")
            db.execute("UPDATE cases SET status = ?, updated_at = ? WHERE id = ?", (status_by_decision[decision], now_iso(), case_id))
        self.audit(actor, f"CASE_{decision.upper()}D", case_id, {"comment": comment, "humanInTheLoop": True})
        return self.get_case(case_id)

    def dashboard(self) -> dict:
        with closing(self.connect()) as db, db:
            counts = {row["status"]: row["amount"] for row in db.execute("SELECT status, COUNT(*) amount FROM cases GROUP BY status")}
            markets = {row["market"]: row["amount"] for row in db.execute("SELECT market, COUNT(*) amount FROM cases GROUP BY market")}
            total = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        return {
            "activeCases": 1248 + total,
            "straightThroughRate": 71.8,
            "medianActivationTime": "14m 32s",
            "dataQualityScore": 98.7,
            "reviewCount": counts.get("Review", 0),
            "markets": markets,
            "throughput": [815, 972, 910, 1129, 1044, 661, 572],
        }

    def governance(self) -> dict:
        return {
            "domains": [
                {"name": "Customer domain", "owner": "Chief Customer Officer", "quality": 99.2},
                {"name": "Compliance domain", "owner": "Compliance Director", "quality": 98.4},
                {"name": "Contract domain", "owner": "Retail Operations Lead", "quality": 98.6},
            ],
            "controls": ["Encryption at rest and in transit", "Least-privilege Cerberus roles", "Hash-chained audit evidence", "Explainable Patronum assessments", "FR and AU retention policies"],
        }

    def audit_entries(self, limit: int = 12) -> list[dict]:
        with closing(self.connect()) as db, db:
            rows = db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [
            {
                "id": row["id"],
                "createdAt": row["created_at"],
                "actor": row["actor"],
                "action": row["action"],
                "entityId": row["entity_id"],
                "details": json.loads(row["details_json"]),
                "entryHash": row["entry_hash"],
            }
            for row in rows
        ]

    def verify_audit_chain(self) -> dict:
        with closing(self.connect()) as db, db:
            rows = db.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        previous_hash = "GENESIS"
        for row in rows:
            payload = "|".join((row["created_at"], row["actor"], row["action"], row["entity_id"], row["details_json"], previous_hash))
            expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if row["previous_hash"] != previous_hash or row["entry_hash"] != expected:
                return {"valid": False, "entries": len(rows), "failedAt": row["id"]}
            previous_hash = row["entry_hash"]
        return {"valid": True, "entries": len(rows)}


class VeritaHandler(BaseHTTPRequestHandler):
    server_version = "Verita/1.0"

    @property
    def service(self) -> VeritaService:
        return self.server.service  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        print(f"[verita] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            return self.send_json({"status": "ok", "service": "Verita API", "time": now_iso()})
        if parsed.path.startswith("/api/"):
            user = self.require_user()
            if not user:
                return
            query = parse_qs(parsed.query)
            if parsed.path == "/api/dashboard":
                return self.send_json(self.service.dashboard())
            if parsed.path == "/api/cases":
                return self.send_json(self.service.list_cases(query.get("q", [""])[0], query.get("status", [""])[0]))
            if parsed.path.startswith("/api/cases/"):
                case = self.service.get_case(parsed.path.removeprefix("/api/cases/"))
                return self.send_json(case) if case else self.send_error_json(HTTPStatus.NOT_FOUND, "Case not found")
            if parsed.path == "/api/governance":
                return self.send_json(self.service.governance())
            if parsed.path == "/api/audit":
                return self.send_json({"chain": self.service.verify_audit_chain(), "entries": self.service.audit_entries(int(query.get("limit", ["12"])[0]))})
            return self.send_error_json(HTTPStatus.NOT_FOUND, "API endpoint not found")
        self.send_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/login":
            return self.send_json(self.service.login())
        user = self.require_user()
        if not user:
            return
        try:
            body = self.read_json()
            if parsed.path == "/api/cases":
                return self.send_json(self.service.create_case(body, user["name"]), status=HTTPStatus.CREATED)
            if parsed.path.startswith("/api/cases/") and parsed.path.endswith("/decision"):
                case_id = parsed.path.removeprefix("/api/cases/").removesuffix("/decision")
                return self.send_json(self.service.decide_case(case_id, body.get("decision", ""), user["name"], body.get("comment", "")))
            self.send_error_json(HTTPStatus.NOT_FOUND, "API endpoint not found")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
        except LookupError as error:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(error))

    def read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 1024 * 1024:
            raise ValueError("Request payload is too large")
        try:
            return json.loads(self.rfile.read(content_length) or b"{}")
        except json.JSONDecodeError as error:
            raise ValueError("Request body must be valid JSON") from error

    def require_user(self) -> dict | None:
        authorization = self.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        user = self.service.cerberus.user_for_token(token)
        if not user:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Cerberus authentication required")
        return user

    def send_json(self, payload: object, *, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def send_static(self, url_path: str) -> None:
        requested = "index.html" if url_path in ("", "/") else url_path.lstrip("/")
        target = (APP_DIR / requested).resolve()
        if APP_DIR not in target.parents and target != APP_DIR:
            return self.send_error_json(HTTPStatus.FORBIDDEN, "Static path rejected")
        if not target.exists() or not target.is_file():
            return self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


class VeritaHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], service: VeritaService) -> None:
        self.service = service
        super().__init__(address, VeritaHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Verita course-project server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="Reset and reseed demo data")
    args = parser.parse_args()

    service = VeritaService(args.db, reset=args.reset)
    server = VeritaHTTPServer((args.host, args.port), service)
    print(f"Verita is running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Verita")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
