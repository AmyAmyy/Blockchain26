import os

REGISTRATION_COMMUNITY_ID_HEX = "4c616233426c6f636b636861696e323032365057"
REGISTRATION_COMMUNITY_ID = bytes.fromhex(REGISTRATION_COMMUNITY_ID_HEX)

SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3ae3fc099fb56ca3b5e1de9a1c843387f2acdbb78b1bd4350"
    "ffde518068a0d246344b10d0d8c355fd0d76873e7d7f7838f3715e025af08f79132"
    "4495e083331ce6"
)
SERVER_PUBKEY_BYTES = bytes.fromhex(SERVER_PUBKEY_HEX)

GROUP_ID = "206290bb8cc8016f"
BLOCKCHAIN_COMMUNITY_ID = b"\x01\xb6\xf0}H\xc6R\xc9H\x1a\xd6\x11H\xf6{G%i\xf3i"


KEY_FILES = ["first_key.txt", "second_key.txt", "third_key.txt"]
MEMBER_COUNT = 3

# 0, 1, or 2. Unique per team member, determines which pubkey we expect to have.
MY_MEMBER_ID = int(os.environ.get("MY_MEMBER_ID", "1"))

def load_member_pubkeys() -> list[bytes]:
    """Load the 3 registered Lab-1 public keys from disk (hex-encoded)."""
    return [bytes.fromhex(open(p).read().strip()) for p in KEY_FILES]

# Keep nonce in signed int64 range
# Valid values are [0, 2^63 - 1], giving a space size of 2^63.
NONCE_SPACE = 2**63
DIFFICULTY = 20
MAX_TX_HASHES = 4 

GENESIS_PREV_HASH = b'\x00' * 32  # used as prev_hash of the genesis block
GENESIS_TIMESTAMP = 1748736000    # Fixed for all nodes
GENESIS_DIFFICULTY = 0
GENESIS_NONCE = 0

MAX_SEARCH_DEPTH_FORK = 30

PARTITION_TEST_ENABLED = False
PARTITION_START_AFTER_SECONDS = 30
PARTITION_DURATION_SECONDS = 60

MAX_SLEEP_MINING_LOOP = 15
SLEEP_POLLING_LOOP = 10

DUMP_DIR_PATH = "chain_dumps"