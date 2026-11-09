# Study Tools Cloud

Server-only Gemini/OpenAI gateway for the portable Windows study helper.
No provider key is present in this checkout. SERVICE_ENABLED is false until the
owner explicitly configures a funded key through Sites runtime secrets.

API: GET /health, POST /v1/register, POST /v1/infer.
Device credentials are random and stored hashed in D1. Quota reservations are
transactional and idempotent. Images, recognized questions and answers are not
stored. Registration uses a salted IP hash, not a stored raw address.

Defaults: 50 lifetime attempts, 20 daily globally, 10 daily per installation,
2 per minute per installation. These are request limits, not a USD balance.
An accepted failed request still uses a slot; there is no automatic paid retry.

Runtime secrets: IP_HASH_SECRET, SERVICE_ENABLED, AI_PROVIDER, AI_MODEL,
GEMINI_API_KEY or OPENAI_API_KEY. Optional quota settings are TOTAL_REQUEST_LIMIT,
DAILY_REQUEST_LIMIT, CLIENT_DAILY_LIMIT and QUOTA_NAMESPACE. Never put secrets in
the source or the desktop ZIP. A new namespace deliberately starts a new lifetime
counter; only the owner may change it. The site audience must remain public for
anonymous desktop registration; access is still controlled by device tokens and limits.

Build: npm run build. Tests: npm test. D1 migrations: npm run db:generate.
Publish through the Sites source workflow; do not use wrangler deploy directly.
