"""Deterministic synthetic fixtures (no real accounts/secrets). Re-run to regenerate."""
import copy, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
H, H2, H3 = "a"*64, "b"*64, "c"*64
launch = {"schema_version":"1.0","run_id":"run_demo001","session_id":"sess_demo001","account_id":"acc_demo001","session_epoch":3,"lease_id":"lease_demo001","lease_expires_at":"2026-10-23T20:00:00Z","client_instance_id":"client_demo001","task_id":"task_bank_probe","task_descriptor_hash":H,"artifact_hash":H2,"config_hash":H3,"credential_ref":"ref:vault:acc_demo001","adapter_endpoint":"http://127.0.0.1:8081/agent","adapter_token_ref":"ref:vault:adapter_demo001","max_session_seconds":3600,"drain_timeout_seconds":120}
T = "2026-10-23T19:00:00Z"
def f(q, v, src, at=T): return {"quality":q,"source":src,"observed_at":at,"value":v}
obs = {"schema_version":"1.0","observation_id":"obs_demo001","account_id":"acc_demo001","client_instance_id":"client_demo001","session_epoch":3,"observed_at":T,"state_version":7,"consistency":"BEST_EFFORT","fields":{
 "client.logged_in": f("KNOWN", True, "agent.status"), "bank.open": f("KNOWN", True, "agent.bank"),
 "bank.items": f("KNOWN", [[995,1200],[1511,40]], "agent.bank"), "inventory.items": f("KNOWN", [], "agent.inventory"),
 "player.position": f("STALE", [3222,3218,0], "agent.player", "2026-10-23T18:59:00Z"), "varp.281": f("UNKNOWN", None, "agent.varp")}}
intent = {"schema_version":"1.0","command_id":"cmd_demo001","account_id":"acc_demo001","session_id":"sess_demo001","client_instance_id":"client_demo001","session_epoch":3,"lease_id":"lease_demo001","expected_state_version":7,"operation":"BANK_WITHDRAW","params":{"item_id":1511,"quantity":10,"noted":False},"precondition_ref":H,"postcondition_ref":H2,"issued_at":"2026-10-23T19:00:01Z","expires_at":"2026-10-23T19:00:31Z","policy_version":1,"config_hash":H3}
intent_noop = dict(intent, command_id="cmd_demo002", operation="NOOP", params={})
intent_walk = dict(intent, command_id="cmd_demo003", operation="WALK_TO", params={"x":3222,"y":3218,"plane":0})
res_ok = {"schema_version":"1.0","event_id":"evt_demo001","command_id":"cmd_demo001","session_id":"sess_demo001","session_epoch":3,"state_version":8,"transport_status":"ACKNOWLEDGED","effect_status":"VERIFIED","reason_code":"NONE","evidence_refs":["obs_demo002"],"occurred_at":"2026-10-23T19:00:05Z"}
res_unknown = dict(res_ok, event_id="evt_demo002", transport_status="TIMEOUT", effect_status="UNKNOWN", evidence_refs=[])
res_notsent = dict(res_ok, event_id="evt_demo003", transport_status="NOT_SENT", effect_status="NOT_ATTEMPTED", reason_code="STALE_CONTEXT", evidence_refs=[])
ai = {"schema_version":"1.0","incident_id":"incident_demo001","account_id":"acc_demo001","session_epoch":3,"observed_state_version":7,"diagnosis":"Requires operator review","suggested_action":"REQUEST_HUMAN_REVIEW","parameters":{},"requires_human_approval":True,"confidence":0.5}
VALID = {"SessionLaunch":{"basic":launch},"Observation":{"basic":obs},"CommandIntent":{"bank_withdraw":intent,"noop":intent_noop,"walk_to":intent_walk},"ResultEvent":{"verified":res_ok,"timeout_unknown":res_unknown,"not_sent":res_notsent},"AIProposal":{"review":ai}}
def mut(base, **kw):
    d = copy.deepcopy(base)
    for k, v in kw.items():
        if v is Ellipsis: d.pop(k)
        else: d[k] = v
    return d
INVALID = {
 "SessionLaunch":{"unknown_version":mut(launch,schema_version="2.0"),"missing_lease":mut(launch,lease_id=...),"extra_field":mut(launch,password="hunter2"),"epoch_zero":mut(launch,session_epoch=0),"epoch_bool":mut(launch,session_epoch=True),"secret_not_ref":mut(launch,credential_ref="p@ssw0rd"),"remote_endpoint":mut(launch,adapter_endpoint="http://10.0.0.5:8081"),"seconds_zero":mut(launch,max_session_seconds=0),"bad_hash":mut(launch,config_hash="xyz"),"bad_timestamp":mut(launch,lease_expires_at="2026-10-23 20:00:00"),"id_is_pid":mut(launch,client_instance_id="12345")},
 "Observation":{"unknown_with_value":mut(obs,fields={"bank.items":f("UNKNOWN",[],"x")}),"known_with_null":mut(obs,fields={"bank.open":f("KNOWN",None,"x")}),"empty_fields":mut(obs,fields={}),"unnamespaced_field":mut(obs,fields={"bank":f("KNOWN",True,"x")}),"negative_state_version":mut(obs,state_version=-1),"bad_consistency":mut(obs,consistency="ATOMIC")},
 "CommandIntent":{"withdraw_missing_params":mut(intent,params={}),"withdraw_extra_param":mut(intent,params={"item_id":1,"quantity":1,"noted":False,"force":True}),"withdraw_zero_quantity":mut(intent,params={"item_id":1,"quantity":0,"noted":False}),"noop_with_params":mut(intent_noop,params={"anything":1}),"walk_plane_4":mut(intent_walk,params={"x":1,"y":1,"plane":4}),"unknown_operation":mut(intent,operation="SELL_ON_GE",params={}),"quantity_bool":mut(intent,params={"item_id":1,"quantity":True,"noted":False}),"state_version_bool":mut(intent,expected_state_version=False),"policy_zero":mut(intent,policy_version=0),"free_text_path":mut(intent,params={"item_id":1,"quantity":1,"noted":"../../etc"})},
 "ResultEvent":{"not_sent_but_verified":mut(res_notsent,effect_status="VERIFIED",evidence_refs=["obs_demo009"]),"verified_without_evidence":mut(res_ok,evidence_refs=[]),"timeout_not_attempted":mut(res_unknown,effect_status="NOT_ATTEMPTED"),"not_attempted_reason_none":mut(res_notsent,reason_code="NONE"),"duplicate_evidence":mut(res_ok,evidence_refs=["obs_dup001","obs_dup001"]),"unknown_reason":mut(res_ok,reason_code="BANNED")},
 "AIProposal":{"free_action":mut(ai,suggested_action="WITHDRAW_ALL"),"with_parameters":mut(ai,parameters={"item":995}),"no_approval":mut(ai,requires_human_approval=False),"confidence_over_1":mut(ai,confidence=1.5),"confidence_bool":mut(ai,confidence=True),"extra_execute_field":mut(ai,execute=True)}}
if __name__ == "__main__":
    n = 0
    for kind, table in (("valid", VALID), ("invalid", INVALID)):
        for contract, cases in table.items():
            d = ROOT / kind / contract; d.mkdir(parents=True, exist_ok=True)
            for name, doc in cases.items():
                (d / f"{name}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n"); n += 1
    print("fixtures written:", n)
