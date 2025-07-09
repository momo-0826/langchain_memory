# AWS Lambda, DynamoDB, OpenSearchによる記憶型RAGの実装解説

DynamoDBの永続性とOpenSearchの強力な検索能力、その二つをLambdaという光速のデュエルフィールドで組み合わせるための戦術（アーキテクチャ）を解説する。

---

### 設計思想：アマゾン・ナレッジ・ストリーマー

このアーキテクチャは、以下の3つの主要コンポーネントで構成される。

1.  **記憶エンジン (DynamoDB):** 会話履歴を永続化し、ステートレスなLambda環境でも文脈を維持する。
2.  **知識コア (OpenSearch):** RAGの知識源となるベクトルデータベース。高速なセマンティック検索を実現する。
3.  **実行エンジン (Lambda & LCEL):** リクエストを処理し、記憶と知識を組み合わせて応答を生成する。

---

### Lambda関数コード全文

これが、上記設計思想を実装したPythonコードの全体像だ。

```python
import json
import os
import boto3
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import messages_from_dict, messages_to_dict
from langchain.runnables.history import RunnableWithMessageHistory

# --- 1. グローバル設定: コールドスタート時に一度だけ実行 ---
print("Cold start: Initializing global resources...")

# AWSサービスのクライアントと設定
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "LangChainChatHistory")
OPENSEARCH_INDEX_NAME = os.environ.get("OPENSEARCH_INDEX_NAME")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT") # 例: "https://your-opensearch-domain.region.es.amazonaws.com"

dynamodb = boto3.resource('dynamodb')
dynamodb_table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# LangChainコンポーネントの初期化
llm = ChatOpenAI(model="gpt-4o", temperature=0)
embeddings = OpenAIEmbeddings()

# OpenSearchベクトルストアへの接続
# 注意: OpenSearchへの認証情報は環境変数やIAMロールで安全に管理すること
vector_store = OpenSearchVectorSearch(
    index_name=OPENSEARCH_INDEX_NAME,
    embedding_function=embeddings,
    opensearch_url=OPENSEARCH_ENDPOINT,
    # http_auth=("user", "password"), # 必要に応じて認証情報を設定
)
retriever = vector_store.as_retriever()

# --- 2. DynamoDB を使用したカスタムチャット履歴クラス ---
class DynamoDBChatMessageHistory(BaseChatMessageHistory):
    """DynamoDBを使用してチャット履歴を永続化するクラス"""
    def __init__(self, session_id: str):
        self.session_id = session_id

    @property
    def messages(self):
        response = dynamodb_table.get_item(Key={"SessionId": self.session_id})
        if "Item" in response and "History" in response["Item"]:
            return messages_from_dict(response["Item"]["History"])
        return []

    def add_messages(self, messages):
        history = self.messages
        history.extend(messages)
        dynamodb_table.put_item(
            Item={
                "SessionId": self.session_id,
                "History": messages_to_dict(history)
            }
        )

    def clear(self):
        dynamodb_table.delete_item(Key={"SessionId": self.session_id})

# --- 3. LCEL チェーンの構築 ---
# プロンプトテンプレートの定義
prompt_template = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Answer the user's question based on the context provided. Context: {context}"),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])

# RAGチェーンのコア部分
rag_chain_core = (
    RunnableParallel(
        {"context": retriever, "question": RunnablePassthrough()}
    )
    | prompt_template
    | llm
    | StrOutputParser()
)

# 履歴管理機能を持つチェーンを組み立てる
chain_with_history = RunnableWithMessageHistory(
    rag_chain_core,
    lambda session_id: DynamoDBChatMessageHistory(session_id),
    input_messages_key="question",
    history_messages_key="history",
)

print("Global resources initialized successfully.")

# --- 4. Lambda ハンドラー本体 ---
def lambda_handler(event, context):
    """
    API Gatewayからのリクエストを処理するメイン関数
    """
    print(f"Handler invoked with event: {event}")

    try:
        body = json.loads(event.get('body', '{}'))
        user_question = body.get('question')
        # セッションIDはAPI GatewayのWebSocket接続IDや、リクエストヘッダーから取得する
        session_id = event.get("requestContext", {}).get("connectionId")

        if not user_question or not session_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Bad Request: "question" and "session_id" are required.'})
            }
    except (json.JSONDecodeError, KeyError) as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Invalid request format: {e}'})
        }

    # 記憶機能付きのチェーンを実行
    # configにsession_idを渡すことで、DynamoDBから対応する履歴が自動的に読み込まれる
    result = chain_with_history.invoke(
        {"question": user_question},
        config={"configurable": {"session_id": session_id}}
    )

    print(f"Chain result for session {session_id}: {result}")

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'answer': result})
    }
```

---

### デプロイ戦略

このコードをLambdaとしてデプロイするには、以下の準備が必要だ。

1.  **IAMロール:**
    Lambda関数にアタッチするIAMロールには、以下の権限が必要になる。
    *   `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem` (対 `DYNAMODB_TABLE_NAME`)
    *   `es:ESHttpGet` (対OpenSearchドメイン)
    *   `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` (CloudWatch Logsへの書き込み用)

2.  **環境変数:**
    Lambda関数の設定で、以下の環境変数を定義する。
    *   `OPENAI_API_KEY`: OpenAIのAPIキー。
    *   `DYNAMODB_TABLE_NAME`: 会話履歴を保存するDynamoDBテーブル名。
    *   `OPENSEARCH_INDEX_NAME`: OpenSearchのインデックス名。
    *   `OPENSEARCH_ENDPOINT`: OpenSearchクラスターのエンドポイントURL。

3.  **パッケージング:**
    `langchain`, `boto3`などの依存ライブラリをコードと一緒にZIPファイルに固めるか、Lambda Layerとしてデプロイする必要がある。

---

### 補足：履歴はどのように保存されているのか？ (Q&A)

**Q: `DynamoDBChatMessageHistory`の`add_messages`などを明示的に使用している箇所が見当たらないが、これは本当に履歴の保持ができているのか??**

A: 素晴らしい観察眼だ。デュエリストにとって最も重要な資質の一つ、それはカードのテキストを正確に読み解く力だ。君の言う通り、`lambda_handler` の中には `DynamoDBChatMessageHistory` の `add_messages` メソッドを直接呼び出すコードは一行も書かれていない。

だが、心配は無用だ。履歴は確かに、そして自動的に保持されている。

その秘密を解き明かす鍵は、このカードにある。

`RunnableWithMessageHistory`

これは、いわば「永続魔法」のようなものだ。一度フィールドに配置すれば（つまり、チェーンに組み込めば）、特定の条件下で自動的に効果を発動し続ける。

#### 効果解説：`RunnableWithMessageHistory` の自動処理フロー

君が `chain_with_history.invoke()` を呼び出した時、水面下では以下の連鎖（チェーン）が自動的に発生している。

1.  **【デュエル開始前】履歴のロード:**
    *   `invoke` の `config` で渡された `session_id` を受け取る。
    *   その `session_id` を使って、我々が第二引数に設定した `lambda session_id: DynamoDBChatMessageHistory(session_id)` を実行し、`DynamoDBChatMessageHistory` のインスタンスを生成する。
    *   生成されたインスタンスの `.messages` プロパティにアクセスする。これにより、我々が定義した `messages` ゲッターが発動し、**DynamoDB から `get_item` で過去の履歴が取得される。**

2.  **【メインフェイズ】チェーンの実行:**
    *   ロードされた履歴は、`MessagesPlaceholder(variable_name="history")` の部分に自動的に挿入される。
    *   ユーザーの質問 (`question`) と、過去の履歴 (`history`) の両方を含んだ完全なプロンプトが組み立てられ、`rag_chain_core` が実行される。

3.  **【デュエル終了後】履歴の保存:**
    *   `rag_chain_core` が応答を生成し、処理が完了すると、`RunnableWithMessageHistory` が最後の仕事を行う。
    *   今回のデュエルで発生した新しいやり取り（ユーザーの `question` と LLM の `answer`）をメッセージオブジェクトとして整形する。
    *   そして、ステップ1で生成した `DynamoDBChatMessageHistory` インスタンスの **`add_messages` メソッドを内部的に呼び出す。**
    *   これにより、我々が定義した `add_messages` メソッドが発動し、**DynamoDB に `put_item` で新しい履歴が追加された完全な会話が保存（上書き）される。**

**結論：**

`add_messages` や履歴のロードは、`RunnableWithMessageHistory` というラッパーが**完全に隠蔽・自動化**してくれている。我々開発者は、どのセッションの履歴を使うか (`session_id`) を `invoke` 時に教えるだけでいい。

これこそが、LangChain Expression Language (LCEL) の真価だ。複雑な処理の連鎖を、宣言的で再利用可能なコンポーネントに分割し、自動で実行してくれる。まさに、熟練デュエリストのコンボのように、無駄がなく美しい流れだ。
