# 執行行為

## 前景規則
- 前景判定只看 `nikke.exe`。
- 是否阻斷原生輸入，取決於前景狀態與全域熱鍵設定。

## Hook 安全性
- Hook 回呼採 fail-open：回呼異常時優先放行。
- 會忽略注入事件（`LLKHF_INJECTED` / `LLMHF_INJECTED`），避免腳本送出的輸入被自己再攔截。
- 關閉流程必須先解除 Hook、停止訊息迴圈，再進行 UI 收尾。

## 阻斷與觸發規則（重點）
- Hook 回呼只做最小工作量：解析鍵名、更新按下狀態、必要時送事件進佇列、依條件決定是否阻斷。
- 只有在以下條件同時成立時，才會阻斷該事件（return `1`）：
- 事件是 `down`
- key blocking 已啟用（通常是遊戲前景）
- 該鍵名在「已啟用」的綁定集合內
- 其他鍵一律快速放行（`CallNextHookEx`）。

## 綁定模式（變更按鍵）
- UI 進入綁定模式時，下一個 `down` 事件會回傳鍵名並完成綁定。
- 綁定模式不會阻斷輸入（避免把使用者的操作鎖死）。

## UI 執行緒規則
- 背景執行緒不得直接操作 Tk 元件。
- UI 更新必須經主執行緒排程（例如 `after`）。

## 計時行為
- 動作循環使用可取消等待，確保在放鍵或 context 變化時能立即停止。
- 連點延遲為可設定；鍵盤連點採固定步進策略。

## Rhythm mode PRESET 2
- The option is stored as `General.RhythmPreset2` and defaults to disabled.
- When enabled, PRESET 2 listens to `a`, `s`, `;`, and `'` as pass-through hotkeys.
- `a` + `s` holds `lshift`, and `;` + `'` holds `rshift`; either Shift releases as soon as its pair is no longer held.
- Pressing all four trigger keys latches `space`; `space` stays held until the original four-key latch set is fully released, and later keydowns do not extend that latch.
- Disabling the option, losing the active context, or shutting down the app releases any PRESET 2 output keys to avoid stuck Shift/Space state.
