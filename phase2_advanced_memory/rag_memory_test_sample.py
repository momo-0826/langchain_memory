import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# OpenAIのAPIキーが設定されていることを確認
if "OPENAI_API_KEY" not in os.environ:
    print("エラー: OPENAI_API_KEYが設定されていません。")
    exit()

# LLMとEmbeddingモデルの初期化
llm = ChatOpenAI(temperature=0)
embeddings = OpenAIEmbeddings()

# --- RAGメモリのコアロジック ---

# 1. 会話履歴を保存するVectorStoreの準備
# ここではFAISSをインメモリで使用するが、実際には永続化されたVectorStoreを使う
# FAISSは、ベクトル検索を行うためのライブラリ
vectorstore = FAISS.from_texts([""], embeddings) # 初期化のために空のテキストを一つ追加

# 2. Retrieverの準備
# VectorStoreから関連情報を検索するためのRetriever
retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) # 関連性の高い上位3件を検索

# 3. 会話履歴を管理する関数
# RunnableWithMessageHistoryに渡すための関数
# ここでは、ChatMessageHistoryに加えて、VectorStoreにも履歴を保存する
def get_session_history_with_rag(session_id: str):
    if session_id not in st.session_state: # Streamlitのセッション状態を想定
        st.session_state[session_id] = ChatMessageHistory()
        st.session_state[f"{session_id}_vectorstore"] = FAISS.from_texts([""], embeddings)
    return st.session_state[session_id]

# 4. プロンプトテンプレートの作成
# 関連する過去の会話（retrieved_history）をプロンプトに含める
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful AI assistant. Use the following retrieved conversation history to answer the question:\n\n{retrieved_history}"),
        MessagesPlaceholder(variable_name="history"), # これまでの会話履歴（短期的）
        ("human", "{input}"),
    ]
)

# 5. チェーンの定義
# RunnablePassthroughでretrieved_historyをプロンプトに渡す
# RunnableWithMessageHistoryの前に、Retrieverで関連履歴を検索するステップを追加
chain = (
    RunnablePassthrough.assign(
        retrieved_history=lambda x: retriever.invoke(x["input"]) # 入力に基づいて関連履歴を検索
    )
    | prompt
    | llm
    | StrOutputParser()
)

# 6. RunnableWithMessageHistoryの準備
# ここでは、ChatMessageHistoryに加えて、VectorStoreにも履歴を保存するカスタム関数を渡す
# ただし、RunnableWithMessageHistoryはChatMessageHistoryオブジェクトを期待するため、
# VectorStoreへの保存は別途フックする必要がある。
# 簡略化のため、ここではChatMessageHistoryに保存しつつ、
# 応答後にVectorStoreにも追加する形にする。

# 実際のRunnableWithMessageHistoryのラッパー
with_rag_memory = RunnableWithMessageHistory(
    chain,
    get_session_history_with_rag, # Streamlitのst.session_stateを想定した関数
    input_messages_key="input",
    history_messages_key="history",
)

# --- 会話の実行 ---
# この部分はStreamlitアプリを想定しているため、ここでは簡略化して直接実行する

# 注意: このスクリプトはStreamlitのst.session_stateを想定しているため、
# そのまま実行するとエラーになる可能性があります。
# 動作確認のためには、st.session_stateを模倣するか、Streamlitアプリとして実行する必要があります。

# 簡略化されたst.session_stateの模倣
class MockSessionState:
    def __init__(self):
        self.data = {}
    def __contains__(self, key):
        return key in self.data
    def __getitem__(self, key):
        return self.data[key]
    def __setitem__(self, key, value):
        self.data[key] = value

st = MockSessionState() # st.session_stateの代わりにこれを使う

# セッションIDを固定
SESSION_ID = "rag_session_1"

# 最初の会話
print("1回目の会話")
user_input_1 = "俺はジャック・アトラスだ。キングだ。"
response_1 = with_rag_memory.invoke(
    {"input": user_input_1},
    config={"configurable": {"session_id": SESSION_ID}},
)
print(f"User: {user_input_1}")
print(f"AI: {response_1}")

# 会話履歴をVectorStoreに追加 (RunnableWithMessageHistoryは自動でChatMessageHistoryには追加するが、VectorStoreには手動で追加する必要がある)
# 実際には、RunnableWithMessageHistoryのコールバックなどで自動化する
st.data[f"{SESSION_ID}_vectorstore"].add_texts([user_input_1, response_1])

print("\n" + "="*50 + "\n")

# 2回目の会話
print("2回目の会話")
user_input_2 = "俺はキングだと言ったはずだ。覚えているか？"
response_2 = with_rag_memory.invoke(
    {"input": user_input_2},
    config={"configurable": {"session_id": SESSION_ID}},
)
print(f"User: {user_input_2}")
print(f"AI: {response_2}")

st.data[f"{SESSION_ID}_vectorstore"].add_texts([user_input_2, response_2])

print("\n" + "="*50 + "\n")

# 3回目の会話 (関連情報を検索して応答するか確認)
print("3回目の会話")
user_input_3 = "俺の肩書きは何だった？"
response_3 = with_rag_memory.invoke(
    {"input": user_input_3},
    config={"configurable": {"session_id": SESSION_ID}},
)
print(f"User: {user_input_3}")
print(f"AI: {response_3}")

st.data[f"{SESSION_ID}_vectorstore"].add_texts([user_input_3, response_3])

print("\n" + "="*50 + "\n")

# VectorStoreの内容を直接確認 (デバッグ用)
print("VectorStoreに保存されたテキスト:")
# FAISSは直接テキストを取り出すメソッドがないため、ここでは簡略化
# 実際には、VectorStoreの内部構造を直接見ることは稀
# print(st.data[f"{SESSION_ID}_vectorstore"].docstore._dict)
