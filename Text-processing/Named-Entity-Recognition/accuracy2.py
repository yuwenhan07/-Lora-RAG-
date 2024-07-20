import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import os
import argparse

os.environ["CUDA_VISIBLE_DEVICES"] = "1"

def predict(messages, model, tokenizer):
    device = "cuda"

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text], return_tensors="pt").to(device)

    generated_ids = model.generate(model_inputs.input_ids, max_new_tokens=512)
    generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)]
    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    return response

def parse_response(response):
    try:
        response_data = eval(response)
        if isinstance(response_data, list):
            return response_data
        else:
            return [response_data]
    except:
        return []

def format_response(parsed_response):
    formatted_response = []
    for entity in ["犯罪嫌疑人", "受害人", "被盗货币", "物品价值", "盗窃获利", "被盗物品", "作案工具", "时间", "地点", "组织机构"]:
        entity_values = [e["text"] for e in parsed_response if e["label"] == entity]
        formatted_response.append(f"{entity}: {entity_values[0] if entity_values else 'None'}")
    return "; ".join(formatted_response)

def main(load_checkpoint):
    # 加载原下载路径的tokenizer和model
    tokenizer = AutoTokenizer.from_pretrained("../../GLM-4-9B-Chat", use_fast=False, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained("../../GLM-4-9B-Chat", device_map="auto", torch_dtype=torch.bfloat16, trust_remote_code=True)

    if load_checkpoint:
        # 加载训练好的Lora模型，将下面的checkpointXXX替换为实际的checkpoint文件名名称
        model = PeftModel.from_pretrained(model, model_id="../../finetune/output/NER/checkpoint-1100")

    # 从指定路径加载测试数据
    data_path = "/home/yuwenhan/law-LLM/buaa&zgzf/Text-processing/Named-Entity-Recognition/data/data.json"
    with open(data_path, 'r', encoding='utf-8') as f:
        test_data = json.load(f)

    results = []

    for test_instance in test_data:
        instruction = "你是一个法律命名实体识别的专家。请根据给定文本，从以下十个方面（犯罪嫌疑人、受害人、被盗货币、物品价值、盗窃获利、被盗物品、作案工具、时间、地点、组织机构）提取文中的实体，没有用None表示，并按照以下格式返回结果：[犯罪嫌疑人: xxx; 受害人： xxx; 被盗货币： None; ……]"
        input_value = test_instance["context"]

        messages = [
            {"role": "system", "content": f"{instruction}"},
            {"role": "user", "content": f"{input_value}"}
        ]

        response = predict(messages, model, tokenizer)
        
        # 将实际标签格式化为字符串
        expected_response = []
        for entity in ["犯罪嫌疑人", "受害人", "被盗货币", "物品价值", "盗窃获利", "被盗物品", "作案工具", "时间", "地点", "组织机构"]:
            entity_values = [e["text"] for e in test_instance["entities"] if e["label"] == entity]
            expected_response.append(f"{entity}: {entity_values[0] if entity_values else 'None'}")
        expected_response = "; ".join(expected_response)
        
        # 解析和格式化预测结果
        parsed_response = parse_response(response)
        formatted_response = format_response(parsed_response)

        results.append({
            "input": input_value,
            "predicted": formatted_response,
            "expected": expected_response
        })

    # 将结果保存为JSON文件
    with open("./data/results_origin.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    # 计算正确率
    correct_predictions = sum(1 for result in results if result["predicted"] == result["expected"])
    total_predictions = len(results)
    accuracy = correct_predictions / total_predictions
    print(f"Accuracy: {accuracy * 100:.2f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--load_checkpoint", action="store_true", help="Whether to load a trained LoRA checkpoint")
    args = parser.parse_args()

    main(args.load_checkpoint)