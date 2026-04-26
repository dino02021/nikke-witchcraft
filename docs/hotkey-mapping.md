# 熱鍵對照細節

> 本文件是 `spec.md` 的補充文件，只描述目前版本支援的鍵名、對照與阻斷細節。
>
> 長期原則與規格入口以 `spec.md` 為準。

## 支援的輸入名稱

使用者綁定會儲存為正規化後的鍵名。常見支援名稱如下：

- 英文字母：`a` 到 `z`
- 數字：`0` 到 `9`
- 功能鍵：`f1` 到 `f24`
- 導航鍵：`home`、`end`、`pageup`、`pagedown`、`insert`、`delete`、`printscreen`
- 方向鍵：`up`、`down`、`left`、`right`
- 控制鍵：`esc`、`tab`、`enter`、`space`、`backspace`、`capslock`、`numlock`、`scrolllock`、`pause`
- 數字鍵盤：`num0` 到 `num9`、`num+`、`num-`、`num*`、`num/`、`num.`、`numsep`
- 滑鼠鍵：`left`、`right`、`middle`、`x1`、`x2`

## 修飾鍵

支援左右側獨立修飾鍵：

- `lshift`、`rshift`
- `lctrl`、`rctrl`
- `lalt`、`ralt`
- `lcmd`、`rcmd`

為了相容舊設定，也保留泛用修飾鍵名稱：

- `shift` 會匹配 `lshift` 或 `rshift`
- `ctrl` 會匹配 `lctrl` 或 `rctrl`
- `alt` 會匹配 `lalt` 或 `ralt`
- `cmd` 會匹配 `lcmd` 或 `rcmd`

## OEM 符號鍵

標準鍵盤配置下支援以下 OEM 符號鍵：

```text
` ; = , - . / [ ] \ '
```

`~` 會正規化成 `` ` ``，因為在 US 配置下兩者來自同一顆實體鍵。

## 未知或冷門鍵

低階 hook 收到尚未列入對照表的鍵盤 VK 時，會回傳穩定名稱 `vk_XX`，其中 `XX` 是 16 進位 VK 值。這類鍵仍可被綁定與保存。

## 阻斷規則

啟用中的一般綁定熱鍵，在有效情境下會阻斷原始輸入，讓綁定功能取代原鍵功能。

pass-through 熱鍵只監聽，不阻斷原始輸入。PRESET 2 的 `a`、`s`、`;`、`'` 就是 pass-through 觸發鍵。

啟用 `General.HotkeysPaused` 時，按鍵綁定區熱鍵會停用並從阻斷集合移除，原始按鍵會正常穿透。

## 滑鼠綁定

滑鼠事件只在「某個滑鼠鍵實際被啟用熱鍵綁定」或「正在綁定模式」時處理。若只綁定 `x2`，程式只監聽 `x2`；未綁定的 `left`、`right` 不會成為熱鍵候選。

連點功能啟動前會用 Windows 即時狀態檢查 left/right 是否正被按住；若有按住會先放開再開始循環。這是連點動作的啟動前檢查，不代表 left/right 會被 mouse hook 長期監聽。

## 音遊模式 PRESET 2

固定觸發鍵為 `a`、`s`、`;`、`'`。

- `a` + `s` 會鎖住 `lshift`。
- `;` + `'` 會鎖住 `rshift`。
- `a` + `s` + `;` + `'` 會鎖住 `space`。

每個輸出鍵只在當次 latch 的原始觸發鍵集合全部放開後才釋放。latch 成立後補按的新鍵不會延長該次 latch。
