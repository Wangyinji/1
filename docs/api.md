# Verita API

All endpoints except login and health require `Authorization: Bearer <token>`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health probe |
| `POST` | `/api/auth/login` | Create a Cerberus demo session |
| `GET` | `/api/dashboard` | Operational metrics |
| `GET` | `/api/cases` | List onboarding cases |
| `GET` | `/api/cases/{id}` | Retrieve case details and evidence |
| `POST` | `/api/cases` | Create a case and run Patronum |
| `POST` | `/api/cases/{id}/decision` | Approve or escalate a review case |
| `GET` | `/api/governance` | Data-domain ownership and controls |
| `GET` | `/api/audit` | Audit entries and hash-chain verification |

## Create-case example

```json
{
  "fullName": "Camille Laurent",
  "email": "camille.laurent@example.fr",
  "country": "FR",
  "customerType": "Individual",
  "address": "16 rue Victor Hugo, Paris"
}
```
