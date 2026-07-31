# GODIMAP

<a id="contents"></a>

## Contents / 目次 / 목차

- [日本語](#ja)
  - [概要と主な機能](#ja-overview)
  - [冒険者様を募集しています](#ja-adventurers)
  - [導入・起動・更新](#ja-install)
  - [基本操作](#ja-controls)
  - [設定・トラブルシューティング](#ja-settings)
  - [ソースコードとビルド](#ja-development)
  - [ライセンスと注意事項](#ja-license)
  - [今後の追加予定](#ja-roadmap)
- [한국어](#ko)
  - [개요와 주요 기능](#ko-overview)
  - [모험가님을 모집합니다](#ko-adventurers)
  - [설치·실행·업데이트](#ko-install)
  - [기본 조작](#ko-controls)
  - [설정·문제 해결](#ko-settings)
  - [소스 코드와 빌드](#ko-development)
  - [라이선스와 주의 사항](#ko-license)
  - [향후 추가 예정](#ko-roadmap)
- [English](#en)
  - [Overview and features](#en-overview)
  - [Adventurers wanted](#en-adventurers)
  - [Installation, launch, and updates](#en-install)
  - [Basic controls](#en-controls)
  - [Settings and troubleshooting](#en-settings)
  - [Source code and building](#en-development)
  - [Licenses and notices](#en-license)
  - [Planned additions](#en-roadmap)

---

<a id="ja"></a>

# 日本語

<a id="ja-overview"></a>

## 概要と主な機能

GODIMAPは、Godiusのゲーム画面に表示される地域名と現在座標をOCRで読み取り、対応するミニマップと現在位置をゲーム画面上へ表示する情報提供型ツールです。

ゲームクライアントの改変、通信解析、自動操作、マクロ操作は行いません。

**[GODIMAP本体（GODIMAP.exe同梱ZIP）のリリースページ](https://github.com/GD-fandev/Godimap/releases)**

- 韓国語・日本語・英語の地域名OCR
- 地域に対応するミニマップの自動表示
- ゲーム内座標 `X:Y` の読み取りと現在位置の点滅表示
- ミニマップの位置・倍率・不透明度調整
- 未登録地域および位置情報未登録地域の案内
- OCR結果と動作状態の確認
- GitHubからのマップ画像・マップ情報更新

### 動作環境

- Windows 10 / 11（64bit）
- ウィンドウ表示されたGodius Client

配布版にはOCRエンジンと韓国語・日本語・英語の認識モデルが含まれます。通常、PythonやWindowsのOCR言語パックを別途インストールする必要はありません。

<a id="ja-adventurers"></a>

## 冒険者様を募集しています

GODIMAPには、まだ測量が完了していない未調査地域があります。

現在の未調査地域は以下の通りです。

- カールマーニュ洞窟 1F
- 中部背骨洞窟 1F
- 東部背骨洞窟 1~5F
- 西部背骨洞窟 1~5F
- レゲ/カリ地下洞窟 9~10F
- サエフ洞窟 2~3F
- シャドミュム洞窟 3~6F
- エブリン・エチリン洞窟 1~5F
- ヘル 1F~10F

これらの地域は入場条件のため制作者自身での調査が難しく、現時点では多くの地図が未完成となっています。十分な状態でお届けできず申し訳ありませんが、いつか自分で調査するか、有志の方のお力を借りながら、少しずつ完成させていきたいと考えています。

未知の地へ赴き、地図の完成に力を貸してくださる勇気ある冒険者様を募集しています。ご協力いただける方は、Discordにて制作者までDMをお送りいただけますと幸いです。

ささやかですが感謝の印として、次回の配布時に地図の完成へご協力くださった冒険者様のお名前を、該当地域のミニマップ左下に刻ませていただきたいと思います。

皆様の冒険の記録が、次にその地を訪れる冒険者様の道標となります。ご協力を心よりお待ちしております。

<a id="ja-install"></a>

## 導入・起動・更新

### 配布フォルダー

```text
GODIMAP/
├─ GODIMAP.exe
├─ maps/
├─ mapdata/
├─ ocr_models/
├─ README.md
└─ ライセンス関連ファイル
```

ZIPをすべて展開し、`GODIMAP.exe`をダブルクリックしてください。EXEだけをデスクトップ等へ移動してはいけません。デスクトップから起動したい場合は、EXEのショートカットを作成してください。

`maps`、`mapdata`、`ocr_models`の名前や内部構成も変更しないでください。同じGODIMAPを二重に起動することはできません。

### マップデータの更新

GODIMAPは起動時に公式GitHubリポジトリへ接続し、マップ画像とマップ情報のバージョンを確認します。EXE自体は自動更新しません。

新しいマップデータがある場合は、状態欄に赤い更新案内が表示されます。案内をクリックした場合にのみZIPをダウンロードします。サイズ、SHA-256、フォルダー構成、JSON、対応画像を検証してから適用し、失敗時は以前のデータへ自動的に戻します。成功後は再起動せずに新しいデータを使用できます。

バージョン確認に伴い、IPアドレス、接続時刻など一般的な通信情報がGitHub側へ送信される場合があります。

<a id="ja-controls"></a>

## 基本操作

### GODIMAPウィンドウ

- `OCR`：実際に読み取っている地域名・座標範囲
- `認識された内容`：`KR`、`JP`、`EN`別の認識結果と`X:Y`
- `状態`：現在の動作状況と更新案内
- `KR / JP / EN`ボタン：表示言語を順番に切り替え
- `HELP`：現在選択中の言語で操作説明を表示

`invalid`は他言語の誤認識を除外した状態、`(No data)`は認識できる文字がない状態です。初回の表示言語はWindowsの言語に合わせて選択され、以後は保存されます。

### 地域名OCR範囲

GodiusまたはGODIMAPの対象ウィンドウが選択されている状態で、数字列の <kbd>0</kbd> キーを押します（テンキーの0ではありません）。

1. 赤い半透明ボックスをドラッグして地域名へ移動します。
2. 右下のハンドルをドラッグしてサイズを調整します。
3. 地域名全体だけが十分な余白とともに入るようにします。
4. もう一度 <kbd>0</kbd> を押して確定します。

### 座標OCR範囲

<kbd>Shift</kbd> + <kbd>0</kbd> を押し、黄色い半透明ボックスをゲーム内の`X:Y`へ合わせます。移動と右下ハンドルによるサイズ調整後、同じキーをもう一度押して確定します。

### ミニマップと現在位置

地域名が登録済みパターンと一致するとミニマップが表示されます。座標変換データがある地域では、現在位置が約0.5秒間隔で点滅する黄色い点として表示されます。

- `No location data`：画像はあるものの座標変換データがない地域
- `No Map Data`：対応するマップがない、または地域名を一定時間特定できない状態
- `Charted by ...`：測量へ協力した冒険者様のお名前。地域へ入った際に約3秒間表示

### ミニマップ編集モード

<kbd>Ctrl</kbd> + <kbd>0</kbd> で編集モードを開始・終了します。

- 左ドラッグ：ミニマップを移動
- 右下の黄色いハンドルをドラッグ：倍率を40%～500%で変更
- マウスホイール：不透明度を30%～100%で変更（100%は完全に不透明）

編集モードを終了するとミニマップはクリックを受け取らず、背後のゲームUIをそのまま操作できます。位置、倍率、不透明度は自動保存されます。

<a id="ja-settings"></a>

## 設定・トラブルシューティング

個人設定は次の場所へ保存されます。

```text
%LOCALAPPDATA%\Godimap\godimap-config.json
```

表示言語、OCR範囲、ウィンドウ位置、ミニマップ位置・倍率・不透明度が保存されます。完全に初期化する場合はGODIMAP終了後にこのファイルをバックアップしてから移動または削除してください。

### Godius Clientが見つからない

- ゲームが起動中か、最小化されていないか確認してください。
- ゲームを管理者権限で起動している場合、GODIMAPにも同等の権限が必要になることがあります。

### OCRが認識しない、または途切れる

- 地域名・座標範囲を再設定し、文字切れや余分なUIがないか確認してください。
- 解像度やゲームUI配置を変更した場合は再設定してください。
- マウスオーバー等による短い欠落では、最後の正常なマップを一定時間維持します。

### ミニマップが表示されない

- 状態欄とOCR結果を確認してください。
- `maps`と`mapdata`に該当地域が含まれているか確認してください。
- ZIPから配布物全体を展開したか確認してください。

<a id="ja-development"></a>

## ソースコードとビルド

主要なリポジトリ構成：

```text
assets/       アイコン
docs/         追加文書
licenses/     第三者ライセンスと素材通知
maps/         更新元となるマップ画像
mapdata/      更新元となるマップJSON
ocr_models/   OCRモデル
packaging/    PyInstaller設定
source/       Pythonソース
tests/        自動テスト
tools/        ビルド・保守ツール
update/       公開用更新manifest
output/       ローカル生成物（Git管理対象外）
```

Python 3.12環境で依存パッケージをインストールした後、`tools/build_godimap.bat`を実行すると、`output/GODIMAP`へ配布一式を生成します。


測量用ツールの詳細手順は、指定された冒険者様へ別途案内します。

<a id="ja-license"></a>

## ライセンスと注意事項

- GODIMAP独自のソースコードは[MIT License](LICENSE.txt)で公開しています。
- ゲーム関連素材、地図画像、アイコン等はMIT Licenseの対象外です。詳細は[Asset Notice](licenses/ASSET_NOTICE.txt)をご確認ください。
- ダンジョン地図画像の出典：[Godius公式ホームページ](https://www.godius.co.kr/guide_8?t_id=2)
- 町の地図画像の出典：[Godius Online Forum](http://godius.s201.xrea.com/mmain.html)
- 第三者ソフトウェアとOCRモデルについては[Third-Party Notices](licenses/THIRD_PARTY_NOTICES.txt)と`licenses/third_party`をご確認ください。
- GODIMAPは非公式ツールです。ゲーム運営方針および素材提供元の規約に従い、各自の判断でご利用ください。

<a id="ja-roadmap"></a>

## 今後の追加予定

- すべての町のマップに、商店およびギルドの表示を追加
- フィールド進入時の道しるべガイドを追加（座標および大まかな方向を案内）
- 日本語の表記名は、今後公式表記に合わせて修正される可能性があります

[目次へ戻る](#contents)

---

<a id="ko"></a>

# 한국어

<a id="ko-overview"></a>

## 개요와 주요 기능

GODIMAP은 Godius 게임 화면에 표시되는 지역명과 현재 좌표를 OCR로 읽어, 해당 미니맵과 현재 위치를 게임 화면 위에 표시하는 정보 제공형 도구입니다.

게임 클라이언트 변조, 통신 분석, 자동 조작 및 매크로 기능은 사용하지 않습니다.

**[GODIMAP 본품(GODIMAP.exe 포함 ZIP) 릴리스 페이지](https://github.com/GD-fandev/Godimap/releases)**

- 한국어·일본어·영어 지역명 OCR
- 지역에 맞는 미니맵 자동 표시
- 게임 좌표 `X:Y` 인식과 현재 위치 점멸 표시
- 미니맵 위치·배율·불투명도 조절
- 미등록 지역과 좌표 데이터가 없는 지역 안내
- OCR 결과 및 동작 상태 확인
- GitHub를 통한 지도 이미지·정보 업데이트

### 실행 환경

- Windows 10 / 11 64비트
- 창 모드로 실행한 Godius Client

배포본에는 OCR 엔진과 한국어·일본어·영어 인식 모델이 포함됩니다. 일반 사용자는 Python이나 Windows OCR 언어팩을 별도로 설치할 필요가 없습니다.

<a id="ko-adventurers"></a>

## 모험가님을 모집합니다

GODIMAP에는 아직 측량이 완료되지 않은 미조사 지역이 있습니다.

미지의 지역을 탐험하고 지도 완성에 힘을 보태주실 용기 있는 모험가님을 모집합니다. 협력해 주실 분은 Discord에서 제작자에게 DM을 보내주시면 감사하겠습니다.

많은 것을 드리지는 못하지만 감사의 뜻으로, 다음 배포 때 지도 완성에 협력해 주신 모험가님의 이름을 해당 지역 미니맵 좌측 하단에 새겨드리고자 합니다.

여러분의 모험 기록이 다음 모험가의 이정표가 됩니다. 많은 협력을 부탁드립니다.

<a id="ko-install"></a>

## 설치·실행·업데이트

### 배포 폴더

```text
GODIMAP/
├─ GODIMAP.exe
├─ maps/
├─ mapdata/
├─ ocr_models/
├─ README.md
└─ 라이선스 관련 파일
```

ZIP 전체를 압축 해제한 다음 `GODIMAP.exe`를 실행하십시오. EXE만 바탕화면 등으로 옮기면 안 됩니다. 바탕화면에서 실행하려면 EXE의 바로가기를 만드십시오.

`maps`, `mapdata`, `ocr_models`의 이름과 내부 구성을 변경하지 마십시오. GODIMAP은 중복 실행할 수 없습니다.

### 맵 데이터 업데이트

GODIMAP은 실행 시 공식 GitHub 저장소에 접속하여 지도 이미지와 지도 정보의 버전을 확인합니다. EXE 자체는 자동 업데이트하지 않습니다.

새 지도 데이터가 있으면 상태 영역에 빨간색 업데이트 안내가 나타납니다. 안내를 클릭해야만 ZIP을 다운로드합니다. 파일 크기, SHA-256, 폴더 구조, JSON 및 대응 이미지를 검증한 후 적용하며, 실패하면 이전 데이터로 자동 복구합니다. 성공하면 프로그램을 다시 시작하지 않아도 새 데이터가 반영됩니다.

버전 확인 과정에서 IP 주소, 접속 시각 등 일반적인 통신 정보가 GitHub 측에 전달될 수 있습니다.

<a id="ko-controls"></a>

## 기본 조작

### GODIMAP 창

- `OCR`: 실제로 읽고 있는 지역명·좌표 화면
- `인식된 내용`: `KR`, `JP`, `EN`별 결과와 `X:Y`
- `상태`: 현재 동작 상태와 업데이트 안내
- `KR / JP / EN` 버튼: 표시 언어를 순서대로 변경
- `HELP`: 현재 선택된 언어로 사용법 표시

`invalid`는 다른 언어의 잘못된 판독을 제외한 상태이고 `(No data)`는 인식할 문자가 없는 상태입니다. 첫 실행 언어는 Windows 표시 언어에 맞춰지며 이후 저장됩니다.

### 지역명 OCR 영역

Godius 또는 GODIMAP 대상 창이 선택된 상태에서 숫자열의 <kbd>0</kbd> 키를 누릅니다(텐키 0 제외).

1. 붉은 반투명 상자를 드래그하여 지역명 위치로 옮깁니다.
2. 오른쪽 아래 핸들을 드래그하여 크기를 조절합니다.
3. 지역명 전체만 여유 있게 들어오도록 맞춥니다.
4. <kbd>0</kbd> 키를 다시 눌러 확정합니다.

### 좌표 OCR 영역

<kbd>Shift</kbd> + <kbd>0</kbd>을 눌러 노란 반투명 상자를 게임의 `X:Y`에 맞춥니다. 위치와 우측 하단 핸들 크기를 조절한 후 같은 키를 다시 눌러 확정합니다.

### 미니맵과 현재 위치

지역명 OCR 결과가 등록된 패턴과 일치하면 미니맵이 나타납니다. 좌표 변환 정보가 있는 지역에서는 현재 위치가 약 0.5초마다 깜빡이는 노란 점으로 표시됩니다.

- `No location data`: 이미지는 있지만 좌표 변환 데이터가 없는 지역
- `No Map Data`: 대응 지도가 없거나 일정 시간 지역명을 확정하지 못한 상태
- `Charted by ...`: 측량에 협력한 모험가 이름. 해당 지역 진입 시 약 3초간 표시

### 미니맵 편집 모드

<kbd>Ctrl</kbd> + <kbd>0</kbd>으로 편집 모드를 켜거나 끕니다.

- 왼쪽 드래그: 미니맵 이동
- 오른쪽 아래 노란 핸들 드래그: 배율 40%～500% 조절
- 마우스 휠: 불투명도 30%～100% 조절(100%는 완전 불투명)

편집 모드를 끄면 미니맵이 클릭을 받지 않으므로 뒤에 있는 게임 UI를 그대로 조작할 수 있습니다. 위치, 배율 및 불투명도는 자동 저장됩니다.

<a id="ko-settings"></a>

## 설정·문제 해결

개인 설정은 다음 위치에 저장됩니다.

```text
%LOCALAPPDATA%\Godimap\godimap-config.json
```

표시 언어, OCR 영역, 창 위치, 미니맵 위치·배율·불투명도가 저장됩니다. 완전히 초기화하려면 GODIMAP을 종료한 후 이 파일을 백업하고 이동하거나 삭제하십시오.

### Godius Client를 찾지 못하는 경우

- 게임이 실행 중인지, 최소화되어 있지 않은지 확인하십시오.
- 게임을 관리자 권한으로 실행했다면 GODIMAP에도 같은 권한이 필요할 수 있습니다.

### OCR이 인식하지 못하거나 잠시 끊기는 경우

- 지역명과 좌표 영역을 다시 설정하고, 글자 잘림이나 불필요한 UI가 포함되지 않았는지 확인하십시오.
- 해상도 또는 게임 UI 배치를 변경했다면 다시 설정하십시오.
- 마우스 오버 등으로 잠깐 인식이 끊겨도 마지막 정상 지도를 일정 시간 유지합니다.

### 미니맵이 나타나지 않는 경우

- 상태 영역과 OCR 결과를 확인하십시오.
- `maps`와 `mapdata`에 해당 지역이 들어 있는지 확인하십시오.
- 배포 ZIP 전체를 압축 해제했는지 확인하십시오.

<a id="ko-development"></a>

## 소스 코드와 빌드

저장소 주요 구조:

```text
assets/       아이콘
docs/         추가 문서
licenses/     제3자 라이선스 및 소재 안내
maps/         업데이트 원본 지도 이미지
mapdata/      업데이트 원본 지도 JSON
ocr_models/   OCR 모델
packaging/    PyInstaller 설정
source/       Python 소스
tests/        자동 테스트
tools/        빌드·관리 도구
update/       공개용 업데이트 manifest
output/       로컬 생성 결과(Git 제외)
```

Python 3.12 환경에 의존 패키지를 설치한 다음 `tools/build_godimap.bat`을 실행하면 `output/GODIMAP`에 사용자 배포본 전체가 만들어집니다.


측량 도구의 상세 사용법은 지정된 모험가님께 별도로 안내합니다.

<a id="ko-license"></a>

## 라이선스와 주의 사항

- GODIMAP 자체 소스 코드는 [MIT License](LICENSE.txt)로 공개합니다.
- 게임 관련 소재, 지도 이미지 및 아이콘 등은 MIT License 대상이 아닙니다. 자세한 내용은 [Asset Notice](licenses/ASSET_NOTICE.txt)를 확인하십시오.
- 던전 지도 이미지 출처: [가디우스 공식 홈페이지](https://www.godius.co.kr/guide_8?t_id=2)
- 마을 지도 이미지 출처: [가디우스 온라인 포럼](http://godius.s201.xrea.com/mmain.html)
- 제3자 소프트웨어와 OCR 모델은 [Third-Party Notices](licenses/THIRD_PARTY_NOTICES.txt) 및 `licenses/third_party`를 확인하십시오.
- GODIMAP은 비공식 도구입니다. 게임 운영 정책과 소재 제공자의 규정을 준수하고 각자의 판단에 따라 사용하십시오.

<a id="ko-roadmap"></a>

## 향후 추가 예정

- 모든 마을 지도에 상점 및 길드 표시 추가
- 필드 진입 시 이정표 가이드 추가(좌표 및 대략적인 방향 안내)
- 일본어 표기명은 추후 공식 표기에 맞춰 수정될 수 있습니다

[목차로 돌아가기](#contents)

---

<a id="en"></a>

# English

<a id="en-overview"></a>

## Overview and features

GODIMAP is an information-only overlay that reads the region name and current coordinates shown in the Godius game window and displays the corresponding minimap and player position.

It does not modify the game client, analyze network traffic, automate gameplay, or provide macro functions.

**[GODIMAP release page (ZIP containing GODIMAP.exe)](https://github.com/GD-fandev/Godimap/releases)**

- Korean, Japanese, and English region-name OCR
- Automatic minimap selection
- In-game `X:Y` coordinate recognition and blinking position marker
- Adjustable minimap position, scale, and opacity
- Notices for unmapped regions and maps without location calibration
- OCR and runtime status display
- Map image and metadata updates from GitHub

### Requirements

- 64-bit Windows 10 or Windows 11
- Godius Client running in windowed mode

The distributed package includes the OCR engine and Korean, Japanese, and English recognition models. End users normally do not need Python or Windows OCR language packs.

<a id="en-adventurers"></a>

## Adventurers wanted

Some GODIMAP regions have not yet been fully surveyed.

We are looking for courageous adventurers who are willing to explore unknown areas and help complete the maps. If you would like to participate, please send the creator a DM on Discord.

As a small token of appreciation, the names of adventurers who help complete a region may be displayed in the lower-left corner of that region's minimap in a future release.

Your exploration can become a guidepost for the adventurers who follow. Thank you for your support.

<a id="en-install"></a>

## Installation, launch, and updates

### Distribution folder

```text
GODIMAP/
├─ GODIMAP.exe
├─ maps/
├─ mapdata/
├─ ocr_models/
├─ README.md
└─ license and notice files
```

Extract the entire ZIP and run `GODIMAP.exe`. Do not move the EXE by itself. Create a shortcut if you want to launch it from the desktop.

Do not rename or rearrange `maps`, `mapdata`, or `ocr_models`. Only one GODIMAP instance can run at a time.

### Map-data updates

At startup, GODIMAP contacts the official GitHub repository to check the version of the map images and metadata. The EXE itself is not updated automatically.

When an update is available, a red notice appears in the status area. The ZIP is downloaded only after you click that notice. GODIMAP validates its size, SHA-256 hash, directory structure, JSON files, and referenced images before installation. A failed installation automatically restores the previous data. A successful update is loaded without restarting the program.

This version check may send ordinary connection information, such as your IP address and connection time, to GitHub.

<a id="en-controls"></a>

## Basic controls

### GODIMAP window

- `OCR`: captured region-name and coordinate areas
- `Recognized Content`: results for `KR`, `JP`, `EN`, and `X:Y`
- `Status`: current runtime state and update notice
- `KR / JP / EN` button: cycles the interface language
- `HELP`: opens instructions in the selected interface language

`invalid` means that an unreliable result from another language was filtered out. `(No data)` means that no readable text was found. The initial interface language follows Windows and is saved afterward.

### Region-name OCR area

With Godius or a relevant GODIMAP window selected, press the number-row <kbd>0</kbd> key (not the numeric-keypad 0).

1. Drag the translucent red box over the region name.
2. Drag its lower-right handle to resize it.
3. Include the full region name with a small margin and as little unrelated UI as possible.
4. Press <kbd>0</kbd> again to confirm.

### Coordinate OCR area

Press <kbd>Shift</kbd> + <kbd>0</kbd> and place the translucent yellow box over the in-game `X:Y` display. Move and resize it with the lower-right handle, then press the same shortcut again to confirm.

### Minimap and current position

A matching registered region name displays its minimap. On a calibrated map, a yellow marker blinks approximately every 0.5 seconds at the current position.

- `No location data`: a map image exists, but coordinate conversion data is unavailable
- `No Map Data`: no matching map exists or the region could not be identified for a while
- `Charted by ...`: names of contributing adventurers, shown for about three seconds when entering the region

### Minimap edit mode

Press <kbd>Ctrl</kbd> + <kbd>0</kbd> to enter or leave edit mode.

- Left-drag: move the minimap
- Drag the yellow lower-right handle: change scale from 40% to 500%
- Mouse wheel: change opacity from 30% to 100% (100% is fully opaque)

Outside edit mode, the minimap ignores mouse input so that you can click the game UI behind it. Position, scale, and opacity are saved automatically.

<a id="en-settings"></a>

## Settings and troubleshooting

Personal settings are stored at:

```text
%LOCALAPPDATA%\Godimap\godimap-config.json
```

This file stores the interface language, OCR regions, window position, and minimap position, scale, and opacity. To reset everything, close GODIMAP, back up the file, and then move or delete it.

### Godius Client is not found

- Confirm that the game is running and not minimized.
- If the game runs as administrator, GODIMAP may need the same privilege level.

### OCR does not recognize text or briefly drops out

- Reconfigure both OCR areas and check for clipped text or excessive unrelated UI.
- Reconfigure them after changing the resolution or game UI layout.
- Short dropouts caused by mouse-over effects are tolerated by retaining the last valid map for a while.

### The minimap does not appear

- Check the status area and OCR results.
- Confirm that the region exists in both `maps` and `mapdata`.
- Confirm that the complete distribution ZIP was extracted.

<a id="en-development"></a>

## Source code and building

Main repository layout:

```text
assets/       icons
docs/         additional documentation
licenses/     third-party licenses and asset notices
maps/         source map images for updates
mapdata/      source map JSON files for updates
ocr_models/   OCR models
packaging/    PyInstaller specifications
source/       Python source code
tests/        automated tests
tools/        build and maintenance tools
update/       public update manifest
output/       local generated output, excluded from Git
```

After installing the dependencies in a Python 3.12 environment, run `tools/build_godimap.bat`. The complete end-user distribution is assembled in `output/GODIMAP`.


Detailed surveying-tool instructions are provided separately to designated adventurers.

<a id="en-license"></a>

## Licenses and notices

- Original GODIMAP source code is released under the [MIT License](LICENSE.txt).
- Game-related assets, map images, and icons are not automatically covered by the MIT License. See the [Asset Notice](licenses/ASSET_NOTICE.txt).
- Dungeon map image source: [Official Godius website](https://www.godius.co.kr/guide_8?t_id=2)
- Town map image source: [Godius Online Forum](http://godius.s201.xrea.com/mmain.html)
- See [Third-Party Notices](licenses/THIRD_PARTY_NOTICES.txt) and `licenses/third_party` for third-party software and OCR-model terms.
- GODIMAP is an unofficial tool. Follow the game operator's policies and the terms of each asset provider, and use it at your own discretion.

<a id="en-roadmap"></a>

## Planned additions

- Shop and guild markers on every town map
- A signpost guide when entering a field, showing coordinates and an approximate direction
- Japanese display names may be revised later to match future official terminology

[Back to contents](#contents)
