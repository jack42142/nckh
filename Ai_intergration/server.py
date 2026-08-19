import os
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

app = FastAPI(title="Qwen3 Local Server")

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đường dẫn snapshot local
MODEL_PATH = r"C:\Users\thien\Downloads\nghiên cứu khoa học\nckh\Ai_intergration\Qwen3-8B\snapshots\b968826d9c46dd6066d109eabc6255188de91218"

print("[1/2] Đang nạp Tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    local_files_only=True,
    trust_remote_code=True
)

# Cấu hình nén 4-bit NF4 chuẩn hóa
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,  # Sửa từ float16 sang bfloat16 cho Qwen
    bnb_4bit_use_double_quant=True
)

print("[2/2] Đang nạp model lên GPU...")
try:
    # Thử nạp ở dạng 4-bit
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto",
        low_cpu_mem_usage=True,              # Sửa lỗi mapping weights từ local snapshot
        local_files_only=True,
        trust_remote_code=True
    )
    print("=> Nạp thành công mô hình dạng 4-bit NF4 lên GPU!")
except Exception as e:
    print(f"⚠️ Nạp 4-bit thất bại ({e}). Tự động chuyển sang nạp bfloat16 gốc...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
        local_files_only=True,
        trust_remote_code=True
    )
    print("=> Nạp thành công mô hình dạng bfloat16 gốc!")

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
        
        # Đảm bảo tensor được gửi đúng thiết bị của model
        model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
        
        with torch.no_grad():
            generated_ids = model.generate(
                **model_inputs,
                max_new_tokens=req.max_tokens,
                do_sample=True if req.temperature > 0 else False,
                temperature=req.temperature
            )
        
        generated_ids = [
            output_ids[len(input_ids):] 
            for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)