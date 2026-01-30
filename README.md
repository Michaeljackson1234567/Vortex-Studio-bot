# Vortex Studio Order Notifier (Discord Bot)

A tiny FastAPI service that DMs specific Discord users when a new order is submitted from your site. Uses a Discord bot token and the HTTP API to open a DM channel and send a rich embed containing the order details.

This service intentionally only notifies the configured user IDs (admins/owners).

## Features
- Sends a well-designed embed with:
  - Full Name
  - Project Name
  - Project Type
  - Deadline (mm/dd/yyyy)
  - Project Description
  - Submitted By (Discord mention, if available)
- Includes action buttons: Open Orders and Visit Site.
- Restricts notifications to `ADMIN_USER_IDS` only.
- Optional shared secret header to prevent abuse from the public internet.

## Security First
You posted app credentials publicly; regenerate both the Discord Bot Token and the OAuth Client Secret in the Discord Developer Portal before going live. Never commit real secrets. Use `.env` locally and provider secrets in production.

## Getting Started

1) Create and fill `.env` based on `.env.example`:

```
DISCORD_BOT_TOKEN=xxxx.your.new.bot.token
ADMIN_USER_IDS=1218987081876115476,1152334351384707173
SHARED_WEBHOOK_SECRET=long-random-secret
ORDERS_URL=https://vortexstudioo.netlify.app/orders
SITE_URL=https://vortexstudioo.netlify.app/
```

2) Install dependencies and run locally (Python 3.10+ recommended):

```
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

3) Test the endpoint:

```
curl -X POST http://localhost:8000/order \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: long-random-secret" \
  -d '{
    "full_name": "John Doe",
    "project_name": "Cool AI App",
    "project_type": "AI Model",
    "deadline": "02/15/2026",
    "description": "Build an LLM-based summarizer.",
    "customer_discord_id": "123456789012345678",
    "customer_username": "johnny#0001"
  }'
```

If the target users have DMs closed, Discord returns 403 and the service will record an error for that user while continuing for others.

## Deploying
You can deploy this anywhere that supports Python web apps (Render, Railway, Fly.io, etc.). Expose port `$PORT`, set the environment variables from your `.env.example`, and run `uvicorn app:app`.

- Example start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`

## Connecting the Website
Do NOT call this API directly from the public browser with the shared secret. Use a server-side function to forward requests.

### Netlify Function (recommended)
Create `netlify/functions/forward-order.js` in your site project:

```js
export default async (event) => {
  if (event.httpMethod !== "POST") return { statusCode: 405, body: "Method Not Allowed" };
  const body = JSON.parse(event.body || "{}");

  // Validate required fields quickly
  const required = ["full_name", "project_name", "project_type", "deadline", "description"];
  for (const k of required) if (!body[k]) return { statusCode: 400, body: `Missing ${k}` };

  const resp = await fetch(process.env.ORDER_BOT_URL + "/order", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Token": process.env.SHARED_WEBHOOK_SECRET,
    },
    body: JSON.stringify(body),
  });

  return { statusCode: resp.status, body: await resp.text() };
}
```

Netlify env variables to set:
- `ORDER_BOT_URL` → your deployed FastAPI base URL
- `SHARED_WEBHOOK_SECRET` → must match the bot service `.env`

From your order form submit handler in the site, POST to `/.netlify/functions/forward-order` with the form data (and include the logged-in Discord user id/username if you have them from OAuth).

## JSON Payload Schema
```json
{
  "full_name": "string",
  "project_name": "string",
  "project_type": "string",
  "deadline": "mm/dd/yyyy",
  "description": "string",
  "customer_discord_id": "string (optional)",
  "customer_username": "string (optional)"
}
```

## Notes
- Keep the two admin IDs exactly as required; adjust `ADMIN_USER_IDS` if you ever need to add/remove.
- If embeds need brand theming (icon/color), we can extend the service to accept branding envs.
