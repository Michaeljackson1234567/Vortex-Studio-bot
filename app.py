import os
from typing import Optional, List
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ADMIN_USER_IDS = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "1218987081876115476,1152334351384707173").split(",") if x.strip()]
SHARED_WEBHOOK_SECRET = os.getenv("SHARED_WEBHOOK_SECRET")
ORDERS_URL = os.getenv("ORDERS_URL", "https://vortexstudioo.netlify.app/orders")
SITE_URL = os.getenv("SITE_URL", "https://vortexstudioo.netlify.app/")

if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is required. Set it in your environment or .env file.")

app = FastAPI(title="Vortex Studio Order Notifier", version="1.0.0")

# Allow your site to call directly if you choose (you can restrict origins further)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[SITE_URL.rstrip("/")],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"]
)


class OrderPayload(BaseModel):
    full_name: str = Field(..., alias="full_name")
    project_name: str = Field(..., alias="project_name")
    project_type: str = Field(..., alias="project_type")
    deadline: str = Field(..., alias="deadline", description="mm/dd/yyyy")
    description: str = Field(..., alias="description")

    # Optional details from your OAuth sign-in (pass if available)
    customer_discord_id: Optional[str] = Field(None, alias="customer_discord_id")
    customer_username: Optional[str] = Field(None, alias="customer_username")


def build_embed(order: OrderPayload) -> dict:
    # Truncate long description to stay under embed limits
    desc = order.description.strip()
    if len(desc) > 4000:
        desc = desc[:3995] + "…"
    # Separate shorter excerpt to fit field value max (1024)
    desc_field = desc if len(desc) <= 1000 else (desc[:995] + "…")

    submitted_by = "Unknown"
    if order.customer_discord_id:
        mention = f"<@{order.customer_discord_id}>"
        if order.customer_username:
            submitted_by = f"{mention} ({order.customer_username}, {order.customer_discord_id})"
        else:
            submitted_by = f"{mention} ({order.customer_discord_id})"

    embed = {
        "title": "🧾 New Order Received",
        "url": ORDERS_URL,
        "description": desc,
        "color": 0x57F287,  # Discord green
        "fields": [
            {"name": "Full Name", "value": order.full_name, "inline": True},
            {"name": "Project Name", "value": order.project_name, "inline": True},
            {"name": "Project Type", "value": order.project_type, "inline": True},
            {"name": "Deadline", "value": order.deadline, "inline": True},
            {"name": "Project Description", "value": desc_field or "(no description)", "inline": False},
            {"name": "Submitted By", "value": submitted_by, "inline": False},
        ],
        "footer": {"text": "Vortex Studio Orders"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return embed


def link_components() -> List[dict]:
    return [
        {
            "type": 1,  # action row
            "components": [
                {
                    "type": 2,  # button
                    "style": 5,  # LINK
                    "label": "Open Orders",
                    "url": ORDERS_URL,
                },
                {
                    "type": 2,
                    "style": 5,
                    "label": "Visit Site",
                    "url": SITE_URL,
                },
            ],
        }
    ]


async def send_dm_to_user(admin_id: str, embed: dict) -> None:
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    async with httpx.AsyncClient(base_url="https://discord.com/api/v10", timeout=15) as client:
        # Create (or fetch) a DM channel with the admin
        dm_resp = await client.post("/users/@me/channels", json={"recipient_id": admin_id}, headers=headers)
        if dm_resp.status_code == 403:
            # User's DMs might be closed; skip gracefully
            return
        if dm_resp.is_error:
            raise HTTPException(status_code=502, detail=f"Failed to open DM with {admin_id}: {dm_resp.text}")

        channel_id = dm_resp.json()["id"]
        payload = {
            "content": "",
            "embeds": [embed],
            "components": link_components(),
        }
        msg_resp = await client.post(f"/channels/{channel_id}/messages", json=payload, headers=headers)
        if msg_resp.is_error:
            raise HTTPException(status_code=502, detail=f"Failed to send DM to {admin_id}: {msg_resp.text}")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/order")
async def receive_order(order: OrderPayload, x_auth_token: Optional[str] = Header(default=None, alias="X-Auth-Token")):
    # Shared secret check to prevent abuse (strongly recommended)
    if SHARED_WEBHOOK_SECRET and x_auth_token != SHARED_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Ensure we only ever DM the allowed recipients
    if not ADMIN_USER_IDS:
        raise HTTPException(status_code=500, detail="ADMIN_USER_IDS is not configured")

    embed = build_embed(order)

    # Send to each authorized admin; ignore DM-closed users silently
    errors = []
    for admin_id in ADMIN_USER_IDS:
        try:
            await send_dm_to_user(admin_id, embed)
        except HTTPException as e:
            errors.append({"admin_id": admin_id, "error": e.detail})

    return {"ok": True, "delivered_to": [a for a in ADMIN_USER_IDS], "errors": errors}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
