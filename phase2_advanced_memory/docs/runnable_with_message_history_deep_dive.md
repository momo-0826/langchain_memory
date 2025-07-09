# `RunnableWithMessageHistory` 解体新書

`RunnableWithMessageHistory`は、一見するとブラックボックスのように見えるが、その内部では明確なルールと順序に従って処理が実行されている。このドキュメントは、その内部構造を徹底的に解説するものである。

---

### `RunnableWithMessageHistory` の基本構造

このRunnableは、既存のチェーンに「記憶の管理」という追加機能を自動的に付与するための、高度なラッパー（包装材）である。これを理解するには、まずコンストラクタに渡す4つの主要な引数（パーツ）の役割を正確に把握する必要がある。

```python
chain_with_history = RunnableWithMessageHistory(
    # パーツ1: runnable (コアエンジン)
    rag_chain_core,

    # パーツ2: get_session_history (履歴調達係)
    lambda session_id: DynamoDBChatMessageHistory(session_id),

    # パーツ3: input_messages_key (ユーザー入力の識別名)
    "question",

    # パーツ4: history_messages_key (履歴注入先の識別名)
    "history",
)
```

#### 【パーツ1】`runnable` (コアエンジン)

*   **役割:** これが君のチェーンの本体、いわばエースモンスターだ。この例では `rag_chain_core` がそれに当たる。
*   **責務:** 履歴のことは一切関知しない。ただ、`input_messages_key`（質問）と `history_messages_key`（履歴）を含む辞書を受け取り、応答を返すことだけに集中する。この「関心の分離」が、再利用性の高いクリーンな設計の鍵だ。

#### 【パーツ2】`get_session_history` (履歴調達係)

*   **役割:** `session_id` という鍵を受け取り、対応する「履歴管理オブジェクト」を返す**工場（ファクトリー関数）**だ。
*   **責務:** `session_id` ごとに、正しい履歴の保管場所（この場合は DynamoDB の特定のアイテム）を指し示す `DynamoDBChatMessageHistory` のインスタンスを生成する。`invoke` が呼ばれるたびに、この工場が稼働し、そのデュエル専用の履歴マネージャーを供給する。

#### 【パーツ3】`input_messages_key` (ユーザー入力の識別名)

*   **役割:** `invoke` 時に渡される入力辞書の中で、どれが「ユーザーからの新しいメッセージ」なのかを `RunnableWithMessageHistory` に教えるためのキー。
*   **責務:** このキー（この例では `"question"`）に紐づく値を、新しい会話履歴として記録する対象としてマークする。

#### 【パーツ4】`history_messages_key` (履歴注入先の識別名)

*   **役割:** `runnable`（コアエンジン）に渡す辞書の中で、どこに「過去の会話履歴」を注入すればよいかを教えるためのキー。
*   **責務:** `MessagesPlaceholder(variable_name="history")` で指定した名前と一致させる必要がある。`RunnableWithMessageHistory` は、ここに `get_session_history` で取得した過去のメッセージリストを自動的にセットする。

---

### `invoke` 実行時の内部処理フロー（完全版）

`chain_with_history.invoke({"question": "..." }, config={"configurable": {"session_id": "..."}})` が実行された瞬間の、内部の精密なステップを追ってみよう。

**【ステップ 0】デュエル開始**
`invoke` がコールされる。`RunnableWithMessageHistory` が制御を握る。

**【ステップ 1】セッションIDの特定**
*   `config` 引数から `{"configurable": {"session_id": "some-user-session-123"}}` を取り出す。
*   `session_id` として `"some-user-session-123"` を確保する。これが今回のデュエルの識別子となる。

**【ステップ 2】履歴マネージャーの召喚**
*   確保した `session_id` を使い、【パーツ2】の `get_session_history` ファクトリー関数を呼び出す。
*   `lambda "some-user-session-123": DynamoDBChatMessageHistory("some-user-session-123")` が実行され、このセッション専用の `DynamoDBChatMessageHistory` インスタンスがメモリ上に生成される。
*   この時点では、まだDBアクセスは発生していない。ただインスタンスが作られただけだ。

**【ステップ 3】過去の履歴をロード（`GET` オペレーション）**
*   `RunnableWithMessageHistory` は、内部で「これからコアエンジンを動かすから、過去の履歴をくれ」と、ステップ2で召喚した履歴マネージャーに要求する。
*   この要求により、`DynamoDBChatMessageHistory` インスタンスの `.messages` プロパティが参照される。
*   `@property` デコレータで定義された `messages` メソッドが発動！ `table.get_item(Key={"SessionId": "some-user-session-123"})` が実行され、**ここで初めて DynamoDB への読み込みが発生する。**
*   DB から取得した履歴データが、LangChain のメッセージオブジェクトのリストに変換されて返される。

**【ステップ 4】入力データの合成**
*   `RunnableWithMessageHistory` は、`invoke` に渡された元の入力辞書 `{"question": "..."}` をベースに、新しい辞書を組み立てる。
*   【パーツ4】で指定されたキー `"history"` を使って、ステップ3でロードした過去の履歴リストを追加する。
*   結果として、`rag_chain_core` に渡される最終的な入力は `{"question": "...", "history": [（過去のメッセージリスト）]}` という形になる。

**【ステップ 5】コアエンジンの実行**
*   合成された完全な入力辞書を使って、【パーツ1】の `rag_chain_core` を `invoke` する。
*   `rag_chain_core` は、履歴のことなど何も知らずに、与えられたコンテキストと質問に基づいて応答を生成する。

**【ステップ 6】未来の履歴を保存（`PUT` オペレーション）**
*   `rag_chain_core` の処理が完了し、最終的な応答（`answer`）が返ってくると、`RunnableWithMessageHistory` が最後の仕事に取り掛かる。
*   今回のやり取り、つまり「ユーザーの質問（`input_messages_key` の値）」と「LLMの応答（ステップ5の結果）」を、新しいメッセージオブジェクトとしてリストにまとめる。
*   ステップ2で召喚した履歴マネージャーの **`.add_messages()` メソッドを内部的に呼び出す。**
*   `add_messages` メソッドが発動！ まず現在の履歴を `.messages` で再度取得し（※）、それに新しいやり取りを追加して、`table.put_item(...)` を実行する。**ここで DynamoDB への書き込みが発生し、会話履歴が更新される。**

（※注：`add_messages` 内で再度 `.messages` を呼ぶのは、複数のリクエストが同時に発生した場合の競合を避けるための基本的な実装です。より堅牢にするには、DynamoDBの条件付き書き込みなどを使う高度な戦術もあります。）

**【ステップ 7】デュエル終了**
*   最終的な応答が `invoke` の呼び出し元に返される。

---

### 結論

`RunnableWithMessageHistory` は単なるラッパーではなく、**状態管理のライフサイクル（生成 → 読み込み → 実行 → 書き込み）を宣言的に定義し、自動で実行してくれる**、極めて強力な制御システムである。このカードを使いこなせれば、君のデュエルは新たなステージへと進化するだろう。
