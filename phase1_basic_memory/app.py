import os
import streamlit as st
from langchain_openai.chat_models.base import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

# envファイルの読み込み
load_dotenv()

if "OPENAI_API_KEY" not in os.environ:
    print("エラー: OPENAI_API_KEYが設定されていません。")
    exit()

# LLMの初期化
llm = ChatOpenAI(temperature=0)

# プロンプトテンプレートの作成
prompt = ChatPromptTemplate(
    [
        ("system", "You are a helpful assistant."),
        # これまでの会話履歴を埋め込む個所を予約
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ]
)

# chainの定義
runnable = (
    RunnablePassthrough.assign(input=lambda x: x["input"])
    | prompt
    | llm
    | StrOutputParser()
)

# セッションごとにチャット履歴を保持するストア
# 今回はStreamlitのセッション状態(st.session_state)を利用して、ブラウザのセッションごとに履歴を管理する
if "history_store" not in st.session_state:
    st.session_state.history_store = {}

def get_session_hisotry(session_id: str):
    """セッションIDに基づいてチャット履歴を取得する関数"""
    if session_id not in st.session_state.history_store:
        st.session_state.history_store[session_id] = ChatMessageHistory()
    return st.session_state.history_store[session_id]

# メモリ機能を持つRunnableを作成
with_message_history = RunnableWithMessageHistory(
    runnable,
    get_session_hisotry,
    input_messages_key="input",
    history_messages_key="history",
)

st.title("メモリ機能有チャットボット")

# 今回は確認用なのでセッションIDを固定で定義しておく
SESSION_ID = "my_session"

# チャット履歴の表示
# st.session_stateに保存されている履歴を取得する
history = get_session_hisotry(SESSION_ID)
for message in history.messages:
    st.chat_message(message.type).write(message.content)

# ユーザーからの入力を受け取る
if user_input := st.chat_input("メッセージを入力してください"):
    # ユーザーの入力を表示する
    st.chat_message("human").write(user_input)

    # LLMからの応答を取得する
    response = with_message_history.invoke(
        {"input": user_input},
        config={"configurable": {"session_id": SESSION_ID}}
    )

    # LLMの応答を表示する
    st.chat_message("ai").write(response)