import importlib.util,pathlib,hashlib,json,types,torch
from mineru_vl_utils import MinerULogitsProcessor
from vllm import SamplingParams
root=pathlib.Path(importlib.util.find_spec("mineru_vl_utils").origin).parent
source=root/"logits_processor/vllm_v1_no_repeat_ngram.py"
vroot=pathlib.Path(importlib.util.find_spec("vllm").origin).parent
protocol=vroot/"entrypoints/openai/chat_completion/protocol.py"
params=SamplingParams(presence_penalty=1.0,frequency_penalty=0.005,repetition_penalty=1.0,extra_args={"no_repeat_ngram_size":100,"debug":False})
processor=MinerULogitsProcessor(None,torch.device("cpu"),False)
processor.update_state(types.SimpleNamespace(removed=[],added=[(0,params,[],[1]*100)],moved=[]))
logits=torch.zeros((1,8),device="cpu");after=processor.apply(logits)
assert torch.isneginf(after[0,1]) and torch.isfinite(after[0,0])
print(json.dumps({"test_scope":"CPU only official processor routing and ngram100 functional check; no model inference/parameters changed","processor_class":processor.__class__.__name__,"processor_source_SHA256":hashlib.sha256(source.read_bytes()).hexdigest(),"OpenAI_protocol_SHA256":hashlib.sha256(protocol.read_bytes()).hexdigest(),"routing_lines":[{"line":i,"text":s} for i,s in enumerate(protocol.read_text().splitlines(),1) if any(k in s for k in ["presence_penalty=self.presence_penalty","frequency_penalty=self.frequency_penalty","extra_args=", "vllm_xargs"])],"actual_params":{"presence_penalty":params.presence_penalty,"frequency_penalty":params.frequency_penalty,"repetition_penalty":params.repetition_penalty,"extra_args":params.extra_args},"ngram100_next_repeat_banned":bool(torch.isneginf(after[0,1])),"other_token_unchanged":bool(torch.isfinite(after[0,0]))},indent=2))
