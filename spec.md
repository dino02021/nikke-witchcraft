# NikkeWitchcraft 規格

> 本文件只保留長期穩定的開發規則與設計原則。  
> 容易變動的實作細節請寫到 `docs/`。

## 目標與範圍
- 使用 Python 實作 Nikke 小工具，提供可維護的模組化架構。
- 平台限定 Windows 10/11。
- 支援多熱鍵並行執行，不採排隊/搶占模型。
- 在可接受 CPU 負擔下維持操作時序精度。

## 版本與命名
- 版本號定義於 `lib/config.py` 的 `APP_VERSION`。
- 主視窗標題由 `APP_TITLE` 組成，格式：`NikkeWitchcraft v<版本>`。
- 功能命名使用一致代號（例如 `DSpam`, `ClickSeq1`, `Jitter`），避免混用舊名。

## 設定與資料檔
- 設定根目錄：`%USERPROFILE%\\Documents\\NikkeWitchcraftSettings`。
- 設定檔路徑由 `ConfigStore` 統一管理。
- 日誌檔路徑由 `Logger` 統一管理，預設寫入 `%LOCALAPPDATA%\\NikkeWitchcraft\\Logs`。
- 新增設定項目時必須同時更新：
- `Settings` dataclass
- `ConfigStore.load/save`
- 對應 UI 與行為層讀寫

## 輸入與執行模型
- 熱鍵監聽、動作執行、UI 更新必須解耦。
- Hook 回呼採 fail-open 原則：異常時優先放行，避免全域輸入鎖死。
- 只有符合條件的綁定鍵可以被阻斷；非綁定輸入預設放行。
- 背景執行緒不得直接操作 Tk 元件，必須經主執行緒排程（例如 `after`）。

## 前景與阻斷規則
- 前景判定以 `nikke.exe` 為唯一依據。
- 是否阻斷原生輸入由遊戲前景與全域熱鍵設定共同決定。
- 任何改動需保證不會出現全鍵鼠失效。

## UI 規範
- UI 建立優先使用 `lib/gui/layout.py` 的工廠方法，避免直接散寫 `ttk` 元件。
- `ui_constants.py` 是間距與排版常數唯一來源。
- 區塊排列遵循由上到下、由左到右；同類互動元件需維持一致間距與狀態語義。
- 禁用狀態必須有視覺回饋（控件禁用、文字變灰、警示色同步調整）。

## 程式風格
- 檔案編碼統一 UTF-8。
- `bool` 命名以 `is_` 開頭。
- 對外方法置前，對內輔助方法以 `_` 開頭並集中在類別後段。
- 優先使用提前返回降低巢狀層級。
- 對話框統一使用 `create_dialog(...)`，必須 `grab_set + transient + close_dialog`。

## 測試與驗證
- 最低要求：修改後可通過 `python -m py_compile`。
- 影響輸入層或 Hook 的改動，需額外做手動驗證：
- 前景/背景切換
- 綁定鍵阻斷與穿透
- 啟停與關閉流程

## 文件分工
- 本文件：原則與規範。
- `docs/hotkey-mapping.md`：鍵名/掃碼/映射等可變動細節。
- `docs/runtime-behavior.md`：前景判定、阻斷策略、關閉順序、異常保護等行為細節。
- `CHANGELOG.md`：版本差異與發佈內容。

## 文件補全規則（人工同步）
- 文件是規則的一部分：修改程式碼後，必須同步更新 `docs/`，使其與「目前版本實作」一致。
- 特別是修改以下內容時，必須補齊對應文件：
- `lib/winhook.py`（鍵名對應、左右鍵命名、未知鍵策略）=> `docs/hotkey-mapping.md`
- `lib/hotkeys.py`（正規化/相容規則、阻斷與觸發條件）=> `docs/hotkey-mapping.md`、`docs/runtime-behavior.md`
- 前景判定/阻斷策略/關閉順序 => `docs/runtime-behavior.md`
- 文件內容以「使用者能照著理解目前行為」為準，不要求列出所有 VK 的完整清單。
