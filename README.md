# Verita MVP

Verita is a working course-project implementation of the Beauxbatons customer onboarding and KYC platform. It supports France and Australia, automated standard-case processing, compliance review, data governance and immutable audit evidence.

## What is implemented

- Responsive browser UI for desktop, tablet, mobile and browser zoom
- Cerberus SAML-style demo login adapter
- Customer onboarding workflow with identity-document simulation
- Patronum explainable KYC risk adapter
- Human-in-the-loop approval and escalation queue
- SQLite persistence for cases, evidence and AI assessments
- Hash-chained audit evidence with integrity verification
- Data-governance dashboard with accountable domain owners
- Automated backend tests

## Start locally

Python 3.12 is already installed on this computer.

```powershell
.\start-verita.ps1
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

To reset the demonstration data, stop the server and run:

```powershell
.\reset-demo.ps1
```

## Run the tests

```powershell
python -m unittest discover -s tests -v
```

## Docker alternative

```powershell
docker build -t verita-mvp .
docker run --rm -p 8080:8080 verita-mvp
```

## Suggested demo flow

1. Sign in with the simulated Cerberus SSO button.
2. Present the operational KPIs and FR/AU case split.
3. Open **Review queue**, select a case and approve or escalate it.
4. Click **New onboarding**, complete the form and simulate document upload.
5. Show Patronum auto-approval for a standard individual case.
6. Open **Data governance** and show the verified hash-chain evidence.

## Production integration boundary

The local implementation deliberately avoids institutional credentials. In production:

- `CerberusAdapter` is replaced by Okta SAML 2.0 federation and role mapping.
- `PatronumAdapter` is replaced by the audited enterprise AI gateway.
- SQLite is replaced by Azure-managed persistence.
- Simulated document upload is replaced by encrypted object storage and malware scanning.
- The local HTTP server is deployed behind an Azure gateway with TLS, observability and resilience controls.

See [docs/architecture.md](docs/architecture.md) for the full architecture mapping.
