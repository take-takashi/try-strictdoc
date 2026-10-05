# StrictDoc Order Management PoC

StrictDocを、注文管理の **Feature → Behavior → Scenario → Source → Test → Test Result** の関係を保つSSOTとして試す小さなPoCです。Dockerは使いません。

## セットアップ

macOSにmiseを用意したうえで、リポジトリルートで実行します。

```bash
mise install                 # mise.toml: Python 3.12 / uv / StrictDoc
uv sync --locked             # pytestとPolicy Checker用StrictDoc APIをインストール
```

StrictDoc CLIはプロジェクトローカルのmise設定からPyPI backend経由で導入し、pytestは開発依存としてuvで管理しています。Policy CheckerはPythonから `strictdoc.api` を読むため、同じ `strictdoc==0.30.1` もuvの開発依存に固定しています。miseのPyPI toolは隔離環境なので、APIをimportするには別途プロジェクト環境への依存宣言が必要です（CLI/APIの二重インストールになります）。

## 試す

```bash
uv run pytest -q --junitxml=reports/orders.pytest.junit.xml
uv run python scripts/check_spec.py
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
   │  ├─ Scenario (ORD-SCN-002)
   │  └─ Scenario (ORD-SCN-004)
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
- **未実装・未テスト検出:** StrictDoc自体ではなく今回追加したPolicy Checkerが、Behaviorのproduction relation、Behavior配下のScenario、Scenarioのpytest relationを検査し、欠落でexit 1を返します。JUnitがあれば未実行・失敗もpassing coverageとして区別します。
- **JUnit:** StrictDocがJUnit XMLを読み、結果とテスト関数を表示するところまで確認しました。機能は実験的な扱いであり、Python test classnameとStrictDocのパス推定に依存します。テスト実行後にレポートを更新する必要もあります。
- **Issue / SSOT / Agent:** GitHub Issueとは独立した恒久的仕様の置き場にはなり得ます。仕様ノード、UID、Source/Testのrelation markerが一緒にGit管理されるので、Agentが仕様を読んで実装する入力にも適します。ただしFeature/Behavior/Scenarioの型制約、受け入れ条件や欠落検査を強く求めるなら、独自Grammar・CI検査が必要です。
- **採用判断:** StrictDocは「仕様とコード/テストの追跡・レビュー」を可視化する用途には候補になります。今回のPolicy Checkerで欠落検出は可能になりました。一方、BDDシナリオ管理や機能ツリー専用DBとしては、Document treeとRelation treeの違い、型制約の弱さ、JUnit結果から仕様への間接リンクが残るため、強い編集時制約が必要になった場合にCustom Grammarを検討します。

## Policy Checker

```bash
# JUnitを作ってからcheckerを実行
uv run pytest -q --junitxml=reports/orders.pytest.junit.xml
uv run python scripts/check_spec.py
```

[`scripts/check_spec.py`](scripts/check_spec.py) はexit code `0` をPASS、`1` をFAILとして返します。現在の成功出力は次のとおりです。

```text
Features:   3
Behaviors:  2
Scenarios:  4
Behavior implementation coverage: 2 / 2 (100.0%)
Scenario test coverage:           4 / 4 (100.0%)
Scenario passing coverage:        4 / 4 (100.0%)
PASSED
```

Checkerが検証するPolicy:

- `SCENARIO` は `tests/` 内の `test_*` functionにfunction-scope relationを持つ。
- `BEHAVIOR` は `src/` 内にSource relationを持つ。`tests/` へのrelationだけでは実装扱いにならない。
- 各Behaviorには、明示的なParent RelationでそのBehaviorを親とするScenarioが必要。
- Scenarioの親はBEHAVIOR、Behaviorの親はFEATUREで、どちらも親をちょうど1つ持つ。
- RequirementにはUIDとFEATURE/BEHAVIOR/SCENARIOの分類が必要。
- relation先のpytest functionにJUnit結果があり、PASSEDであることも確認する。レポート未生成/未読込時はPassing CoverageをN/Aとし、実行順の誤りを防ぐためCheckerも失敗する。

`Feature` / `Behavior` / `Scenario`の件数に加え、実装coverage・test-linked coverage・JUnit passing coverageを別々に出します。JUnit結果の不合格はCheckerも失敗します。未テストScenarioの場合のエラーはUIDとタイトルを示します。

### Checkerの自動テストと「仕様追加 → Checker FAIL」実験

[`tests/test_policy_checker.py`](tests/test_policy_checker.py) は一時ディレクトリに小さな`.sdoc`・ソース・JUnit fixtureを作り、次を検証します。プロジェクト本体の仕様を壊してテストすることはありません。

- 正常系PASS
- Scenarioのtest relationなしでFAIL
- Behaviorのproduction relationなしでFAIL
- Behaviorのchild ScenarioなしでFAIL
- Scenarioの親がFeatureでFAIL
- Behaviorの親がScenarioでFAIL
- JUnitがない/FAILEDならpassing coverageがN/A/低下しFAIL

実際に本体にも`ORD-SCN-004: キャンセル済み注文を再度キャンセルできない`を追加し、relation/testを付けない状態でCheckerを実行しました。結果は`Scenario test coverage: 3 / 4 (75.0%)`、exit code `1`でした。その後、`cancel_order`の再キャンセル拒否と対応pytestを加えると、pytestとCheckerがPASSし、`4 / 4 (100.0%)`になりました。

## Checkerが使うStrictDoc API

正規表現で`.sdoc`を解析していません。CheckerはStrictDoc 0.30.1の`strictdoc.api` exportから以下を利用します。

- `ProjectConfigLoader`と`TraceabilityIndexBuilder`でプロジェクト設定を読み、SDocとSourceを含むIndexを構築。
- `SDocDocumentIterator` / `SDocNode`でRequirementを抽出。`reserved_tags`からTAGSを読む。
- `get_requirement_reference_uids()`とIndexの`get_node_by_uid()`で、明示されたParent Relationと親ノードのTAGSを照合。
- Indexの`get_requirement_file_links()`でSource relationを取得。function-scope markerとSource indexの関数範囲を照合し、`test_*`関数かを判定。
- JUnit importerが生成した`TEST_RESULT`ノードの`TEST_PATH` / `TEST_FUNCTION` / `STATUS`を使い、Scenarioのテスト関数と結果を照合。

必要なクラスは`strictdoc.api`からimportでき、独自`.sdoc` parserは不要でした。ただしTraceabilityIndexのSource markerと関数行範囲など、返却モデルの詳細にも依存しています。公開APIの名前だけでなく、モデルの細部まで永久に互換とは仮定せず、バージョンをmise/uv双方で0.30.1に固定し、fixtureテストをアップグレード時のガードにします。

## Coverageの意味と限界

- **Behavior Implementation Coverage**は、Behaviorに`src/`内のSource Relationがある割合です。実装の正しさや実行時coverageを証明する値ではありません。
- **Scenario Test Coverage**は、Scenarioにテスト関数へのSource Relationがある割合です。Relationの存在を保証するもので、テスト品質までは判断しません。
- **Scenario Passing Coverage**は、Scenarioのrelation先functionがJUnitに現れ、すべてPASSEDの場合にカバー済みとします。pytest実行後のレポートがないと算出できず、N/Aです。
- JUnit resultはScenario UIDに直接つながるのではなく、Source functionのpath/nameを経由して対応付けます。テスト名規約、JUnit importer、StrictDoc側のpath解決に依存します。
- `pytest`自体もCIで実行するため、失敗したpytestはCI失敗です。Checkerのpassing coverageはさらに、どのScenarioまで通ったかを見せます。

## 最終評価: A — StrictDoc + 薄いPolicy Checkerで十分（現PoCの範囲）

このPoCの4 Scenario、2 Behaviorの範囲では、標準Requirement + TAGS + Parent/Source Relationと外部Checkerだけで、**仕様にScenarioを加える → relation/testがなければexit 1 → テストを加えるとexit 0**のループが成立しました。必要なCIでChecker実行を必須にする運用なら、Custom GrammarなしでもScenario Coverageを独自品質ゲートにできます。CheckerはStrictDocの構造を再実装せず、APIで読み取ったグラフにプロジェクト固有の数個のルールを適用する構成です。

ただし、TAGSはGrammar上の専用型ではありません。誤った/複数の種別、必須フィールドや許容Relationを編集時点でStrictDoc自身に制約させたい場合は、次段階でCustom Grammarに`FEATURE` / `BEHAVIOR` / `SCENARIO`の型を持たせる価値があります。それでも「srcにproduction実装がある」「test relationがpytest関数である」「JUnitで通った」といった横断ポリシーは外部Checker/CIの責任です。つまりCustom GrammarはPolicy Checkerを置き換えず、誤記防止と編集UIの改善を補います。

この結果だけからStrictDocがあらゆるFeature TreeやAI開発フローに最適とは結論できません。現時点では**仕様SSOTとトレーサビリティはStrictDoc、横断的な必須条件は小さなPolicy Checker、実行成功はpytest/JUnit**に分けるAが妥当です。モデルやPolicyが大きくなり、Checkerの例外処理・API依存が仕様の中心より重くなったらB（Custom Grammar）を再評価します。C（別方式）に移る決定的な限界は、この小規模PoCでは確認されませんでした。
