import streamlit as st
import os
import faiss
import torch
from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# 设置环境变量
os.environ["CUDA_VISIBLE_DEVICES"] = "6,7"

# 路径设置
tokenizer_path = "../BAAI_bge-m3"
gen_model_path = "../GLM-4-9B-Chat"

# 检查CUDA设备的可用性
assert torch.cuda.device_count() > 1, "至少需要两个CUDA设备"
assert torch.cuda.is_available(), "CUDA设备不可用"

# 设置设备
device_query = torch.device("cuda:1")  # 使用第二个可用的设备
device_gen = torch.device("cuda:0")    # 使用第一个可用的设备

# 加载tokenizer和模型
tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
model = AutoModel.from_pretrained(tokenizer_path)

# 加载生成模型和tokenizer
gen_tokenizer = AutoTokenizer.from_pretrained(gen_model_path, trust_remote_code=True)
gen_model = AutoModelForCausalLM.from_pretrained(gen_model_path, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True, trust_remote_code=True)

# 确保模型加载正确后再移动到设备
model = model.to(device_query)
model = torch.nn.DataParallel(model, device_ids=[1])

gen_model = gen_model.to(device_gen)
gen_model = torch.nn.DataParallel(gen_model, device_ids=[0]).eval()

# 固定随机种子
torch.manual_seed(42)

# 加载FAISS索引
index_path = "../RAG/faiss_index/embedding.index"
index = faiss.read_index(index_path)

# 加载条目和文件名映射
entries = []
with open("../RAG/faiss_index/entries.txt", "r", encoding="utf-8") as f:
    for line in f:
        file_path, entry = line.strip().split('\t')
        # 去掉路径中的../reference
        file_path = file_path.replace("../reference_book/", "")
        entries.append((file_path, entry))


# 函数：生成答案
def generate_answer(context, query):
    input_text = f"法律问题:{query}\n回答可能会用到的参考文献:{context}\n"
    inputs = gen_tokenizer(input_text, return_tensors="pt", truncation=True, max_length=gen_tokenizer.model_max_length).to(device_gen)
    gen_kwargs = {"max_length": 2500, "do_sample": True, "top_k": 1}

    with torch.no_grad():
        outputs = gen_model.module.generate(**inputs, **gen_kwargs)
        answer = gen_tokenizer.decode(outputs[0], skip_special_tokens=True)
    # 去除input_text相关内容
    answer = answer.replace(input_text, "").strip()
    return answer

# 函数：检索最相近的条目
def retrieve_similar_entries(query, k=3):
    inputs = tokenizer(query, return_tensors="pt", truncation=True, max_length=tokenizer.model_max_length).to(device_query)
    with torch.no_grad():
        query_emb = model(**inputs).last_hidden_state.mean(dim=1).cpu().numpy()
    
    _, indices = index.search(query_emb, k)
    return [(entries[idx][0], entries[idx][1]) for idx in indices[0]]

# Streamlit界面
st.title("法律咨询生成器")
query = st.text_input("请输入您的法律问题:")

if query:
    similar_entries = retrieve_similar_entries(query)
    context = "\n".join([entry for _, entry in similar_entries])
    
    st.sidebar.title("参考文献")
    for file_path, entry in similar_entries:
        st.sidebar.write(f"文件: {file_path}\n条目: {entry}\n")

    answer = generate_answer(context, query)
    st.write("回答:")
    st.write(answer)