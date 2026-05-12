from ipv8.messaging.payload_dataclass import VariablePayload

# ─── Message payloads ────────────────────────

class RegisterPayload(VariablePayload):
    msg_id = 1
    format_list = ["varlenH", "varlenH", "varlenH"]
    names = ["member1_key", "member2_key", "member3_key"]

class ResponseRegisterPayload(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenHutf8", "varlenHutf8"]
    names = ["success", "group_id", "message"]

class ChallengeRequestPayload(VariablePayload):
    msg_id = 3
    format_list = ["varlenHutf8"]
    names = ["group_id"]

class ChallengeResponsePayload(VariablePayload):
    msg_id = 4
    format_list = ["varlenH", "q", "d"]
    names = ["nonce", "round_number", "deadline"]

class SubmissionPayload(VariablePayload):
    msg_id = 5
    format_list = ["varlenHutf8", "q", "varlenH", "varlenH", "varlenH"]
    names = ["group_id", "round_number", "sig1", "sig2", "sig3"]

class RoundResultPayload(VariablePayload):
    msg_id = 6
    format_list = ["?", "q", "q", "varlenHutf8"]
    names = ["success", "round_number", "round_completed", "message"]


# ─── Internal peer-to-peer payloads (not seen by the server) ────────────────

class GroupIdPayload(VariablePayload):
    """Member 0 broadcasts the registered group_id to members 1 and 2."""
    msg_id = 7
    format_list = ["varlenHutf8"]
    names = ["group_id"]

class SignaturePayload(VariablePayload):
    """Non-leader sends its signature on the nonce back to the round leader."""
    msg_id = 9
    format_list = ["q", "q", "varlenH"]
    names = ["round_number", "member_index", "signature"]