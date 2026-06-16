"""
Lab 1 — Proof of Work over IPv8
================================
Fill in YOUR_EMAIL and YOUR_GITHUB_URL before running.

Usage:
    pip install pyipv8
    python lab1_client.py
"""

import asyncio
import hashlib
import multiprocessing
import os
import struct
import time
from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs, BootstrapperDefinition, Bootstrapper
from ipv8.keyvault.crypto import default_eccrypto
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.payload_dataclass import VariablePayload, vp_compile
from ipv8.peer import Peer as PeerType
from ipv8_service import IPv8

# ──────────────────────────────────────────────
# FILL THESE IN BEFORE RUNNING
# ──────────────────────────────────────────────
YOUR_EMAIL = ""   # <── change this
YOUR_GITHUB_URL = "https://github.com/AmyAmyy/Blockchain26"  # <── change this
# ──────────────────────────────────────────────

COMMUNITY_ID_HEX = "2c1cc6e35ff484f99ebdfb6108477783c0102881"
SERVER_PUBKEY_HEX = (
    "4c69624e61434c504b3a86b23934a28d669c390e2d1fc0b0870706c4591cc0cb178bc5a811da6d87d27ef319b2638ef60cc8d119724f4c53a1ebfad919c3ac4136c501ce5c09364e0ebb"
)
DIFFICULTY_BITS = 28          # need 28 leading zero bits
KEY_FILE = "my_key.pem"       # your identity — back this up!
    
# Pre-compute the difficulty mask
# 28 bits → first 3 bytes == 0x00 AND top nibble of 4th byte == 0x00
_FULL_ZERO_BYTES = DIFFICULTY_BITS // 8          # 3
_REMAINING_BITS  = DIFFICULTY_BITS % 8           # 4
_LAST_MASK       = (0xFF << (8 - _REMAINING_BITS)) & 0xFF  # 0xF0
 
 
# ─── Message payloads ────────────────────────
 
class SubmissionPayload(VariablePayload):
    msg_id = 1
    format_list = ["varlenHutf8", "varlenHutf8", "q"]
    names = ["email", "github_url", "nonce"]
 
 
class ResponsePayload(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenHutf8"]
    names = ["success", "message"]
 
 
# Compile for faster (de)serialisation
SubmissionPayload = vp_compile(SubmissionPayload)
ResponsePayload   = vp_compile(ResponsePayload)
 
 
# ─── PoW mining ──────────────────────────────
 
def _check_hash(digest: bytes) -> bool:
    """Return True if digest has DIFFICULTY_BITS leading zero bits."""
    for i in range(_FULL_ZERO_BYTES):
        if digest[i] != 0:
            return False
    if _REMAINING_BITS > 0:
        if digest[_FULL_ZERO_BYTES] & _LAST_MASK:
            return False
    return True
 
 
def _mine_worker(email: str, github_url: str, start: int, step: int, result_queue, stop_event):
    """Worker process: tries nonces start, start+step, start+2*step, ..."""
    prefix = email.encode("utf-8") + b"\n" + github_url.encode("utf-8") + b"\n"
    nonce = start
    checked = 0
    t0 = time.time()
    while not stop_event.is_set():
        data = prefix + struct.pack(">q", nonce)
        digest = hashlib.sha256(data).digest()
        checked += 1
        if _check_hash(digest):
            print(f"  nonce: {nonce}")
            result_queue.put((nonce, digest.hex()))
            return
        nonce += step
        if checked % 500_000 == 0:
            elapsed = time.time() - t0
            rate = checked / elapsed / 1_000
            print(f"  [worker-{start % step}] {checked:,} hashes, "
                  f"{rate:.0f} kH/s, nonce={nonce}", flush=True)
 
 
def mine_pow(email: str, github_url: str) -> int:
    """
    Multi-process PoW search.
    Returns the winning nonce (non-negative int64).
    """
    print(f"\n⛏  Starting PoW search (difficulty={DIFFICULTY_BITS} bits)…")
    print(f"   email:      {email}")
    print(f"   github_url: {github_url}")
    print(f"   Expected ~{2**DIFFICULTY_BITS / 1e6:.0f}M hashes\n")
 
    num_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"   Using {num_workers} worker process(es)\n")
 
    manager = multiprocessing.Manager()
    result_queue = manager.Queue()
    stop_event   = manager.Event()
    hint = 507387470  # random nonce to hint workers where to start
 
    workers = []
    for i in range(num_workers):
        p = multiprocessing.Process(
            target=_mine_worker,
            args=(email, github_url, i + hint, num_workers, result_queue, stop_event),
            daemon=True,
        )
        p.start()
        workers.append(p)
 
    # Wait for first result
    nonce, digest_hex = result_queue.get()
    stop_event.set()
    for p in workers:
        p.join(timeout=2)
 
    print(f"\n✅  Found nonce={nonce}")
    print(f"   SHA-256: {digest_hex}")
    return nonce
 
 
# ─── IPv8 Community ──────────────────────────
 
class Lab1Community(Community):
    community_id = bytes.fromhex(COMMUNITY_ID_HEX)
 
    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ResponsePayload, self.on_response)
        self._server_peer: PeerType | None = None
        self._submitted = False
        self._done = asyncio.Event()
 
        # Pre-decode the server public key for comparison
        self._server_pubkey_bytes = bytes.fromhex(SERVER_PUBKEY_HEX)
 
    def started(self) -> None:
        self.network.add_peer_observer(self)
    # def started(self) -> None:
    #     async def debug_peers():
    #         peers = self.get_peers()
    #         print(f"👀 Peers seen: {len(peers)}")
    #         for p in peers:
    #             print("   ", p)

    #     self.register_task("debug_peers", debug_peers, interval=5.0, delay=0) 

    # ── peer discovery ──
 
    def on_peer_added(self, peer: PeerType) -> None:
        print("Peer discovered:", peer)
        pk_bytes = peer.public_key.key_to_bin()
        if pk_bytes == self._server_pubkey_bytes:
            print(f"🔗  Found server peer: {peer}")
            self._server_peer = peer
            if not self._submitted:
                self._submitted = True
                asyncio.ensure_future(self._submit())
                
 
    def on_peer_removed(self, peer: PeerType) -> None:
        if self._server_peer and peer == self._server_peer:
            print("⚠️  Server peer disconnected")
            self._server_peer = None
 
    # ── submission ──
 
    async def _submit(self) -> None:
        loop = asyncio.get_event_loop()

        # Run the blocking mining entirely off the event loop thread
        nonce = await loop.run_in_executor(None, mine_pow, YOUR_EMAIL, YOUR_GITHUB_URL)

        payload = SubmissionPayload(
            email=YOUR_EMAIL,
            github_url=YOUR_GITHUB_URL,
            nonce=nonce,
        )
        print(f"\n📤  Sending submission to server…")
        self.ez_send(self._server_peer, payload)
 
    # ── response handler ──
 
    @lazy_wrapper(ResponsePayload)
    def on_response(self, peer: PeerType, payload: ResponsePayload) -> None:
        # Only trust the real server
        if peer.public_key.key_to_bin() != self._server_pubkey_bytes:
            print(f"⚠️  Ignoring response from unknown peer {peer}")
            return
 
        status = "✅  ACCEPTED" if payload.success else "❌  REJECTED"
        print(f"\n{status}")
        print(f"   Message: {payload.message}")
        self._done.set()
 
    async def wait_for_response(self, timeout: float = 120.0) -> None:
        try:
            await asyncio.wait_for(self._done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print("\n⏰  Timed out waiting for server response.")
            print("    Check that IPv8 peer discovery is working and your")
            print("    packet is being signed (ez_send was used).")
 
 
# ─── Key management ──────────────────────────
 
def load_or_create_key(path: str):
    
    if os.path.exists(path):
        print(f"🔑  Loading existing key from {path}")
        with open(path, "rb") as f:
            return default_eccrypto.key_from_private_bin(f.read())
    else:
        print(f"🔑  Generating new key → {path}  (BACK THIS UP!)")
        key = default_eccrypto.generate_key("curve25519")
        with open(path, "wb") as f:
            f.write(key.key_to_bin())
        return key
 
 
# ─── Main ────────────────────────────────────
 
async def main():
    # Basic validation
    if YOUR_EMAIL == "yourname@student.tudelft.nl":
        print("❌  Set YOUR_EMAIL before running!")
        return
    if YOUR_GITHUB_URL == "https://github.com/you/lab1-repo":
        print("❌  Set YOUR_GITHUB_URL before running!")
        return
    if not (YOUR_EMAIL.endswith("@tudelft.nl") or YOUR_EMAIL.endswith("@student.tudelft.nl")):
        print("❌  Email must end in @tudelft.nl or @student.tudelft.nl")
        return
    if "\n" in YOUR_EMAIL or "\n" in YOUR_GITHUB_URL:
        print("❌  Email and URL must not contain newlines")
        return
 
    key = load_or_create_key(KEY_FILE)
 
    builder = (
        ConfigBuilder()
        .clear_keys()
        .clear_overlays()
        .add_key("my_key", "curve25519", KEY_FILE)
        .add_overlay(
            "Lab1Community",
            "my_key",
            [WalkerDefinition(Strategy.RandomWalk, 50, {"timeout": 3.0})],
            default_bootstrap_defs,
            {},
            [("started",)],
        )
    )
 
    ipv8_instance = IPv8(
        builder.finalize(),
        extra_communities={"Lab1Community": Lab1Community},
    )
    await ipv8_instance.start()
    await asyncio.sleep(5)
    print("Walkable addresses known:", ipv8_instance.network.get_walkable_addresses())
 
    community: Lab1Community = ipv8_instance.get_overlay(Lab1Community)
 
    print("🌐  IPv8 started — searching for server peer…")
    # await asyncio.sleep(5)
    # print(f"    Community: {COMMUNITY_ID_HEX}")
    # print(f"    Server PK: {SERVER_PUBKEY_HEX[:32]}…\n")
 
    await community.wait_for_response(timeout=600)
 
    await ipv8_instance.stop()
    print("\nDone.")
 


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    multiprocessing.freeze_support()
    asyncio.run(main())