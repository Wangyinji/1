# Verita Five-Minute Software Demo

## Opening

“Verita is the unified FR and AU onboarding capability. This implementation demonstrates the target operating model: secure intake, explainable automation and controlled human intervention.”

## 1. Cerberus login

Click **Continue with Cerberus SSO**.

Explain that the MVP uses a local adapter. In production it maps to the Cerberus Okta SAML 2.0 instance and least-privilege roles.

## 2. Operations dashboard

Show the KPI cards and FR/AU market split.

Explain that the Architecture Board can monitor straight-through processing, activation time and golden-record quality.

## 3. Human-in-the-loop review

Open **Review queue**, select a high-risk case and approve it.

Explain that Patronum returns reasons and a confidence score. It does not autonomously approve sensitive cases.

## 4. Standard onboarding

Click **New onboarding** and enter:

- Name: `Camille Laurent`
- Email: `camille.laurent@example.fr`
- Country: `France`
- Customer type: `Individual`
- Address: `16 rue Victor Hugo, Paris`

Simulate the encrypted upload and continue to Patronum. Create and activate the case after the 96-point recommendation appears.

## 5. Governance and auditability

Open **Data governance**.

Show domain ownership, lineage and the verified hash chain. Explain that every login, case creation, AI assessment and human decision is traceable.
