# `rag_memory_fixed_system_prompt_test.py`におけるLCELデータフロー解説

このドキュメントでは、`rag_memory_fixed_system_prompt_test.py`ファイル内のLangChain Expression Language (LCEL) を用いたデータフローについて、各Runnableの役割とデータの変換過程を詳細に解説します。

## 全体像

`full_rag_chain`は、以下のRunnableをパイプ（`|`）で連結して構成されています。

`rag_context_and_question_preparer`
`prepare_human_message_content`
`final_chat_prompt`
`llm`
`StrOutputParser()`

このチェーンは、`with_rag_history`という`RunnableWithMessageHistory`によってラップされており、会話履歴の管理も行われます。

## 各Runnableの役割とデータフロー

### 1. `rag_context_and_question_preparer`

*   **定義**:
    ```python
    rag_context_and_question_preparer = {
        "context": lambda x: "\n\n".join(retriever.invoke({"question": x["question"]})),
        "question": RunnablePassthrough(),
    }
    ```
*   **入力**: `with_rag_history.invoke()`から渡される辞書。例: `{"question": "遊星について教えてください。"}`
*   **処理**:
    *   `"context"`キー: 入力辞書`x`から`x["question"]`（ユーザーの質問文字列）を取り出し、`retriever.invoke()`に渡します。`retriever`は関連文書のリストを返し、それを`"\n\n".join()`で結合して一つの文字列（`combined_context_string`）にします。
    *   `"question"`キー: `RunnablePassthrough()`は、受け取った入力辞書`x`全体をそのまま出力します。
*   **出力**: `{"context": combined_context_string, "question": {"question": "遊星について教えてください。"}}`
    *   `"question"`キーの値が辞書全体になっている点に注意してください。

### 2. `prepare_human_message_content`

*   **定義**:
    ```python
    prepare_human_message_content = {
        "rag_human_message_content": rag_human_message_template,
        "question": RunnablePassthrough(),
    }
    ```
*   **入力**: `rag_context_and_question_preparer`の出力。例: `{"context": combined_context_string, "question": {"question": "遊星について教えてください。"}}`
*   **処理**:
    *   LCELの辞書形式のRunnableは、受け取った入力辞書全体を、内部の各Runnable（`rag_human_message_template`と`RunnablePassthrough()`）に**そのまま渡します**。
    *   `"rag_human_message_content"`キー: `rag_human_message_template`（`PromptTemplate`インスタンス）は、入力辞書から`input_variables`（`"context"`と`"question"`）に合致するキーの値を自動的に探し出し、テンプレートをフォーマットします。
        *   `"context"`には`combined_context_string`が渡されます。
        *   `"question"`には`{"question": "遊星について教えてください。"}`という辞書全体が渡されますが、`PromptTemplate`は辞書から`"question"`キーの文字列値（"遊星について教えてください。"）を適切に抽出して使用します。
        *   結果として、`rag_human_message_template`はフォーマットされた文字列（`formatted_human_message_string`）を生成します。
    *   `"question"`キー: `RunnablePassthrough()`は、受け取った入力辞書全体（`{"context": combined_context_string, "question": {"question": "遊星について教えてください."}}`）をそのまま出力します。
*   **出力**: `{"rag_human_message_content": formatted_human_message_string, "question": {"context": combined_context_string, "question": {"question": "遊星について教えてください."}}}`
    *   ここでも`"question"`キーの値が辞書全体になっている点に注意してください。

### 3. `final_chat_prompt`

*   **定義**:
    ```python
    final_chat_prompt = ChatPromptTemplate.from_messages([
        ("system", fixed_system_prompt_content),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{rag_human_message_content}")
    ])
    ```
*   **入力**: `prepare_human_message_content`の出力。例: `{"rag_human_message_content": formatted_human_message_string, "question": {"context": ..., "question": {...}}}`
    *   **重要**: このRunnableが実行される直前に、`RunnableWithMessageHistory`が`history_messages_key="history"`で指定された`"history"`キーに、現在の会話履歴（`ChatMessageHistory`オブジェクトから取得）を自動的に追加します。
*   **処理**:
    *   `fixed_system_prompt_content`（固定文字列）がシステムメッセージとして設定されます。
    *   `MessagesPlaceholder(variable_name="history")`に、`RunnableWithMessageHistory`によって追加された会話履歴が埋め込まれます。
    *   `("human", "{rag_human_message_content}")`に、入力辞書から`"rag_human_message_content"`キーの値（`formatted_human_message_string`）が埋め込まれます。
    *   入力辞書内の`"question"`キー（辞書全体）は、`final_chat_prompt`では使用されないため、無視されます。
*   **出力**: `BaseMessage`オブジェクトのリスト（LLMが解釈できる形式のプロンプト）。例:
    ```
    [
        SystemMessage(content='あなたは優秀なアシスタントです。'),
        HumanMessage(content='ユーザー1の質問'),
        AIMessage(content='AI1の応答'),
        HumanMessage(content='ユーザー2の質問'),
        AIMessage(content='AI2の応答'),
        SystemMessage(content='文脈:
[結合されたコンテキスト]'),
        HumanMessage(content='[rag_human_message_templateでフォーマットされた文字列]')
    ]
    ```

### 4. `llm`

*   **定義**: `llm = ChatOpenAI(temperature=0)`
*   **入力**: `final_chat_prompt`の出力（`BaseMessage`オブジェクトのリスト）。
*   **処理**: LLM（大規模言語モデル）がプロンプトを解釈し、応答を生成します。
*   **出力**: LLMの応答オブジェクト（例: `AIMessage`）。

### 5. `StrOutputParser()`

*   **定義**: `StrOutputParser()`
*   **入力**: `llm`の出力（LLMの応答オブジェクト）。
*   **処理**: LLMの応答オブジェクトから、純粋な応答文字列を抽出します。
*   **出力**: LLMが生成した応答文字列。

## `RunnableWithMessageHistory`の役割

`RunnableWithMessageHistory`は、上記の`full_rag_chain`をラップし、以下の重要な役割を果たします。

1.  **入力の監視**: `input_messages_key="question"`で指定されたキー（`"question"`）の値を、ユーザーの現在の入力として認識します。
2.  **履歴の取得**: `get_session_history`関数を使用して、指定された`session_id`に対応する`ChatMessageHistory`オブジェクトから過去の会話履歴を取得します。
3.  **履歴の挿入**: `full_rag_chain`が実行される直前に、取得した会話履歴を`history_messages_key="history"`で指定された`"history"`キーとして、`full_rag_chain`の入力に自動的に追加します。これにより、`final_chat_prompt`の`MessagesPlaceholder(variable_name="history")`が正しく埋め込まれます。
4.  **履歴の保存**: `full_rag_chain`が応答を生成した後、現在のユーザー入力とLLMの応答を`ChatMessageHistory`オブジェクトに保存し、次回の会話に備えます。

この詳細なデータフロー解説が、LCELの挙動と、各コンポーネントがどのように連携してRAGと記憶機能を実装しているかの理解に役立つことを願っています。

```