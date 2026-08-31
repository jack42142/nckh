import os
import torch
import traceback
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

app = FastAPI(title="Qwen3 Local Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_PATH = r"C:\Users\thien\Downloads\nghiên cứu khoa học\nckh\Ai_intergration\Qwen3-8B\snapshots\b968826d9c46dd6066d109eabc6255188de91218"
OFFLOAD_FOLDER = "./offload_cache"

os.makedirs(OFFLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------------------------
# 0. Hardware Check
# ---------------------------------------------------------------------------
if not torch.cuda.is_available():
    print("⚠️ CUDA không khả dụng, hệ thống sẽ chạy hoàn toàn trên CPU.")
else:
    print(f"[0/2] Phát hiện GPU: {torch.cuda.get_device_name(0)}")
    print(f"      CUDA Arch Capability: {torch.cuda.get_device_capability(0)}")

# ---------------------------------------------------------------------------
# 1. Load Tokenizer & Fix Special Tokens
# ---------------------------------------------------------------------------
print("[1/2] Đang nạp Tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    local_files_only=True,
    trust_remote_code=True
)

# Fix pad_token_id mapping to prevent special token tensor comparison errors
if tokenizer.pad_token_id is None:
    tokenizer.pad_token = tokenizer.eos_token

# ---------------------------------------------------------------------------
# 2. Load Model
# ---------------------------------------------------------------------------
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True
)

print("[2/2] Đang nạp model...")

try:
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto",
        llm_int8_enable_fp32_cpu_offload=True,
        offload_folder=OFFLOAD_FOLDER,
        low_cpu_mem_usage=True,
        local_files_only=True,
        trust_remote_code=True
    )
    print("=> Nạp thành công mô hình 4-bit!")

except Exception as e:
    print(f"⚠️ Nạp 4-bit thất bại, nạp bfloat16 gốc: {e}")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        offload_folder=OFFLOAD_FOLDER,
        low_cpu_mem_usage=True,
        local_files_only=True,
        trust_remote_code=True
    )
    print("=> Nạp thành công mô hình bfloat16!")

# ---------------------------------------------------------------------------
# 3. API Schema & Endpoint
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7

@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        messages = [{"role": "user", "content": req.prompt}]
        text = tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
        
        main_device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model_inputs = tokenizer([text], return_tensors="pt").to(main_device)
        
        with torch.no_grad():
            generated_ids = model.generate(
                input_ids=model_inputs.input_ids,
                attention_mask=model_inputs.attention_mask,
                max_new_tokens=req.max_tokens,
                do_sample=True if req.temperature > 0 else False,
                temperature=req.temperature if req.temperature > 0 else None,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        
        generated_ids = [
            output_ids[len(input_ids):] 
            for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        
        raw_response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
        # Lọc bỏ thẻ suy luận <think> nếu có
        clean_response = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL).strip()
        
        return {"response": clean_response}

    except Exception as e:
        print("\n❌ Lỗi khi thực thi API:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)