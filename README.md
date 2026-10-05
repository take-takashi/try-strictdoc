# StrictDoc Order Management PoC

StrictDocを、注文管理の **Feature → Behavior → Scenario → Source → Test → Test Result** の関係を保つSSOTとして試す小さなPoCです。Dockerは使いません。

## セットアップ

macOSにmiseを用意したうえで、リポジトリルートで実行します。

```bash
mise install                 # mise.toml: Python 3.12 / uv / StrictDoc
uv sync --locked             # プロジェクト環境にpytestをインストール
```

StrictDocはプロジェクトローカルのmise設定からPyPI backend経由で導入します。pytestはアプリ依存ではなく開発依存としてuvで管理しています。

## 試す

```bash
uv run pytest --junitxml=reports/orders.pytest.junit.xml
mise exec -- strictdoc server .
```

StrictDocは `http://127.0.0.1:5111` で起動します。`reports/orders.pytest.junit.xml` はStrictDocがJUnitとして認識するファイル名です。レポートがない場合や仕様・実装を変更した場合は、StrictDocを起動する前にテストを実行してください。

StrictDocは `.gitignore` のパターンもドキュメント検索から除外します。そのため、インポートしたいJUnit XMLを `.gitignore` で無視するとStrictDocにも見つかりません。JUnitレポートをGit管理しない場合は、`.gitignore` ではなくローカルの `.git/info/exclude` に追加してください。

### `.sdoc` の更新と生成物

仕様の編集元は [`docs/order-management.sdoc`](docs/order-management.sdoc) です。`.sdoc` は直接編集し、任意で整形してからHTMLを再生成します。

```bash
mise exec -- strictdoc format .
mise exec -- strictdoc export . --formats=html --output-dir build/strictdoc
```

HTMLは生成物で、Git管理しません。対話的な確認には上記の `strictdoc server .` を使います。

### 生成HTMLで確認できるもの

生成先は `build/strictdoc/html/index.html` です。HTMLから以下を確認できます。

- **Traceability**: Order Management文書のTraceability view — Parent/Child階層とSourceリンク
- **Traceability Matrix**: `traceability_matrix.html`
- **Tree Map**: `tree_map.html` — Document tree、requirements source coverage、requirements test coverage
- **Source coverage**: `source_coverage.html` — コード側のrelation markerと参照先
- **JUnit結果**: `orders.pytest.junit.html` — テストケースとPASSED/FAILED、テスト関数リンク

HTMLページへの相対URLはStrictDocの出力形式に依存します。サーバーで使う場合は、起動後のDocument/Traceability画面と各画面のナビゲーションを利用してください。

## `.sdoc` の構造

[`docs/order-management.sdoc`](docs/order-management.sdoc) ではStrictDoc標準の `[REQUIREMENT]` ノードを使っています。各ノードにUIDを付け、組み込みの `TAGS` で `FEATURE` / `BEHAVIOR` / `SCENARIO` を分類し、組み込みの `Parent` Relationで親UIDを明示しています。Markdown見出しではありません。

```text
Order (ORD-FEAT-001)
└─ Cancel Order (ORD-FEAT-003)
   ├─ Behavior (ORD-BEH-001)
   │  ├─ Scenario (ORD-SCN-001)
   │  └─ Scenario (ORD-SCN-002)
   └─ Behavior (ORD-BEH-002)
      └─ Scenario (ORD-SCN-003)
```

`Create Order` もFeatureノードとして置いてありますが、実装対象外です。現PoCではCustom Grammarを作っていません。タグは編集しやすい一方、Grammarがノード種別として検証するものではなく、BehaviorにScenarioを必須にする等の制約もありません。種別を強制したくなった段階で、独自Grammarの `FEATURE` / `BEHAVIOR` / `SCENARIO` ノードや必須フィールドへ進むのが妥当です。

## Traceabilityの実装

- [`src/order.py`](src/order.py) の `cancel_order` 関数docstringに `@relation(UID, scope=function)` を置き、2つのBehaviorを関数へリンクしています。
- [`tests/test_order.py`](tests/test_order.py) では各pytest関数のdocstringから対応Scenarioへリンクしています。
- StrictDocはPython関数を解析し、HTML上で関数の行範囲へのリンクを作ります。行番号を手書きしていないので、行追加には比較的強い一方、関数名やUID変更時はmarkerを同期する必要があります。
- JUnit importerはpytestの `classname` / test名からテストファイルと関数を推定し、レポートのTest Resultからテスト関数へリンクします。`tests/__init__.py` はJUnitのclassnameを `tests.test_order` にし、この対応付けを安定させるためのものです。

到達する関係は `Feature → Behavior → Scenario → test function → JUnit result` と `Behavior → implementation function` です。Scenarioから結果までは、Scenarioのrelation marker → pytest関数と、JUnit Result → 同じpytest関数のSource linkを辿ります。レポート内のTest ResultからScenario UIDへの直接Relationが自動生成されるわけではありません。

## 触って分かったこと

- **自然だったこと:** `.sdoc` はプレーンテキストでAIにも人間にも差分レビューしやすく、標準RequirementのUID・TAGS・Parent Relationで小さな機能ツリーを表現できました。Custom GrammarなしでPoCを始められます。
- **UID:** Parent Relation・Source marker・Test markerそれぞれがUIDを参照するため、安定したIDが要ります。意味のある接頭辞を付けて手動管理するのは小規模なら簡単ですが、大規模では移動・改名時に更新漏れを防ぐ運用が必要です。
- **階層の癖:** この例はノードを文書内でフラットに並べ、Relationで親子付けしています。Traceability画面では意図した階層になりますが、**Document Tree / Document tree mapはファイル内の配置**を表示するため、Parent RelationのFeature treeと同じにはなりません。Relation階層を見たい場合はTraceabilityを使います。
- **Code / Test:** 関数単位のリンクと行範囲表示は実用的でした。テスト関数をScenarioへ直接結び、JUnit結果をその関数へ自動リンクすることで、間をSource経由で辿れます。テストディレクトリはStrictDoc設定の `include_source_paths` に含める必要があります。
- **Coverage:** StrictDocのsource coverageはRequirementとソースのリンク状態であって、実行時の行・分岐カバレッジではありません。Tree Mapにはソース coverageとtest coverageが別々に表示され、未リンクScenarioを視覚的に見つけられます。JUnitは実行時の成功/失敗を補います。
- **未実装・未テスト検出:** 未リンク項目の発見やレビューには役立ちますが、「すべてのScenarioにテストが必須」といった品質ゲートや不足検出を、このPoCだけでCI失敗にするわけではありません。追加の検証スクリプト/ポリシー、またはGrammar設計が必要です。
- **JUnit:** StrictDocがJUnit XMLを読み、結果とテスト関数を表示するところまで確認しました。機能は実験的な扱いであり、Python test classnameとStrictDocのパス推定に依存します。テスト実行後にレポートを更新する必要もあります。
- **Issue / SSOT / Agent:** GitHub Issueとは独立した恒久的仕様の置き場にはなり得ます。仕様ノード、UID、Source/Testのrelation markerが一緒にGit管理されるので、Agentが仕様を読んで実装する入力にも適します。ただしFeature/Behavior/Scenarioの型制約、受け入れ条件や欠落検査を強く求めるなら、独自Grammar・CI検査が必要です。
- **採用判断:** StrictDocは「仕様とコード/テストの追跡・レビュー」を可視化する用途には候補になります。一方で、BDDシナリオ管理や機能ツリー専用DBとしてそのまま使うには、文書ツリーとRelationツリーの違い、型制約の弱さ、テスト結果から仕様への間接リンクが気になります。まず標準機能で十分な規模か試し、強い構造制約が必須になってからCustom Grammarを検討するのがよさそうです。
