### `rag_memory_test_sample.py`のRAGメモリ機能の解説

RAG（Retrieval-Augmented Generation）は、LLMが外部の知識を参照して応答を生成する強力な技術だ。そして、この`rag_memory_test_sample.py`は、そのRAGの仕組みを「会話の記憶」に応用している。

例えるなら、これまでのメモリが「**会話の全てを記録するレコーダー**」だったとすれば、RAGメモリは「**会話の中から、今の話題に関連する部分だけを瞬時に探し出して、LLMに提示する賢い図書館員**」のようなものだ。

---

### `rag_memory_test_sample.py`のRAGメモリ機能の解説

このコードの目的は、「**過去の会話履歴の中から、現在のユーザーの入力に最も関連性の高い部分だけを抽出し、それをLLMへのプロンプトに含めることで、より文脈に沿った応答を生成させる**」ことだ。

これを実現するために、以下の主要なコンポーネントが連携している。

1.  **`OpenAIEmbeddings()` (埋め込みモデル)**
    *   **役割**: テキストを数値のベクトル（埋め込み）に変換する。
    *   **RAG特有の動き**: 人間が理解できる言葉を、コンピュータが比較・検索できる「意味の数値表現」に変換する。これにより、「ジャック」と「キング」が意味的に近い、といったことをコンピュータが理解できるようになる。

2.  **`FAISS` (ベクトルストア)**
    *   **役割**: 埋め込みモデルによってベクトル化されたテキストデータを効率的に保存し、高速に検索できるようにするデータベース。
    *   **RAG特有の動き**: 会話の各ターン（ユーザーの入力とAIの応答）が、この`FAISS`という図書館に「本」として格納される。それぞれの「本」には、その内容を表す「分類番号」（ベクトル）が振られている。

3.  **`retriever = vectorstore.as_retriever()` (リトリーバー)**
    *   **役割**: ベクトルストアから、与えられたクエリ（質問）に最も関連性の高いテキストを検索して取り出す機能。
    *   **RAG特有の動き**: ユーザーが新しい質問をすると、このリトリーバーが「図書館員」として機能する。ユーザーの質問をベクトル化し、`FAISS`図書館の中から、その質問のベクトルに最も近い（つまり、意味的に関連性の高い）「本」（過去の会話履歴）を素早く探し出してくる。`search_kwargs={"k": 3}`は、「関連性の高い上位3冊の本を持ってきてくれ」という指示だ。

4.  **プロンプトテンプレート (`ChatPromptTemplate`) の変更**
    *   **役割**: LLMに渡す指示書（プロンプト）のひな形。
    *   **RAG特有の動き**: 
        ```python
        ("system", "You are a helpful AI assistant. Use the following retrieved conversation history to answer the question:\n\n{retrieved_history}"),
        MessagesPlaceholder(variable_name="history"), # これまでの会話履歴（短期的）
        ("human", "{input}"),
        ```
        *   `{retrieved_history}`という新しいプレースホルダーが追加されている。ここに、リトリーバーが探し出してきた「関連性の高い過去の会話」が挿入される。
        *   システムプロンプトで「`retrieved_history`を使って質問に答えろ」と明示的に指示することで、LLMは関連情報に基づいて応答を生成する。
        *   `MessagesPlaceholder(variable_name="history")`は、フェーズ1で学んだ、`RunnableWithMessageHistory`が管理する**直近の会話履歴（短期的メモリ）**が入る場所だ。RAGメモリは、この短期的な履歴に加えて、**長期的な関連履歴**も参照する、という二重構造になっている。

5.  **チェーンの定義 (`RunnablePassthrough.assign(...)`)**
    *   **役割**: データの流れを制御し、各コンポーネントを連携させる。
    *   **RAG特有の動き**: 
        ```python
        chain = (
            RunnablePassthrough.assign(
                retrieved_history=lambda x: retriever.invoke(x["input"])
            )
            | prompt
            | llm
            | StrOutputParser()
        )
        ```
        *   これがRAGの心臓部だ。ユーザーの新しい入力（`x["input"]`）がチェーンに入ると、まず`RunnablePassthrough.assign`が発動する。
        *   この`assign`の中で、`retriever.invoke(x["input"])`が実行され、ユーザーの入力に関連する過去の会話履歴が`FAISS`から検索される。
        *   検索された結果は、`retrieved_history`というキーで、プロンプトに渡されるデータに追加される。
        *   これにより、`prompt`は、ユーザーの現在の入力、直近の会話履歴、そして**RAGによって検索された関連性の高い過去の会話**という、全ての文脈情報を受け取って、LLMへの指示書を組み立てる。

6.  **`RunnableWithMessageHistory`と`VectorStore`への手動追加**
    *   **役割**: `RunnableWithMessageHistory`は、`ChatMessageHistory`（短期メモリ）の管理を自動で行う。
    *   **RAG特有の動き**: 
        *   `RunnableWithMessageHistory`は、`ChatMessageHistory`オブジェクトを期待するため、`get_session_history_with_rag`関数は`ChatMessageHistory`を返す。
        *   しかし、`FAISS`（長期メモリ）への会話履歴の追加は、`RunnableWithMessageHistory`の自動管理の範囲外だ。
        *   そのため、コードの実行部分で`st.data[f"{SESSION_ID}_vectorstore"].add_texts(...)`のように、**各会話ターンが終わるたびに、手動でユーザーの入力とAIの応答を`FAISS`に追加している**。
        *   これは、実際のアプリケーションでは、`RunnableWithMessageHistory`のコールバック機能や、カスタムのラッパーを作成することで自動化される部分だ。

### RAGメモリの「賢さ」

通常のバッファメモリが「全ての会話をそのまま記憶する」のに対し、RAGメモリは「**必要な情報だけを、膨大な過去の会話の中から探し出してくる**」という点で賢い。

これにより、LLMに渡すプロンプトの長さを抑えつつ、関連性の高い長期的な文脈を提供できるため、より正確で、より深い理解に基づいた応答が可能になる。
