[Model Ai]
https://huggingface.co/Qwen/Qwen3-8B

## 🐳 Docker Image

Image dự án đã được lưu trữ tại GitHub Container Registry:

```bash
# Đăng nhập GHCR
echo $CR_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Tải Image về
docker pull ghcr.io/YOUR_USERNAME/qwen-airllm:v1

# Chạy Container
docker run --gpus all -d -p 8000:8000 ghcr.io/YOUR_USERNAME/qwen-airllm:v1