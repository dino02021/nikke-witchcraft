# 熱鍵對應表

## 用途
本檔記錄容易變動的按鍵對應細節，避免把這類內容寫死在 `spec.md`。

## 程式位置
- 鍵盤與滑鼠熱鍵的正規化：`lib/hotkeys.py`
- 低階 VK 到鍵名映射：`lib/winhook.py`

## 鍵名規則（總覽）
本專案使用「字串鍵名」作為綁定資料的唯一識別。

### 鍵盤（常見）
- 英文字母：`a` ~ `z`
- 主鍵盤數字：`0` ~ `9`
- 功能鍵：`f1` ~ `f24`
- 導航/編輯：`home/end/pageup/pagedown/insert/delete/printscreen`
- 方向鍵：`up/down/left/right`
- 系統/控制：`esc/tab/enter/space/backspace/capslock/numlock/scrolllock/pause`
- Numpad：`num0` ~ `num9`、`num+ num- num* num/ num. numsep`

### 左右鍵（不同名稱）
以下鍵位會以左右不同名稱回報，便於精準綁定：
- `lshift` / `rshift`
- `lctrl` / `rctrl`
- `lalt` / `ralt`
- `lcmd` / `rcmd`

### 舊名稱相容（綁定時）
為了相容舊設定，你仍可綁：`shift/ctrl/alt/cmd`，其行為是「同時匹配左右」：
- 綁 `shift` 會同時匹配 `lshift` 與 `rshift`
- 綁 `ctrl` 會同時匹配 `lctrl` 與 `rctrl`
- 綁 `alt` 會同時匹配 `lalt` 與 `ralt`
- 綁 `cmd` 會同時匹配 `lcmd` 與 `rcmd`

### OEM 符號鍵（依鍵盤佈局可能不同）
常見符號（US 佈局）：
```
` ; = , - . / [ ] \ '
```
另外：
- `~` 會正規化為 `` ` ``（多數 US 佈局是同一顆實體鍵的 shift 版）

### 滑鼠鍵
- `left`、`right`、`middle`、`x1`、`x2`

## 全鍵位（含冷門鍵）支援
本專案允許綁定未列入表內的冷門鍵：
- 已知 VK：回傳可讀鍵名（例如 `a`, `1`, `esc`, `pageup`）
- 未知/冷門 VK：回傳 `vk_XX`（16 進位），仍可綁定

## 維護規則
新增或調整可綁定按鍵時，必須同步更新：
- `lib/winhook.py`（VK 映射 / 鍵名）
- `lib/hotkeys.py`（鍵名正規化與相容規則）
- 本文件（對外行為說明）

## Rhythm mode PRESET 2
- The fixed pass-through trigger keys are `a`, `s`, `;`, and `'`.
- Holding `a` + `s` latches `lshift` until both original trigger keys are released.
- Holding `;` + `'` latches `rshift` until both original trigger keys are released.
- Holding all four trigger keys latches `space`; it releases only after the original four-key latch set is fully released.
- These keys are registered as pass-through hotkeys, so PRESET 2 itself does not block native input.
