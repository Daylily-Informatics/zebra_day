# zebra_day Playwright E2E

This suite runs live browser authentication against Cognito for two zebra_day GUI identities:

- standard operator user
- admin user

Required environment:

```bash
export ZDAY_E2E_BASE_URL="https://localhost:8118"
export ZDAY_E2E_COGNITO_REGION="us-west-2"
export ZDAY_E2E_COGNITO_USER_POOL_ID="..."
export ZDAY_E2E_AWS_PROFILE="lsmc"  # optional
export ZDAY_E2E_STANDARD_EMAIL="zebra-day-e2e-standard@example.com"
export ZDAY_E2E_STANDARD_PASSWORD="CodexPlaywright1!"
export ZDAY_E2E_ADMIN_EMAIL="zebra-day-e2e-admin@example.com"
export ZDAY_E2E_ADMIN_PASSWORD="CodexPlaywright1!"
```

Install browser support:

```bash
python -m pip install -e .
playwright install chromium
```

Run the auth slice:

```bash
pytest tests/e2e/test_auth_e2e.py -m e2e
```

Run the full live browser suite:

```bash
pytest tests/e2e/ -m e2e
```
