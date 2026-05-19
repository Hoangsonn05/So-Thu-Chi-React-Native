# Automated Reporting: Env, Deploy, and Safe E2E Checks

## Required Render environment

- `FIREBASE_KEY_PATH`: absolute path to the Firebase service account JSON on Render. For local development only, the server falls back to `Server_Local/firebase_key.json`.
- `OPENROUTER_API_KEY`: required for AI parsing, OCR, agent chat, and AI comments. Finance reports fall back to rule-based comments if this is missing or OpenRouter fails.
- `BASE_WEBHOOK_URL`: public backend URL used when registering Telegram webhooks.
- `RESEND_API_KEY`: required only for email export.
- `ENABLE_DEBUG_ENDPOINTS`: set to `true` only while running controlled production checks.
- `DEBUG_ENDPOINT_TOKEN`: required when debug endpoints are enabled. Send it as `X-Debug-Token`.

Optional collector env vars:

- `EXTERNAL_HTTP_TIMEOUT_SECONDS`
- `EXTERNAL_COLLECTOR_USER_AGENT`
- `EXTERNAL_GOLD_URL`, `EXTERNAL_GOLD_BACKUP_URLS`
- `EXTERNAL_FUEL_URL`
- `EXTERNAL_USD_RATE_URL`, `EXTERNAL_USD_RATE_BACKUP_URLS`
- `EXTERNAL_OPENAI_PRICING_URL`, `EXTERNAL_GEMINI_PRICING_URL`, `EXTERNAL_DEEPSEEK_PRICING_URL`

## Render deploy steps

1. Set the required env vars above in Render.
2. Provide Firebase credentials as a Render secret file and point `FIREBASE_KEY_PATH` at that file.
3. Deploy the backend service normally. Do not expose `Server_Local/.env` or `firebase_key.json`.
4. Confirm logs show scheduler startup and config presence only, for example `OPENROUTER_API_KEY=present`.
5. Confirm there are no logs containing OpenRouter keys, Telegram bot tokens, FCM tokens, or full Telegram bot URLs.

## Debug endpoints

Debug routes are not registered unless `ENABLE_DEBUG_ENDPOINTS=true`.

All debug requests require:

```http
X-Debug-Token: <DEBUG_ENDPOINT_TOKEN>
```

If `DEBUG_ENDPOINT_TOKEN` is missing, endpoints return:

```json
{"detail":"debug_not_configured"}
```

Available endpoints:

- `POST /api/debug/create-test-task`
- `POST /api/debug/run-scheduler-once`
- `GET /api/debug/user-report-state/{uid}`

`create-test-task` only creates IDs beginning with `debug_`.

Example:

```bash
curl -X POST "$BASE_URL/api/debug/create-test-task" \
  -H "Content-Type: application/json" \
  -H "X-Debug-Token: $DEBUG_ENDPOINT_TOKEN" \
  -d '{"uid":"TEST_UID","task_type":"daily_finance_report","schedule_type":"daily","time":"20:00","next_run_now":true}'

curl -X POST "$BASE_URL/api/debug/run-scheduler-once" \
  -H "Content-Type: application/json" \
  -H "X-Debug-Token: $DEBUG_ENDPOINT_TOKEN" \
  -d '{"uid":"TEST_UID"}'

curl "$BASE_URL/api/debug/user-report-state/TEST_UID" \
  -H "X-Debug-Token: $DEBUG_ENDPOINT_TOKEN"
```

The state endpoint recursively redacts tokens, API keys, authorization values, FCM tokens, and Telegram bot URLs.

## App AI assistant endpoint

The React Native AI assistant must call the backend instead of OpenRouter directly.

```http
POST /api/ai/assistant
```

Request:

```json
{
  "firebase_uid": "USER_UID",
  "message": "ăn sáng 30k",
  "mode": "auto"
}
```

Response:

```json
{
  "success": true,
  "message": "Đã ghi nhận chi 30.000đ cho Ăn uống.",
  "intent": "transaction",
  "transaction": {
    "type": 0,
    "amount": 30000,
    "category": "Ăn uống",
    "note": "Ăn sáng",
    "date": "19/05/2026",
    "source": "Tiền mặt"
  },
  "transaction_id": "appai_1"
}
```

Expo needs `EXPO_PUBLIC_API_BASE_URL` set to the backend base URL. Do not add `OPENROUTER_API_KEY` or any public OpenRouter key to Expo env.

## Safe production test flow

Use a dedicated Firebase test UID with a known Telegram/FCM delivery channel.

1. Enable debug endpoints temporarily on Render.
2. Create a `debug_` finance task with `next_run_now=true`.
3. Run scheduler once and confirm a `success`, `failed`, or `skipped` outcome is returned.
4. Read `user-report-state` and confirm:
   - `scheduled_tasks`
   - today `delivery_state`
   - `finance_reports`
   - `external_reports`
   - `external_snapshots`
5. Test external manual-before-07:00 behavior by calling the normal Telegram/agent flow for `morning_external_brief`, then run scheduler once for the test UID and verify `skip_auto_today=true`.
6. Test no-delivery-channel with a test UID that has no Telegram `botToken/chatId` and no FCM token; expected scheduler result is `failed` with `no_delivery_channel`, not a crash.
7. Disable debug endpoints after checks.

## Plugin/MCP policy

- Firebase MCP: use only to verify the test UID and specific report collections after a controlled test. Do not scan user data broadly.
- Render plugin: use only for env presence, service health, and scheduler/runtime logs. Do not redeploy unless explicitly requested.
- GitHub plugin: use only for final diff, PR, or commit preparation. Do not commit until tests pass and a diff summary is reviewed.
- Expo plugin: do not use for backend-only changes. Use it only if mobile UI, Expo config, or native behavior changes.
