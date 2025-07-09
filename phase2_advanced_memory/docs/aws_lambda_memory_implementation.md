# AWS Lambda での記憶保持型 RAG チェーンの実装

AWS Lambda のようなサーバーレス環境で、会話の記憶を保持する RAG チェーンを実装するには、特有の制約とアーキテクチャを理解する必要があります。

グローバル変数に会話履歴を保存するような単純なアプローチは、Lambda のステートレスな性質上、機能しません。

---

### Lambda の壁：ステートレスという原則

まず、なぜグローバルな辞書（例：`history_store = {}`）が使えないのかを理解することが重要です。

- **実行環境の寿命**: Lambda 関数はリクエストごとに新しい実行環境（マイクロコンテナ）で起動される可能性があり、処理が完了するとその環境は破棄されることがあります。
- **ステートレス**: Lambda の基本原則は「ステートレス」です。あるリクエストでメモリに保存したデータは、次のリクエストでは存在しないと考えるべきです。
- **並列実行**: 同時に多数のリクエストが発生すると、Lambda は複数の実行環境を並列で起動します。各環境は独立しており、メモリ空間を共有しません。

このため、Python のグローバル辞書に保存された履歴は、次のリクエストでは失われてしまいます。

### 解決策：記憶の外部化（Externalize State）

この問題を解決する唯一の戦略は、**記憶を Lambda 関数の外部にある、永続的なストレージに保存する**ことです。

Lambda 関数自体は短期的な処理（デュエル）に集中し、記憶（戦績）は外部のデータベースに記録します。この外部ストレージとして、以下の AWS サービスが適しています。

- **Amazon DynamoDB**: キーバリューストア。セッション ID をキーに会話履歴を保存するのに最適で、Lambda との相性も抜群です。**最も一般的な選択肢**と言えます。
- **Amazon ElastiCache (Redis など)**: 高速なインメモリデータベース。
- **Amazon S3**: オブジェクトストレージ。会話ターンごとにファイルを書き出すことも可能ですが、一般的に DynamoDB より低速で複雑になります。

---

### `handler` 関数への実装 (DynamoDB 利用例)

#### ステップ 1：DynamoDB 対応の`ChatMessageHistory`クラスを作成

まず、`BaseChatMessageHistory` を継承し、DynamoDB との通信をカプセル化したクラスを作成します。

```python
import boto3
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import messages_from_dict, messages_to_dict

# DynamoDBクライアント
dynamodb = boto3.resource('dynamodb')
# 使用するテーブル名を決めておく
TABLE_NAME = 'LangChainChatHistory'
table = dynamodb.Table(TABLE_NAME)

class DynamoDBChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id: str):
        self.session_id = session_id

    @property
    def messages(self):
        """DynamoDBから履歴を取得"""
        response = table.get_item(Key={"SessionId": self.session_id})
        if "Item" in response and "History" in response["Item"]:
            return messages_from_dict(response["Item"]["History"])
        return []

    @messages.setter
    def messages(self, messages):
        """このセッターは直接使わず、add_messages経由で更新する"""
        pass

    def add_messages(self, messages):
        """DynamoDBに履歴を追加（上書き）"""
        history = self.messages
        history.extend(messages)
        table.put_item(
            Item={
                "SessionId": self.session_id,
                "History": messages_to_dict(history)
            }
        )

    def clear(self):
        """DynamoDBから履歴を削除"""
        table.delete_item(Key={"SessionId": self.session_id})
```

#### ステップ 2：`handler` 関数内でのチェーンの組み立て

次に、この `DynamoDBChatMessageHistory` を使って、Lambda の `handler` 関数を組み立てます。

```python
# retrieverやllm、コアチェーンはhandlerの外で定義し、ウォームスタート時に再利用する
rag_core_chain = ...

def get_session_history(session_id: str) -> DynamoDBChatMessageHistory:
    """リクエストごとに、DynamoDBの履歴クラスのインスタンスを返す"""
    return DynamoDBChatMessageHistory(session_id)

with_rag_history = RunnableWithMessageHistory(
    rag_core_chain,
    get_session_history,
    input_messages_key="prompt",
    history_messages_key="history",
)

# --- Lambdaハンドラ本体 ---
def handler(event, context):
    # 1. リクエストからユーザー入力とセッションIDを取得
    body = json.loads(event.get("body", "{}"))
    user_prompt = body.get("prompt")
    session_id = event.get("requestContext", {}).get("connectionId") # 例: WebSocket

    if not user_prompt or not session_id:
        return {"statusCode": 400, "body": "prompt and session_id are required"}

    # 2. 記憶機能付きのチェーンを呼び出す
    response = with_rag_history.invoke(
        {"prompt": user_prompt},
        config={"configurable": {"session_id": session_id}}
    )

    # 3. 応答を返す
    return {
        "statusCode": 200,
        "body": json.dumps({"response": response})
    }
```

### RAG のベクトルストアについて

RAG で使う`retriever`（ベクトルストア）も同様に、永続化が必要です。

- **インデックスファイルの置き場所**: Faiss などのベクトルインデックスファイルは、**S3**に保存します。
- **読み込み戦略**: Lambda 関数の**コールドスタート時**（最初の実行時）に、S3 からインデックスファイルをダウンロードし、Lambda の `/tmp` ディレクトリ（書き込み可能）に展開します。そして、そのファイルを読み込んで `retriever` を初期化します。
- **キャッシュ**: 初期化した `retriever` は、**`handler` 関数の外側のグローバル変数**に格納します。これにより、**ウォームスタート時**（同じ実行環境が再利用される時）には、この重い初期化処理をスキップでき、パフォーマンスが大幅に向上します。
