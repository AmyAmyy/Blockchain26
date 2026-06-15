from ipv8.messaging.payload_dataclass import VariablePayload

# ─── Part 1 ────────────────────────

class RegisterBlockchain(VariablePayload):
    msg_id = 1
    format_list = ["varlenHutf8", "varlenH"]
    names = ["group_id", "community_id"]

class RegisterResponse(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenHutf8"]
    names = ["success", "message"]

# ─── Part 2 ────────────────────────

class SubmitTransaction(VariablePayload):
    msg_id = 1
    format_list = ["varlenH", "varlenH", "q", "varlenH"]
    names = ["sender_key", "data", "timestamp", "signature"]

class SubmitTransactionResponse(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenH", "varlenHutf8"]
    names = ["success", "tx_hash", "message"]

class GetChainHeight(VariablePayload):
    msg_id = 3
    format_list = ["q"]
    names = ["request_id"]

class ChainHeightResponse(VariablePayload):
    msg_id = 4
    format_list = ["q", "q", "varlenH"]
    names = ["request_id", "height", "tip_hash"]

class GetBlock(VariablePayload):
    msg_id = 5
    format_list = ["q"]
    names = ["height"]

class BlockResponse(VariablePayload):
    msg_id = 6
    format_list = ["q", "varlenH", "varlenH", "q", "q", "q", "varlenH", "varlenH"]
    names = ["height", "prev_hash", "txs_hash", "timestamp", "difficulty", "nonce", "block_hash", "tx_hashes"]

# ─── Blockchain community messages ────────────────────────

class GetMultipleBlocks(VariablePayload):
    msg_id = 7
    format_list = ["q"]
    names = ["start_height"]

class MultipleBlocksResponse(VariablePayload):
    msg_id = 8
    format_list = ["q", "q", "varlenH"]
    names = ["start_height", "num_blocks", "blocks_data"]