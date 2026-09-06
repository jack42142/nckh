"""
# ============================================================
# Credit: Code được hỗ trợ bởi Claude Code (Anthropic)
# ============================================================

"""
generate.py — Text generation với Qwen3.5-2B (multimodal, dùng text-only)

Qwen3.5-2B architecture: Qwen3_5ForConditionalGeneration (text + vision)
Trong project này chỉ dùng text → bỏ qua vision inputs.

Cú pháp:
    from generate import Generator
    gen = Generator.get()        # load 1 lần, cache lại
    answer = gen.generate(system=..., user=...)   # trả về (text, tokens, time_s)
"""

import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tắt telemetry/verbose của HF
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Cache HF về thư mục model local (giống embed.py)
os.environ.setdefault(
    "HF_HOME", str(Path(__file__).parent / "model" / "hf_cache")
)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ----------------------------- CONFIG -----------------------------

DEFAULT_LLM = (
    "./model/models--Qwen--Qwen3.5-2B/"
    "snapshots/15852e8c16360a2fea060d615a32b45270f8a8fc"
)

# Ngưỡng relevance: nếu top-1 cosine score < threshold → gọi LLM với prompt "refuse"
RELEVANCE_THRESHOLD = 0.40

MAX_NEW_TOKENS = 400
TEMPERATURE = 0.5
TOP_P = 0.9

# ----------------------------- PROMPTS -----------------------------

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI chuyên trả lời về thế giới Genshin Impact.\n"
    "Chỉ trả lời dựa trên thông tin trong phần [CONTEXT] được cung cấp bên dưới.\n"
    "Nếu thông tin trong CONTEXT không đủ hoặc không liên quan để trả lời câu hỏi, "
    'hãy nói chính xác câu: "Tôi không tìm thấy thông tin này trong dữ liệu hiện có. '
    'Bạn có thể hỏi chi tiết hơn về nhân vật, khu vực hoặc cốt truyện khác."\n'
    "Yêu cầu: trả lời bằng tiếng Việt, ngắn gọn (3-5 câu), không thêm thông tin ngoài CONTEXT."
)

REFUSE_SYSTEM = (
    "Bạn là trợ lý AI chuyên Genshin Impact. Câu hỏi của người dùng nằm ngoài phạm vi "
    "kiến thức được cung cấp. Hãy lịch sự từ chối và gợi ý hỏi về Genshin Impact."
)

USER_TEMPLATE = (
    "[CONTEXT]\n"
    "------\n"
    "{context}\n"
    "------\n"
    "\n"
    "Câu hỏi: {question}\n"
    "Trả lời:"
)


# ----------------------------- GENERATOR -----------------------------


class Generator:
    """Wrapper cho Qwen3.5-2B text generation. Singleton theo model_path."""

    _instances: dict[str, "Generator"] = {}

    def __init__(self, model_path: str):
        model_path = str(model_path)
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Không tìm thấy model tại: {model_path}\n"
                f"Kiểm tra lại đường dẫn trong generate.py:DEFAULT_LLM"
            )

        print(f"[+] Loading LLM: {model_path}")
        t0 = time.perf_counter()

        # Auto-detect device + dtype
        if torch.cuda.is_available():
            self.device = "cuda"
            self.dtype = torch.bfloat16
        else:
            self.device = "cpu"
            self.dtype = torch.float32
        print(f"    -> device={self.device}, dtype={self.dtype}")

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Load model
        # Qwen3.5-2B architecture: Qwen3_5ForConditionalGeneration
        # Mặc dù là multimodal class, transformers vẫn cho phép load
        # mà không cần vision weights nếu truyền text-only.
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=self.dtype,
            device_map=self.device,
            trust_remote_code=True,
        )
        self.model.eval()

        # Warmup: chạy generate 1 lần với input ngắn để compile/load kernel
        try:
            self._warmup()
        except Exception as e:
            print(f"    [!] Warmup skipped: {e}")

        elapsed = time.perf_counter() - t0
        print(f"[+] LLM ready in {elapsed:.1f}s")

    def _warmup(self) -> None:
        """Chạy generate 1 lần ngắn để khởi tạo CUDA kernels / cache."""
        with torch.inference_mode():
            inputs = self.tokenizer(
                "Xin chào", return_tensors="pt"
            ).to(self.device)
            self.model.generate(
                **inputs,
                max_new_tokens=8,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        print(f"    -> warmup done")

    @classmethod
    def get(cls, model_path: str = DEFAULT_LLM) -> "Generator":
        if model_path not in cls._instances:
            cls._instances[model_path] = cls(model_path)
        return cls._instances[model_path]

    def _build_messages(self, system: str, user: str) -> list[dict]:
        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

    def generate(
        self,
        system: str,
        user: str,
        max_new_tokens: int = MAX_NEW_TOKENS,
        temperature: float = TEMPERATURE,
        top_p: float = TOP_P,
    ) -> tuple[str, int, float]:
        """Sinh câu trả lời. Trả về (answer_text, new_tokens, time_seconds)."""
        messages = self._build_messages(system, user)

        # Áp chat template
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

        input_len = inputs["input_ids"].shape[1]

        do_sample = temperature > 0.0
        gen_kwargs = dict(
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        if do_sample:
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_p"] = top_p

        t0 = time.perf_counter()
        with torch.inference_mode():
            output_ids = self.model.generate(**inputs, **gen_kwargs)
        elapsed = time.perf_counter() - t0

        # Chỉ lấy phần sinh ra (bỏ prompt)
        new_ids = output_ids[0][input_len:]
        answer = self.tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        return answer, int(new_ids.shape[0]), elapsed


# ----------------------------- HELPERS -----------------------------


def build_context(chunks: list[dict], max_chars: int = 6000) -> str:
    """Ghép các chunks thành context string, cắt nếu quá dài."""
    parts: list[str] = []
    total = 0
    for i, c in enumerate(chunks, 1):
        title = c["metadata"].get("title", "")
        section = c["metadata"].get("section", "")
        header = f"[{i}] {title}"
        if section:
            header += f" — {section}"
        text = c["content"].strip()
        snippet = f"{header}\n{text}\n"
        if total + len(snippet) > max_chars:
            break
        parts.append(snippet)
        total += len(snippet)
    return "\n".join(parts) if parts else "(không có)"


def should_refuse(chunks: list[dict], threshold: float = RELEVANCE_THRESHOLD) -> bool:
    """Quyết định có nên từ chối hay không dựa trên top-1 score."""
    if not chunks:
        return True
    return chunks[0]["score"] < threshold


# ----------------------------- CLI -----------------------------


def main():
    """Quick test: load LLM, hỏi 1 câu cứng."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default="Xin chào, bạn là ai?")
    parser.add_argument("--model-path", default=DEFAULT_LLM)
    args = parser.parse_args()

    gen = Generator.get(args.model_path)
    answer, ntok, secs = gen.generate(
        system="Bạn là trợ lý AI thân thiện. Trả lời ngắn gọn bằng tiếng Việt.",
        user=args.question,
    )
    print(f"\n=== ANSWER ({ntok} tokens, {secs:.2f}s) ===\n{answer}\n")


if __name__ == "__main__":
    main()
