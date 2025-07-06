import os
from langchain_openai.chat_models.base import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferMemory
from dotenv import load_dotenv

# envファイル読み込み
load_dotenv()

if "OPENAI_API_KEY" not in os.environ:
    print("エラー: OPENAI_API_KEYが設定されていません。")
    exit()

# LLMの初期化を行う
llm = ChatOpenAI(temperature=0)

# プロンプトテンプレートの作成
# MessagePlaceholderに過去の履歴を挿入する
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant."),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)

# # LCELでチェーンを組む
# RunnablePassthrough.assignを使って入力がdict型となることを保証する
# llmの後にStrOutputParserを使用することで出力を扱いやすい文字列に変換する
runnable = (
    RunnablePassthrough.assign(
        # RunnableWithMessageHistoryが 'history' を自動的に割り当てる
        # ここでは入力（input）が後続のpromptに正しく渡されることを保証する
        input=lambda x: x["input"]
    )
    | prompt
    | llm
    | StrOutputParser()
)

# セッションごとのチャット履歴を保存するストア
# 簡単に動作確認するためにメモリ上にdictとして保存
store = {}

def get_session_history(session_id: str):
    """セッションIDに基づいてチャット履歴を取得する"""
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

# メモリ管理機能を持つRunnableを作成する
with_message_history = RunnableWithMessageHistory(
    runnable,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)

# session_idを定義
session_id = "session_1"

# 1回目の会話
print("1回目の会話")
response1 = with_message_history.invoke(
    {"input": "俺の名はジャックだ。よろしく頼む。"},
    config={"configurable": {"session_id": session_id}},
)
print(response1)

print("\n" + "="*50 + "\n")

# 2回目の会話
print("2回目の会話")
response2 = with_message_history.invoke(
    {"input": "俺の名前がわかるか??"},
    config={"configurable": {"session_id": session_id}},
)
print(response2)

print("\n" + "="*50 + "\n")

# メモリの内容を確認
print(f"セッションID:'{session_id}'の現在のメモリ：")
print(store[session_id].messages)