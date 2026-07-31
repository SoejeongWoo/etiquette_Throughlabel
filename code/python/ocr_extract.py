# 라벨 이미지 1장 -> 추출 텍스트. VARCO-VISION-2.0-1.7B-OCR 기반.
# 코랩(GPU) 비교 테스트에서 EasyOCR/DeepSeek-OCR 대비 채택됨 — notebooks/ocr_model_comparison.ipynb 참고.
# 사용법: python code/python/ocr_extract.py <이미지 경로>
# 주의: GPU 없이 CPU로 돌리면 이미지 1장에 수 분 걸릴 수 있음.
import sys

import torch
from PIL import Image
from transformers import AutoProcessor, LlavaOnevisionForConditionalGeneration

MODEL_NAME = "NCSOFT/VARCO-VISION-2.0-1.7B-OCR"
MAX_NEW_TOKENS = 4096  # 글자마다 <bbox> 좌표 4개가 붙는 출력 형식이라 토큰을 많이 먹음. 너무 작으면 전성분 도달 전에 잘림.
TARGET_SIZE = 2304  # 모델 권장 최소 해상도(긴 변 기준)


def load_image(image_path):
    # PIL은 Windows 비ASCII 경로(예: ©)도 문제없이 읽음.
    image = Image.open(image_path).convert("RGB")
    w, h = image.size
    if max(w, h) < TARGET_SIZE:
        scale = TARGET_SIZE / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)))
    return image


def main():
    if len(sys.argv) != 2:
        print("사용법: python ocr_extract.py <이미지 경로>")
        sys.exit(1)

    image_path = sys.argv[1]
    image = load_image(image_path)

    model = LlavaOnevisionForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,
        attn_implementation="sdpa",
        device_map="auto",
    )
    processor = AutoProcessor.from_pretrained(MODEL_NAME)

    conversation = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "<ocr>"},
            ],
        },
    ]
    inputs = processor.apply_chat_template(
        conversation,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device, torch.float16)

    generate_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
    trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generate_ids)]
    output_len = trimmed[0].shape[0]
    if output_len >= MAX_NEW_TOKENS:
        print(f"경고: 생성 토큰 수({output_len})가 MAX_NEW_TOKENS에 도달 — 잘렸을 수 있음\n")

    output = processor.decode(trimmed[0], skip_special_tokens=False)
    print(output)


if __name__ == "__main__":
    main()
