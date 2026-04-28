"""
Seed data for development — Kenyan users, chats, and messages.

Runs after alembic upgrade head. Idempotent: checks if seed data already exists.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from db.models.chat import Chat, ChatParticipant, ChatType
from db.models.message import DeliveryStatus, Message, MessageDelivery, MessageStatus
from db.models.user import User
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ─── Kenyan seed users ─────────────────────────────────────────────
SEED_USERS = [
    {"phone": "+254712345678", "name": "Wanjiku Kamau"},
    {"phone": "+254723456789", "name": "Omondi Otieno"},
    {"phone": "+254734567890", "name": "Achieng' Nyambura"},
    {"phone": "+254745678901", "name": "Kiprop Chebet"},
    {"phone": "+254756789012", "name": "Mwende Mutua"},
    {"phone": "+254767890123", "name": "Barasa Wekesa"},
    {"phone": "+254778901234", "name": "Nyokabi Maina"},
    {"phone": "+254789012345", "name": "Juma Mwangi"},
]

# Conversations: (sender_index, receiver_index, messages_list)
# messages_list: list of (text, hours_ago)
SEED_CONVERSATIONS = [
    (
        0,
        1,
        [  # Wanjiku ↔ Omondi
            ("Mambo vipi? Umesha fika?", 48),  # 2 days ago
            ("Poa ndugu. Niko njiani tu.", 47),
            ("Sawa, tutaonana huko stage.", 47),
            ("Nimefika, uko wapi?", 2),  # 2 hours ago
            ("Niko hapa kwa kiosk. Nakuja!", 1.5),
        ],
    ),
    (
        2,
        3,
        [  # Achieng' ↔ Kiprop
            ("Nyasaye omera! In anyo nade?", 72),  # 3 days ago
            ("Ber ahinya. In to?", 71),
            ("Aneno ni idhi e dala?", 70),
            ("Ee, abiro. Abiro konyi gi chiemo.", 10),  # 10 hours ago
            ("Heri timo sa kuon. Ingiere!", 9.5),
        ],
    ),
    (
        4,
        5,
        [  # Mwende ↔ Barasa
            ("Habari za asubuhi?", 24),  # 1 day ago
            ("Nzuri sana. Umelala poa?", 23),
            ("Sawa kabisa. Leo una mpango gani?", 22),
            ("Nataka tupige story baadaye.", 3),  # 3 hours ago
            ("Sawa, nitakupigia simu saa tatu.", 2.8),
        ],
    ),
    (
        6,
        7,
        [  # Nyokabi ↔ Juma
            ("Uko na plan za leo?", 6),  # 6 hours ago
            ("Niko kwa kazi hadi saa kumi.", 5.5),
            ("Twende tuke kula chapo baadaye?", 5),
            ("Njaa imekula kabisa. Chapo na kuku?", 4.5),
            ("Hio ndio best combo! Tutafute hoteli njema.", 4),
        ],
    ),
    (
        0,
        2,
        [  # Wanjiku ↔ Achieng' (cross-tribe)
            ("Niaje, ushafika?", 12),
            ("Pia sijafika, traffic imekula", 11.5),
        ],
    ),
]

# Group chats
SEED_GROUPS = [
    {
        "name": "Kanisa Choir Group",
        "members": [0, 1, 2, 3],
        "messages": [
            (0, "Jumatano tunafanya rehearsal saa kumi. Msichelewe!", 96),
            (1, "Sawa, nitaleta vituo vipya vya mkusanyiko.", 95),
            (2, "Mungu abariki. Nimekuwa training solo ya leo.", 90),
            (3, "Naskia poa. Tutaanza na 'Ni Wewe' kwanza.", 85),
            (0, "Mkumbushe Kevin acheze keyboard kesho.", 48),
            (1, "Kevin amesema atakuja baada ya kazi.", 47),
        ],
    },
    {
        "name": "Kasarani Neighbourhood Watch",
        "members": [4, 5, 6, 7, 0],
        "messages": [
            (4, "Jamani, huyu jamaa anazunguka tangu jana usiku. Mtu anamjua?", 72),
            (5, "Amekuwa akiingia kwa compound za watu. Nimemshika picha.", 71),
            (6, "Lete hio picha kwa group. Tuwe watchful.", 70),
            (7, "Nimeona msee ako na hoodie nyekundu, akionekana suspicious.", 48),
            (0, "Nimemshout. Alikimbia nikimfuata. Polisi wametajwa.", 24),
            (4, "Asanteni kwa macho. Tushinde uhalifu pamoja!", 12),
        ],
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        existing = await db.execute(select(User).limit(1))
        if existing.scalar_one_or_none():
            logger.info("Seed data already exists, skipping.")
            return

        logger.info("Seeding Kenyan demo data...")

        # ─── Create users ───────────────────────────────────────
        created_users = []
        for data in SEED_USERS:
            user = User(
                id=uuid4(),
                phone_number=data["phone"],
                name=data["name"],
            )
            db.add(user)
            created_users.append(user)
        await db.flush()

        # ─── Create private chats and messages ──────────────────
        for sender_idx, receiver_idx, msgs in SEED_CONVERSATIONS:
            sender = created_users[sender_idx]
            receiver = created_users[receiver_idx]

            # Ensure sorted UUIDs for consistent participant check
            chat_id = _chat_id_for(sender.id, receiver.id)
            chat = Chat(
                id=chat_id,
                type=ChatType.PRIVATE,
            )
            db.add(chat)
            db.add_all(
                [
                    ChatParticipant(chat_id=chat.id, user_id=sender.id),
                    ChatParticipant(chat_id=chat.id, user_id=receiver.id),
                ]
            )
            await db.flush()

            for text, hours_ago in msgs:
                sender_user = created_users[sender_idx]
                msg = Message(
                    id=uuid4(),
                    chat_id=chat.id,
                    sender_id=sender_user.id,
                    text=text,
                    status=MessageStatus.READ,
                    created_at=datetime.utcnow() - timedelta(hours=hours_ago),
                )
                db.add(msg)

        # ─── Create group chats ─────────────────────────────────
        for group_data in SEED_GROUPS:
            chat = Chat(
                id=uuid4(),
                type=ChatType.GROUP,
                group_name=group_data["name"],
            )
            db.add(chat)
            for idx in group_data["members"]:
                db.add(ChatParticipant(chat_id=chat.id, user_id=created_users[idx].id))
            await db.flush()

            for sender_idx, text, hours_ago in group_data["messages"]:
                msg = Message(
                    id=uuid4(),
                    chat_id=chat.id,
                    sender_id=created_users[sender_idx].id,
                    text=text,
                    created_at=datetime.utcnow() - timedelta(hours=hours_ago),
                )
                db.add(msg)

        await db.commit()
        logger.info(
            f"Seeded {len(SEED_USERS)} users, "
            f"{len(SEED_CONVERSATIONS)} private chats, "
            f"{len(SEED_GROUPS)} group chats, "
            f"and messages across all conversations."
        )


def _chat_id_for(uid1: UUID, uid2: UUID) -> UUID:
    """Deterministic chat ID for a pair of users (sorted)."""
    from hashlib import md5

    sorted_ids = sorted([str(uid1), str(uid2)])
    hash_bytes = md5("".join(sorted_ids).encode()).digest()
    return UUID(bytes=hash_bytes[:16], version=4)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
