import asyncio
import multiprocessing
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8.util import run_forever
from ipv8_service import IPv8
from lab3_community import Lab3Community
from blockchain_community import BlockchainCommunity

 # ─── Main ────────────────────────────────────
 
async def main():    
    builder = (
        ConfigBuilder()
        .clear_keys()
        .clear_overlays()
        .add_key("my_key", "curve25519", "my_key.pem") # Change this to own key
        .add_overlay(
            "Lab3Community",
            "my_key",
            [WalkerDefinition(Strategy.RandomWalk, 50, {"timeout": 3.0})],
            default_bootstrap_defs,
            {},
            [("started",)],
        )
        # .add_overlay(
        #     "BlockchainCommunity",
        #     "my_key",
        #     [WalkerDefinition(Strategy.RandomWalk, 50, {"timeout": 3.0})],
        #     default_bootstrap_defs,
        #     {},
        #     [("started",)],
        # )
    )
 
    ipv8_instance = IPv8(
        builder.finalize(),
        extra_communities={"Lab3Community": Lab3Community, "BlockchainCommunity": BlockchainCommunity},
    )
    await ipv8_instance.start()

    print("IPv8 started")

    await run_forever()
 


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn")
    multiprocessing.freeze_support()
    asyncio.run(main())