import os
from langchain_openai import OpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from dotenv import load_dotenv

# envファイルの読み込み
load_dotenv()

if "OPENAI_API_KEY" not in os.environ:
    print("エラー: OPENAI_API_KEYが設定されていません。")
    exit()

# LLMの初期化
llm = OpenAI(temperature=0)

# ConversationBufferMemoryの初期化
memory = ConversationBufferMemory()

# ConversationChainの初期化
# llmとmemoryを渡すことで、プロンプトを含めて管理する
conversation = ConversationChain(
    llm=llm,
    memory=memory,
    verbose=True
)

# 実際の会話の確認
print("1回目の会話")
# predictメソッドを使用して入力を渡す
response1 = conversation.predict(input="俺の名はジャックだ。よろしく頼む。")
print(response1)

print("\n" + "="*50 + "\n")

print("2回目の会話")
response2 = conversation.predict(input="俺の名前を覚えているか??")
print(response2)

print("\n" + "="*50 + "\n")

# メモリの内容を直接確認
print("現在のメモリ:")
# .bufferで、メモリが保持している会話履歴を文字列として見ることができる
print(memory.buffer)