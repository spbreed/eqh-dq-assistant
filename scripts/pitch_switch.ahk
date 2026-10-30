; Pitch mode switcher for one monitor: OBS lightboard ⇄ browser/AWS, while one Teams screen share runs throughout.
; AutoHotkey v2 (Windows). See docs/PITCH_SCRIPT.md → "Studio setup: OBS + Teams on one monitor".
;
;   Ctrl+Alt+L  Lightboard mode: OBS scene "LB-Full"; projector restored full screen and in front
;   Ctrl+Alt+D  Deck            Ctrl+Alt+A  App (assistant)   Ctrl+Alt+W  AWS console   Ctrl+Alt+T  Terminal
;               (each of these: OBS scene "Presenter", projector minimised, that window in front)
;   Ctrl+Alt+P  Prepare the projector once: borderless, maximised
;
; In OBS → Settings → Hotkeys, set "Switch to scene LB-Full" = Ctrl+Alt+F1 and "Switch to scene Presenter" = Ctrl+Alt+F2.
; Window titles below match this repo's deck and app; adjust with Window Spy if yours differ.
#Requires AutoHotkey v2.0
#SingleInstance Force
SetTitleMatchMode 2
SetKeyDelay 30, 30

PROJ    := "Windowed Projector (Program)"
DECK    := "AI Data Quality Assistant — Emergere"
APP     := "Data Quality Assistant"          ; the assistant pages (the deck is excluded below)
AWS     := "AWS"                            ; console tab titles contain "| AWS" / "AWS Management Console"
TERM    := "ahk_exe WindowsTerminal.exe"

ObsScene(fkey) {
    SendEvent "{Ctrl down}{Alt down}{" fkey "}{Alt up}{Ctrl up}"
}

LightboardMode(*) {
    ObsScene("F1")
    if WinExist(PROJ) {
        WinRestore PROJ
        WinMaximize PROJ
        WinActivate PROJ
    }
}

ScreenMode(title, exclude := "") {
    ObsScene("F2")
    if WinExist(PROJ)
        WinMinimize PROJ
    if WinExist(title, , exclude)
        WinActivate title, , exclude
}

PrepareProjector(*) {
    if !WinExist(PROJ) {
        MsgBox "Open it first: right-click the OBS preview → Windowed Projector (Program)."
        return
    }
    WinSetStyle "-0xC40000", PROJ   ; remove the title bar and border
    WinMaximize PROJ
}

^!l::LightboardMode()
^!d::ScreenMode(DECK)
^!a::ScreenMode(APP, "Emergere")
^!w::ScreenMode(AWS)
^!t::ScreenMode(TERM)
^!p::PrepareProjector()
