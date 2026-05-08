from ipv8.messaging.payload_dataclass import VariablePayload

# ─── Message payloads ────────────────────────
 
class RegisterPayload(VariablePayload):
    msg_id = 1
    format_list = ["varlenH", "varlenH", "varlenH"]
    names = ["member1_key", "member2_key", "member3_key"]
 
class ResponsePayload(VariablePayload):
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
    format_list = ["varlenH", "q", "varlenH", "varlenH", "varlenH"]
    names = ["group_id", "round_number", "sig1", "sig2", "sig3"]

class RoundResultPayload(VariablePayload):
    msg_id = 6
    format_list = ["?", "q", "q", "varlenHut8"]
    names = ["success", "round_number", "round_completed", "message"]


# Compile for faster (de)serialisation
# RegisterPayload = vp_compile(RegisterPayload)
# ResponsePayload   = vp_compile(ResponsePayload)
# ChallengeRequestPayload = vp_compile(ChallengeRequestPayload)
# ChallengeResponsePayload = vp_compile(ChallengeResponsePayload)
# SubmissionPayload = vp_compile(SubmissionPayload)
# RoundResultPayload = vp_compile(RoundResultPayload)