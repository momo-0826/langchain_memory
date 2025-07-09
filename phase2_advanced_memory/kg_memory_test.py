import os
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationChain
from langchain_community.memory.kg import ConversationKGMemory
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv

# envファイルの読み込み
load_dotenv()

if "OPENAI_API_KEY" not in os.environ:
    print("エラー: OPENAI_API_KEYが設定されていません。")
    exit()

# LLMの初期化
llm = ChatOpenAI(temperature=0)

# ConversationKGMemoryの初期化
# llmを渡してLLMがエンティティと関係性を抽出するようにする
memory = ConversationKGMemory(llm)

# プロンプトテンプレートの作成
# KGMemoryは抽出したナレッジグラフをkgという変数名でプロンプトに挿入する
_DEFAULT_TEMPLATE = """
以下は人間とAIの友好的な会話です。AIはそのコンテキストから多くの具体的な情報を提供します。もし質問の答えを知らない場合は正直に知りませんと答えます。

現在の会話：
{history}
エンティティ：
{entities}
ナレッジグラフ：
{kg}
人間：{input}
AI：
"""

# プロンプトの設定
prompt = PromptTemplate(
    input_variables=["history", "entities", "kg", "input"],
    template=_DEFAULT_TEMPLATE
)

# ConversationChainの構築
conversation = ConversationChain(
    llm=llm,
    memory=memory,
    prompt=prompt,
    verbose=True
)

print(conversation.predict(input="こんにちは、私の名前はジャックです。"))
print(conversation.predict(input="私の名前は何ですか？"))
print(conversation.predict(input="私はネオ・ドミノシティに住んでいます。"))
print(conversation.predict(input="私はどこに住んでいますか？"))
print(conversation.predict(input="私のお気に入りのカードはレッドデーモンズ・ドラゴンです。"))
print(conversation.predict(input="私のお気に入りのカードは何ですか？"))
print(conversation.predict(input="私のお気に入りのコーヒー豆はブルーアイズマウンテンです。"))
print(conversation.predict(input="私のお気に入りのコーヒー豆は何ですか？"))