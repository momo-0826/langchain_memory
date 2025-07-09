# `RunnableParallel`を使う場合と使わない場合の違い

LCEL (LangChain Expression Language) でチェーンを構築する際、`RunnableParallel`、つまり辞書 `{}` で処理を囲むか囲まないかで、データの流れと構造が根本的に変わる。

この違いを理解することは、チェーンを自在に操るための重要な鍵となる。

入力はどちらのパターンも `{"prompt": "遊星について"}` とする。

---

### パターン1：`RunnableParallel` で囲む場合

`RunnableParallel` は、複数の独立した処理を並行して実行し、その結果を一つの辞書に集約するために使用する。

```python
from langchain_core.runnables import RunnableParallel

# retrieverのモックを単純化
def simple_retriever(query_dict):
    return f"Context for '{query_dict['question']}'"

chain_with_parallel = RunnableParallel({
    "docs": lambda x: simple_retriever({"question": x["prompt"]}),
    "prompt": lambda x: x["prompt"]
})

# 実行
# chain_with_parallel.invoke({"prompt": "遊星について"})
```

#### 挙動

1.  `RunnableParallel` は、入力として `{"prompt": "遊星について"}` を受け取る。
2.  この入力データは、辞書内の**各キー（`"docs"` と `"prompt"`）の処理（ラムダ関数）に、それぞれ独立して**渡される。
3.  `"docs"` の処理は、`simple_retriever` を呼び出し、`"Context for '遊星について'"` という文字列を計算する。
4.  `"prompt"` の処理は、入力から `"遊星について"` という文字列をそのまま取り出す。
5.  `RunnableParallel` は、これらの結果を**一つの新しい辞書にまとめて**出力する。

#### 出力結果

```json
{
  "docs": "Context for '遊星について'",
  "prompt": "遊星について"
}
```

#### ポイント
- **複数の独立した処理を並行して実行**し、その結果を**一つの辞書に集約**する。
- 後続のチェーンに、**構造化された複数のデータ（この場合は `docs` と `prompt`）**を渡したい場合に使う。
- LCELにおいて、データソースをまとめてプロンプトに渡す際の標準的な手法である。

---

### パターン2：`RunnableParallel` で囲まない場合（`RunnableLambda`の例）

`RunnableParallel` を使わず、単一の `Runnable`（ここでは `RunnableLambda`）で処理を実装する場合。

```python
from langchain_core.runnables import RunnableLambda

def retriever_and_passthrough(input_dict):
    # この関数の中で、複数の処理を自分で書く
    docs = simple_retriever({"question": input_dict["prompt"]})
    prompt = input_dict["prompt"]
    # 自分で辞書を作って返す
    return {"docs": docs, "prompt": prompt}

chain_without_parallel = RunnableLambda(retriever_and_passthrough)

# 実行
# chain_without_parallel.invoke({"prompt": "遊星について"})
```

#### 挙動
1.  `RunnableLambda` は、入力として `{"prompt": "遊星について"}` を受け取る。
2.  その入力データが、`retriever_and_passthrough` 関数に**丸ごと**渡される。
3.  関数**内部**で、`retriever` の呼び出しや `prompt` の取り出しが行われる。
4.  関数は、**最終的な結果として一つのオブジェクト**（この場合は辞書）を返す。

#### 出力結果
```json
{
  "docs": "Context for '遊星について'",
  "prompt": "遊星について"
}
```

#### ポイント
- **一連の処理を一つの関数にまとめる**。
- 出力の形式は、関数の `return` 次第で、辞書だけでなく文字列やリストなど、自由に決めることができる。

---

### 結論：何が違うのか？

一見すると、どちらも同じ辞書を出力しているように見える。だが、その**意図と使い方**が全く違う。

- **`RunnableParallel`（辞書 `{}`）を使う場合**:
    - **宣言的（Declarative）**な書き方。
    - 「`docs` というキーにはこの処理の結果を、`prompt` というキーにはこの処理の結果を入れたい」という**構造**をLCELに伝える。
    - LCELが内部でデータの流れを最適化してくれる可能性がある。
    - **複数の独立したデータソースをまとめて、後続のプロンプトなどに渡す**場合に非常に便利で、LCELらしい書き方と言える。

- **`RunnableParallel` を使わない場合（例: `RunnableLambda`）**:
    - **命令的（Imperative）**な書き方。
    - 「この関数を実行して、その戻り値を次に渡してくれ」という**処理そのもの**をLCELに伝える。
    - `RunnableParallel` では表現できないような、**複雑な条件分岐やループを含む処理**をチェーンに組み込みたい場合に使う。

君がやろうとしていた「`retriever` で取得したコンテキストと、元の質問を、両方ともプロンプトテンプレートに渡す」という目的のためには、**`RunnableParallel` を使うのが最も自然で、LCELらしい書き方**なんだ。
